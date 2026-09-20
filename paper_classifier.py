"""
论文学科自动分类模块。

双轨策略：
  1. SBERT 语义分类（优先）— 零样本：编码论文文本 + 学科描述 → 余弦相似度
  2. LLM 分类（备选）— 直接让 LLM 判断学科
  3. 关键词规则（兜底）— 原有 CATEGORY_PATTERNS 方法

优势：不需要训练数据，基于语义理解即可分类，对跨学科论文也有效。
"""

import logging
import numpy as np

from utils.sbert_manager import sbert_manager

logger = logging.getLogger("InnoCite.PaperClassifier")


# 学科编码 → 中文名 + 描述（用于 SBERT 零样本匹配）
CATEGORY_DESCRIPTIONS = {
    "cs.CV": "计算机视觉与图像处理 Computer Vision and Pattern Recognition。研究图像识别、目标检测、图像分割、图像生成、视频理解等。",
    "cs.CL": "自然语言处理与计算语言学 Computation and Language。研究机器翻译、文本生成、情感分析、信息抽取、语言模型等。",
    "cs.AI": "人工智能 Artificial Intelligence。研究知识表示、推理、规划、搜索算法、多智能体系统等。",
    "cs.LG": "机器学习 Machine Learning。研究深度学习、强化学习、优化算法、模型泛化、联邦学习等。",
    "cs.IR": "信息检索 Information Retrieval。研究搜索引擎、推荐系统、排序算法、信息过滤等。",
    "cs.RO": "机器人学 Robotics。研究机器人控制、路径规划、SLAM、人机交互等。",
    "cs.HC": "人机交互 Human-Computer Interaction。研究用户界面、可用性、交互设计等。",
    "cs.NE": "神经网络与进化计算 Neural and Evolutionary Computing。研究神经网络架构、遗传算法等。",
    "cs.SD": "软件工程 Software Engineering。研究软件开发方法、测试、维护等。",
    "cs.DB": "数据库 Databases。研究数据管理、查询优化、数据挖掘等。",
    "stat.ML": "统计机器学习 Statistics and Machine Learning。研究统计学习方法、贝叶斯推断等。",
}


class PaperClassifier:
    """论文学科自动分类器。

    用法：
        classifier = PaperClassifier()
        category = classifier.classify(title, abstract)
        # 返回: "cs.CV" 或 None（未知时）
    """

    def __init__(self, app_config=None):
        self._app_config = app_config
        self._category_embeddings = None
        self._category_list = None

    @property
    def sbert_available(self):
        """检查 SBERT 是否可用（由全局 SBERTManager 统一管理）。"""
        return sbert_manager.available

    @property
    def model(self):
        """获取共享的 SBERT 模型实例，并触发学科向量预计算。"""
        m = sbert_manager.model
        if m is not None:
            self._precompute_category_embeddings()
        return m

    @property
    def llm_enabled(self):
        """检查 LLM 分类是否启用"""
        if self._app_config:
            enabled = self._app_config.get("AUTO_CLASSIFY_ENABLED", True) \
                if hasattr(self._app_config, 'get') else True
        else:
            import os
            enabled = os.environ.get("AUTO_CLASSIFY_ENABLED", "1") == "1"
        return enabled

    def _precompute_category_embeddings(self):
        """预计算所有学科描述的 SBERT 向量（一次计算，多次复用）"""
        model = self.model
        if model is None or self._category_embeddings is not None:
            return

        self._category_list = list(CATEGORY_DESCRIPTIONS.keys())
        descriptions = [CATEGORY_DESCRIPTIONS[c] for c in self._category_list]

        try:
            self._category_embeddings = sbert_manager.encode(
                descriptions, show_progress_bar=False, convert_to_numpy=True
            )
        except Exception:
            logger.warning("学科向量预计算失败")
            self._category_embeddings = None

    def classify(self, title, abstract):
        """对论文进行学科分类。

        返回:
            str: 学科代码（如 "cs.CV"），无法判断时返回 None
        """
        text = f"{title or ''} {abstract or ''}".strip()
        if not text:
            return None

        # ── 路径 1：SBERT 语义分类 ──
        if self.sbert_available and self._category_embeddings is not None:
            try:
                result = self._classify_sbert(text)
                if result:
                    return result
            except Exception:
                logger.debug("SBERT 分类异常，尝试 LLM", exc_info=True)

        # ── 路径 2：LLM 分类 ──
        if self.llm_enabled:
            try:
                from llm_client import get_llm_client
                llm = get_llm_client()
                if llm and llm.available:
                    result = llm.classify_paper(title, abstract)
                    if result and result in CATEGORY_DESCRIPTIONS:
                        return result
            except Exception:
                logger.debug("LLM 分类异常", exc_info=True)

        return None

    def _classify_sbert(self, text):
        """SBERT 零样本分类"""
        model = self.model
        if model is None:
            return None
        # 编码论文文本（经 SBERTManager 线程安全封装）
        text_embedding = sbert_manager.encode(
            [text], show_progress_bar=False, convert_to_numpy=True
        )[0]

        # 计算与各学科的余弦相似度
        text_norm = text_embedding / (np.linalg.norm(text_embedding) + 1e-10)
        cat_norms = self._category_embeddings / (
            np.linalg.norm(self._category_embeddings, axis=1, keepdims=True) + 1e-10
        )
        similarities = np.dot(cat_norms, text_norm)

        # 取最高分
        best_idx = int(np.argmax(similarities))
        best_score = float(similarities[best_idx])

        # 阈值过滤：相似度太低说明不属于任何已知学科
        if best_score < 0.15:
            return None

        return self._category_list[best_idx]


# ── 模块级单例 ──
_classifier = None


def get_classifier(app_config=None):
    """获取论文分类器单例"""
    global _classifier
    if _classifier is None:
        _classifier = PaperClassifier(app_config)
    return _classifier
