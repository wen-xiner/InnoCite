"""
InnoCite - 学术论文创新点提炼与跨学科推荐系统
Flask 主入口，负责应用工厂、配置和蓝图注册。
路由逻辑拆分到 routes/ 包下的各蓝图模块。
"""

import os
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime

from flask import Flask, render_template, request, jsonify, session, redirect, url_for

from flasgger import Swagger
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect, CSRFError
from models import db
from config import get_config
from utils.response import api_error, ErrorCode

# ── 蓝图导入 ──
from routes.papers import papers_bp
from routes.innovation import innovation_bp
from routes.trends import trends_bp
from routes.recommend import recommend_bp
from routes.report import report_bp
from routes.admin import admin_bp
from routes.auth import auth_bp
from routes.evaluate import evaluate_bp
from routes.bookmarks import bookmarks_bp
from keyword_trend import _register_cache_invalidation


def create_app(config_class=None):
    """Flask 应用工厂函数。

    参数:
        config_class: 配置类，为 None 时自动从 APP_ENV 环境变量读取。
    """
    app = Flask(__name__)

    # ── 加载配置 ──
    if config_class is None:
        config_class = get_config()
    app.config.from_object(config_class)

    # 确保上传目录存在
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    # ── 日志 ──
    log_level = getattr(logging, app.config.get("LOG_LEVEL", "INFO").upper())
    log_dir = os.path.dirname(app.config["LOG_FILE"])
    os.makedirs(log_dir, exist_ok=True)

    # 滚动文件处理器：单文件最大 10MB，保留 10 个备份
    file_handler = RotatingFileHandler(
        app.config["LOG_FILE"],
        maxBytes=app.config.get("LOG_MAX_BYTES", 10 * 1024 * 1024),
        backupCount=app.config.get("LOG_BACKUP_COUNT", 10),
        encoding="utf-8",
    )
    file_handler.setFormatter(logging.Formatter(
        "[%(asctime)s] %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(logging.Formatter(
        "[%(asctime)s] %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))

    logging.basicConfig(level=log_level, handlers=[stream_handler, file_handler])

    # ── Swagger / OpenAPI ──
    if app.config.get("SWAGGER_UI_ENABLED", True):
        swagger_config = {
            "headers": [],
            "specs": [{"endpoint": "apispec", "route": "/apispec.json"}],
            "static_url_path": "/flasgger_static",
            "swagger_ui": True,
            "specs_route": app.config["SWAGGER_ROUTE"],
        }
        Swagger(app, config=swagger_config, template={
            "info": {
                "title": "InnoCite API",
                "description": "学术论文创新点提炼与跨学科推荐系统 API 文档",
                "version": "1.0.0",
            },
            "tags": [
                {"name": "论文导入", "description": "论文数据导入（arXiv / CSV / PDF）"},
                {"name": "创新点", "description": "创新点提取、查看与编辑"},
                {"name": "关键词趋势", "description": "关键词提取与热度时序分析"},
                {"name": "跨学科推荐", "description": "基于向量相似度的跨学科推荐"},
                {"name": "统计", "description": "数据库统计摘要"},
                {"name": "报告", "description": "PDF 报告与数据导出"},
                {"name": "系统管理", "description": "嵌入重建、推荐重建等管理操作"},
            ],
        })

    # ── CSRF 保护 ──
    csrf = CSRFProtect(app)

    # 豁免 Swagger / API 文档路由（Swagger UI 通过 JS 发请求，不走 CSRF cookie）
    if app.config.get("SWAGGER_UI_ENABLED", True):
        csrf.exempt("apispec")
        csrf.exempt("flasgger.static")
        csrf.exempt("flasgger.apispec_swagger")
        csrf.exempt("flasgger.oauth_redirect")

    # CSRF 校验失败时返回友好 JSON（API 请求）或 HTML（页面请求）
    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        if request.path.startswith("/api/") or request.path.startswith("/import/"):
            return api_error(
                "CSRF 校验失败，请刷新页面后重试。",
                code=ErrorCode.CSRF_ERROR, status=400,
            )
        return render_template(
            "base.html",
            error_code=400,
            error_message="表单已过期，请返回上一页刷新后重新提交。",
        ), 400

    # ── 数据库 + 迁移 ──
    db.init_app(app)
    migrate = Migrate(app, db)

    # SQLite 并发写优化：WAL 模式 + busy_timeout，降低后台任务与
    # 请求线程并发写时的 "database is locked" 概率（仅对 SQLite 生效）
    if app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"):
        from sqlalchemy import event as _sa_event
        from sqlalchemy.engine import Engine as _SAEngine

        @_sa_event.listens_for(_SAEngine, "connect")
        def _set_sqlite_pragma(dbapi_connection, connection_record):
            try:
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA busy_timeout=5000")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.close()
            except Exception:
                pass

    # 注册数据库事件：论文增删时自动失效关键词缓存
    _register_cache_invalidation()

    # ── 注册蓝图 ──
    app.register_blueprint(auth_bp)         # 认证蓝图最先注册
    app.register_blueprint(papers_bp)
    app.register_blueprint(innovation_bp)
    app.register_blueprint(trends_bp)
    app.register_blueprint(recommend_bp)
    app.register_blueprint(report_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(evaluate_bp)
    app.register_blueprint(bookmarks_bp)

    # ── 数据库迁移 + 初始化管理员 ──
    with app.app_context():
        # 策略：优先使用 Alembic 迁移（生产级），
        # 当 migrations 目录不存在时（首次部署/开发环境）回退到 create_all。
        migrations_dir = os.path.join(os.path.dirname(__file__), "migrations")
        if os.path.isdir(migrations_dir):
            from flask_migrate import upgrade as _migrate_upgrade
            _migrate_upgrade()
            logging.getLogger("InnoCite").info("数据库迁移已应用（Alembic upgrade）")
        else:
            # 仅在数据库中无任何表时才输出建表日志（避免每次重启重复打印）
            from sqlalchemy import inspect as _inspect
            _existing_tables = _inspect(db.engine).get_table_names()
            db.create_all()
            if not _existing_tables:
                logging.getLogger("InnoCite").info(
                    "migrations/ 目录不存在，已使用 db.create_all() 建表"
                )

        # 确保默认管理员账户存在（幂等）
        from models import User
        admin_username = app.config.get("DEFAULT_ADMIN_USERNAME", "admin")
        if not User.query.filter_by(username=admin_username).first():
            admin = User(
                username=admin_username,
                display_name="管理员",
                is_active=True,
                is_admin=True,
            )
            admin.set_password(app.config.get("DEFAULT_ADMIN_PASSWORD", "admin123"))
            db.session.add(admin)
            db.session.commit()
            logging.getLogger("InnoCite").info(
                "已创建默认管理员: %s（请尽快修改默认密码）", admin_username
            )

    # ── 健康检查 ──
    # 供部署探针 / 运维巡检使用，无需登录。
    @app.route("/healthz")
    def healthz():
        """健康检查：DB 连通性 + SBERT 状态 + LLM key 配置。"""
        import time as _time
        status = {"status": "ok", "checks": {}, "timestamp": int(_time.time())}

        # 1. 数据库连通性
        try:
            from sqlalchemy import text as _sa_text
            db.session.execute(_sa_text("SELECT 1"))
            status["checks"]["database"] = "ok"
        except Exception as e:
            status["checks"]["database"] = f"error: {e}"
            status["status"] = "degraded"

        # 2. SBERT 状态
        from utils.sbert_manager import sbert_manager
        status["checks"]["sbert"] = "ok" if sbert_manager.available else "unavailable"

        # 3. LLM key 配置
        has_key = bool(app.config.get("DEEPSEEK_API_KEY"))
        status["checks"]["llm"] = "ok" if has_key else "not_configured"

        # 4. 数据库论文数（只读，用于简单统计）
        try:
            from models import Paper
            status["stats"] = {"paper_count": Paper.query.count()}
        except Exception:
            status["stats"] = {"paper_count": None}

        # DB 故障视为不健康（返回 503），其余状态正常返回 200
        if status["checks"]["database"] != "ok":
            return jsonify(status), 503
        return jsonify(status)

    # ── 错误处理 ──
    @app.errorhandler(404)
    def not_found(e):
        if request.path.startswith("/api/"):
            return api_error("资源未找到", code=ErrorCode.NOT_FOUND, status=404)
        return render_template(
            "base.html", error_code=404, error_message="页面未找到"
        ), 404

    @app.errorhandler(500)
    def internal_error(e):
        db.session.rollback()
        if request.path.startswith("/api/"):
            return api_error(
                "服务器内部错误",
                code=ErrorCode.INTERNAL_ERROR, status=500,
            )
        return render_template(
            "base.html", error_code=500, error_message="服务器内部错误"
        ), 500

    # ── 全局登录拦截 ──
    # 除登录页、静态文件、API 文档外，所有请求必须先登录。
    @app.before_request
    def require_login():
        # 无需登录的公开路径
        public_prefixes = [
            "/auth/login",
            "/auth/logout",
            "/auth/register",
            "/healthz",
            "/static/",
            "/apidocs/",
            "/apispec.json",
            "/flasgger_static/",
        ]
        if any(request.path.startswith(p) for p in public_prefixes):
            return None

        # 未登录：API 请求返回 JSON，页面请求重定向到登录页
        if "user_id" not in session:
            if request.path.startswith("/api/") or request.path.startswith("/import/"):
                return api_error(
                    "请先登录",
                    code=ErrorCode.UNAUTHORIZED, status=401,
                )
            return redirect(url_for("auth.login", next=request.url))

        return None

    # ── Gzip 压缩（零依赖，自动压缩 JSON/HTML/CSS/JS 响应）──
    from utils.gzip_middleware import GzipMiddleware
    app.wsgi_app = GzipMiddleware(app.wsgi_app)

    # 注入应用实例给后台任务队列（后台线程需独立 app context 访问数据库）
    from utils.task_queue import set_app as _task_queue_set_app
    _task_queue_set_app(app)

    return app


# ── 启动入口 ──
if __name__ == "__main__":
    app = create_app()

    # Werkzeug 重载器在 Debug 模式下会启动父子两个进程，
    # 仅在实际运行进程（子进程）中打印 banner，避免重复输出。
    is_reloader_child = os.environ.get("WERKZEUG_RUN_MAIN") == "true"
    show_banner = is_reloader_child or not app.config.get("DEBUG", False)

    if show_banner:
        banner = (
            "\n" + "=" * 60 + "\n"
            "[InnoCite] 学术论文创新点提炼与跨学科推荐系统\n"
            "=" * 60 + "\n"
            f"[*] 环境: {os.environ.get('APP_ENV', 'development')}\n"
            "[*] 访问地址: http://127.0.0.1:5000\n"
            "[*] API 文档: http://127.0.0.1:5000/apidocs/\n"
            "[*] 日志文件: instance/innocite.log\n"
            "=" * 60 + "\n"
        )
        print(banner)
        logging.getLogger("InnoCite").info("InnoCite 启动")

    app.run(debug=app.config["DEBUG"], host="0.0.0.0", port=5000)
