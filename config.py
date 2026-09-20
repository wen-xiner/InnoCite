"""
InnoCite 多环境配置管理。

通过环境变量 APP_ENV 切换配置：
    APP_ENV=development  (默认) — 开发环境
    APP_ENV=testing      — 测试环境
    APP_ENV=production   — 生产环境

使用方式:
    from config import get_config
    app.config.from_object(get_config())
"""

import os
import secrets
from utils import BASE_DIR

# 自动加载 .env 文件（若存在）
try:
    from dotenv import load_dotenv
    _env_path = os.path.join(BASE_DIR, ".env")
    if os.path.exists(_env_path):
        load_dotenv(_env_path)
except ImportError:
    pass


class BaseConfig:
    """基础配置（所有环境共享的默认值）"""

    # ── Flask ──
    SECRET_KEY = os.environ.get("SECRET_KEY", secrets.token_hex(32))
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB 上传限制

    # ── 数据库 ──
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        f"sqlite:///{os.path.join(BASE_DIR, 'instance', 'innocite.db')}",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # ── 文件上传 ──
    UPLOAD_FOLDER = os.environ.get(
        "UPLOAD_FOLDER",
        os.path.join(BASE_DIR, "instance", "uploads"),
    )

    # ── 日志 ──
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
    LOG_FILE = os.environ.get(
        "LOG_FILE",
        os.path.join(BASE_DIR, "instance", "innocite.log"),
    )
    LOG_MAX_BYTES = 10 * 1024 * 1024   # 单个日志文件最大 10MB
    LOG_BACKUP_COUNT = 10              # 保留最近 10 个备份文件

    # ── Swagger / OpenAPI ──
    SWAGGER_UI_ENABLED = True
    SWAGGER_ROUTE = "/apidocs/"

    # ── 推荐系统 ──
    SBERT_MODEL_NAME = os.environ.get(
        "SBERT_MODEL_NAME", "all-MiniLM-L6-v2"
    )
    RECOMMENDATION_TOP_N_DEFAULT = 3
    TFIDF_MAX_FEATURES = 3000

    # ── CSRF 保护 ──
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = 3600       # Token 有效期 1 小时
    WTF_CSRF_SSL_STRICT = False      # 开发环境不使用 HTTPS

    # ── 认证系统 ──
    DEFAULT_ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    DEFAULT_ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")
    # 登录后会话保持时间（秒），None 表示浏览器关闭时失效
    PERMANENT_SESSION_LIFETIME = 86400  # 24 小时

    # ── arXiv API ──
    ARXIV_SEARCH_DELAY = 0.1     # 批量搜索间隔（秒）
    ARXIV_MAX_RESULTS = 100      # 单次搜索最大结果数

    # ── GROBID 学术 PDF 解析 ──
    # Docker 启动：docker run -p 8070:8070 lfoppiano/grobid:0.8.1
    GROBID_URL = os.environ.get("GROBID_URL", "http://localhost:8070")
    GROBID_TIMEOUT = int(os.environ.get("GROBID_TIMEOUT", "30"))  # 秒
    GROBID_ENABLED = os.environ.get("GROBID_ENABLED", "1") == "1"

    # ── LLM 大语言模型配置 ──
    # 优先级：DeepSeek API（主力）→ 规则引擎（兜底）
    # DeepSeek API 兼容 OpenAI SDK，对 JSON 结构化输出支持优秀
    LLM_BACKEND = os.environ.get("LLM_BACKEND", "auto")
    DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    # 双模型策略：flash 处理快速任务，pro 处理深度推理
    DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")
    DEEPSEEK_MODEL_PRO = os.environ.get("DEEPSEEK_MODEL_PRO", "deepseek-v4-pro")
    # 功能开关
    LLM_INNOVATION_ENABLED = os.environ.get("LLM_INNOVATION_ENABLED", "1") == "1"
    LLM_REASON_ENABLED = os.environ.get("LLM_REASON_ENABLED", "1") == "1"
    KEYBERT_ENABLED = os.environ.get("KEYBERT_ENABLED", "1") == "1"
    AUTO_CLASSIFY_ENABLED = os.environ.get("AUTO_CLASSIFY_ENABLED", "1") == "1"
    # LLM 请求参数
    LLM_TIMEOUT = int(os.environ.get("LLM_TIMEOUT", "30"))
    LLM_MAX_RETRIES = int(os.environ.get("LLM_MAX_RETRIES", "2"))
    LLM_TEMPERATURE = float(os.environ.get("LLM_TEMPERATURE", "0.3"))


class DevelopmentConfig(BaseConfig):
    """开发环境配置"""
    DEBUG = True
    TESTING = False
    SECRET_KEY = os.environ.get("SECRET_KEY", "innocite-dev-key")
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "DEBUG")


class TestingConfig(BaseConfig):
    """测试环境配置"""
    DEBUG = False
    TESTING = True
    SECRET_KEY = os.environ.get("SECRET_KEY", "innocite-test-key")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "sqlite:///:memory:"
    )
    SWAGGER_UI_ENABLED = False
    ARXIV_SEARCH_DELAY = 0  # 测试时不需要延迟


class ProductionConfig(BaseConfig):
    """生产环境配置"""
    DEBUG = False
    TESTING = False
    # 生产环境必须通过环境变量设置密钥，无默认值时拒绝启动
    SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "WARNING")
    SWAGGER_UI_ENABLED = os.environ.get("SWAGGER_UI", "0") == "1"


# ── 配置映射 ──
_config_map = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    # 别名
    "dev": DevelopmentConfig,
    "test": TestingConfig,
    "prod": ProductionConfig,
}


def get_config():
    """根据 APP_ENV 环境变量返回对应的配置类。"""
    env = os.environ.get("APP_ENV", "development").lower()
    config_class = _config_map.get(env)
    if config_class is None:
        available = ", ".join(sorted(set(_config_map.keys())))
        raise ValueError(
            f"未知的 APP_ENV 值: '{env}'。可用值: {available}"
        )
    return config_class
