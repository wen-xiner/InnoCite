"""
SBERT 模型共享单例管理器。

应用启动后，Recommender / KeyBERTExtractor / PaperClassifier 三个模块
共享同一份 SentenceTransformer 模型实例和连通性检测结果，
避免重复加载模型（每个实例 ~400MB 内存）和重复网络检测。

连通性检测在后台线程中异步执行，不阻塞 HTTP 请求。
"""

import os
import logging
import threading

logger = logging.getLogger("InnoCite.SBERTManager")


class SBERTManager:
    """SBERT 模型全局单例管理器。

    用法：
        from utils.sbert_manager import sbert_manager

        if sbert_manager.available:
            model = sbert_manager.model
            embedding = model.encode(["text"])
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._model = None
        self._available = None
        self._encode_lock = threading.Lock()  # 串行化模型推理，保证线程安全
        self._model_name = os.environ.get(
            "SBERT_MODEL_NAME", "all-MiniLM-L6-v2"
        )
        self._initialized = True

    # ── 属性 ──────────────────────────────

    @property
    def available(self):
        """检测 SBERT 是否可用（首次调用时检测，后续复用结果）。"""
        if self._available is None:
            with self._lock:
                if self._available is None:
                    self._available = self._check_availability()
        return self._available

    @property
    def model(self):
        """获取 SBERT 模型实例（延迟加载，首次访问时触发）。"""
        if not self.available:
            return None
        if self._model is None:
            with self._lock:
                if self._model is None:
                    self._model = self._load_model()
        return self._model

    def encode(self, texts, **kwargs):
        """线程安全的 SBERT 编码封装。

        SentenceTransformer 模型内部存在共享状态，多线程并发调用
        encode() 可能产生竞态。通过全局锁将推理串行化，保证并发
        请求下的结果确定性。

        用法与 model.encode() 一致：
            sbert_manager.encode(["text1", "text2"], show_progress_bar=False)

        返回:
            与 SentenceTransformer.encode() 相同的 numpy 数组 / list
        """
        if not self.available:
            raise RuntimeError("SBERT 模型不可用")
        model = self.model
        if model is None:
            raise RuntimeError("SBERT 模型加载失败")
        with self._encode_lock:
            return model.encode(texts, **kwargs)

    @property
    def model_name(self):
        return self._model_name

    # ── 内部方法 ──────────────────────────

    def preload_async(self):
        """在后台线程中提前触发连通性检测，避免阻塞首次 HTTP 请求。"""
        if self._available is not None:
            return  # 已检测过
        t = threading.Thread(target=lambda: self.available, daemon=True)
        t.start()
        logger.debug("SBERT 连通性检测已在后台启动")

    def _check_availability(self):
        """直接尝试加载 SBERT 模型。

        模型优先从本地缓存加载；如缓存未命中，SentenceTransformer 会
        通过 HF_ENDPOINT 环境变量指定的镜像自动下载。
        """
        try:
            self._load_model()
            return True
        except Exception:
            logger.info(
                "SBERT 模型不可用（本地无缓存且网络不可达），"
                "将使用 TF-IDF / 规则引擎回退"
            )
            return False

    def _load_model(self):
        """实际加载 SentenceTransformer 模型（优先本地缓存，回退网络下载）。"""
        from sentence_transformers import SentenceTransformer

        model_path = self._local_model_path()
        if model_path:
            logger.info("从本地加载 SBERT 模型: %s", model_path)
            model = SentenceTransformer(model_path)
            logger.info("SBERT 模型加载完成（本地）: %s", self._model_name)
            return model

        logger.info("本地模型不存在，尝试从网络加载: %s ...", self._model_name)
        model = SentenceTransformer(self._model_name)
        logger.info("SBERT 模型加载完成: %s", self._model_name)
        return model

    @staticmethod
    def _local_model_path():
        """查找本地模型目录（data/models/<model_name>），存在则返回路径。"""
        import os as _os
        base_dir = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
        candidates = [
            _os.path.join(base_dir, "data", "models", "all-MiniLM-L6-v2"),
            _os.path.join(base_dir, "data", "models"),
        ]
        for c in candidates:
            if _os.path.isdir(c) and _os.path.isfile(_os.path.join(c, "modules.json")):
                return c
        return None


# ── 模块级单例 ──
sbert_manager = SBERTManager()
# 导入时即触发后台检测，不阻塞 import
sbert_manager.preload_async()
