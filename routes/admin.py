"""
系统管理蓝图：向量嵌入重建、推荐缓存重建、LLM 状态检查。
管理接口仅管理员可用（is_admin=True），普通登录用户无权触发全库重算。
"""

import logging
from functools import wraps

from flask import Blueprint, jsonify, session
from models import db, Paper, PaperEmbedding, Recommendation, User
from routes.helpers import get_recommender, get_llm_client
from utils.response import api_success, api_error, ErrorCode

logger = logging.getLogger("InnoCite")

admin_bp = Blueprint("admin", __name__)


def admin_required(f):
    """管理接口鉴权装饰器：仅允许 is_admin=True 的用户访问。

    全局登录拦截（app.py before_request）已保证 session 中有 user_id，
    此处只需校验角色。返回 JSON 错误，兼容 API 调用方。
    """
    @wraps(f)
    def wrapper(*args, **kwargs):
        user = db.session.get(User, session.get("user_id"))
        if user is None or not user.is_active or not user.is_admin:
            logger.warning(
                "非管理员尝试访问管理接口 %s (user_id=%s)",
                f.__name__,
                session.get("user_id"),
            )
            return api_error(
                "需要管理员权限",
                code=ErrorCode.FORBIDDEN, status=403,
            )
        return f(*args, **kwargs)
    return wrapper


@admin_bp.route("/api/rebuild-embeddings", methods=["POST"])
@admin_required
def rebuild_embeddings():
    """重建所有论文的 SBERT 向量嵌入
    ---
    tags:
      - 系统管理
    responses:
      200:
        description: 已重建的论文数量
    """
    try:
        PaperEmbedding.query.delete()
        db.session.commit()

        recommender = get_recommender()
        count = recommender.compute_all_embeddings()

        return api_success(message=f"已为 {count} 篇论文重新计算向量嵌入")
    except Exception as e:
        return api_error(
            f"向量重建失败: {str(e)}",
            code=ErrorCode.INTERNAL_ERROR, status=500,
        )


@admin_bp.route("/api/rebuild-recommendations", methods=["POST"])
@admin_required
def rebuild_recommendations():
    """重建所有跨学科推荐缓存
    ---
    tags:
      - 系统管理
    responses:
      200:
        description: 已生成的推荐结果数
    """
    try:
        Recommendation.query.delete()
        db.session.commit()

        recommender = get_recommender()
        papers = Paper.query.filter(Paper.abstract.isnot(None)).all()
        total = 0

        for paper in papers:
            try:
                results = recommender.recommend(
                    paper.id, top_n=3, force_refresh=True
                )
                total += len(results)
            except Exception:
                logger.exception("论文 %d 推荐重建失败", paper.id)

        return api_success(message=f"已生成 {total} 条推荐结果")
    except Exception as e:
        return api_error(
            f"推荐重建失败: {str(e)}",
            code=ErrorCode.INTERNAL_ERROR, status=500,
        )


@admin_bp.route("/api/llm-status")
@admin_required
def llm_status():
    """检查 LLM 各后端可用性
    ---
    tags:
      - 系统管理
    responses:
      200:
        description: LLM 后端状态
    """
    try:
        llm = get_llm_client()
        status = llm.check_availability()
        return api_success(data={
            "backends": status,
            "innovation_enabled": llm.available,
        })
    except Exception as e:
        return api_error(
            f"LLM 状态检查失败: {str(e)}",
            code=ErrorCode.INTERNAL_ERROR, status=500,
        )
