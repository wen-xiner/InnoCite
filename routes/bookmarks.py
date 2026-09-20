"""
用户论文收藏蓝图：添加/移除收藏、获取收藏列表。
"""

import logging
from flask import Blueprint, request, jsonify, session, render_template
from models import db, Paper, user_bookmarks
from utils.response import api_success, api_error, ErrorCode

logger = logging.getLogger("InnoCite")

bookmarks_bp = Blueprint("bookmarks", __name__)


@bookmarks_bp.route("/bookmarks")
def bookmarks_page():
    """我的收藏页面"""
    papers = Paper.query.order_by(Paper.created_at.desc()).all()
    return render_template("bookmarks.html", papers=papers)


def _get_user_id():
    """从 session 获取当前用户 ID。"""
    return session.get("user_id")


# ═══════════════════════════════════════════
# 收藏 / 取消收藏
# ═══════════════════════════════════════════

@bookmarks_bp.route("/api/bookmarks", methods=["GET"])
def list_bookmarks():
    """获取当前用户的收藏论文列表
    ---
    tags:
      - 收藏
    responses:
      200:
        description: 收藏论文列表
    """
    user_id = _get_user_id()
    if not user_id:
        return api_error("请先登录", code=ErrorCode.UNAUTHORIZED, status=401)

    papers = (
        Paper.query.join(user_bookmarks, Paper.id == user_bookmarks.c.paper_id)
        .filter(user_bookmarks.c.user_id == user_id)
        .order_by(user_bookmarks.c.created_at.desc())
        .all()
    )
    return api_success(data=[p.to_dict() for p in papers])


@bookmarks_bp.route("/api/bookmarks/check", methods=["GET"])
def check_bookmarks():
    """批量检查指定论文的收藏状态（返回已收藏的 paper_id 集合）
    ---
    tags:
      - 收藏
    parameters:
      - in: query
        name: paper_ids
        type: string
        description: 逗号分隔的论文 ID 列表
    responses:
      200:
        description: 已收藏的论文 ID 列表
    """
    user_id = _get_user_id()
    if not user_id:
        return api_success(data=[])

    ids_str = request.args.get("paper_ids", "")
    if not ids_str:
        return api_success(data=[])

    try:
        paper_ids = [int(x.strip()) for x in ids_str.split(",") if x.strip()]
    except ValueError:
        return api_success(data=[])

    rows = (
        db.session.query(user_bookmarks.c.paper_id)
        .filter(
            user_bookmarks.c.user_id == user_id,
            user_bookmarks.c.paper_id.in_(paper_ids),
        )
        .all()
    )
    return api_success(data=[r[0] for r in rows])


@bookmarks_bp.route("/api/bookmarks/<int:paper_id>", methods=["POST"])
def add_bookmark(paper_id):
    """收藏一篇论文
    ---
    tags:
      - 收藏
    parameters:
      - in: path
        name: paper_id
        type: integer
        required: true
        description: 论文 ID
    responses:
      200:
        description: 操作结果
    """
    user_id = _get_user_id()
    if not user_id:
        return api_error("请先登录", code=ErrorCode.UNAUTHORIZED, status=401)

    paper = Paper.query.get(paper_id)
    if not paper:
        return api_error("论文不存在", code=ErrorCode.NOT_FOUND, status=404)

    stmt = user_bookmarks.insert().values(user_id=user_id, paper_id=paper_id)
    try:
        db.session.execute(stmt)
        db.session.commit()
        return api_success(message=f"已收藏「{paper.title[:30]}…」")
    except Exception:
        db.session.rollback()
        return api_success(message="该论文已在收藏列表中")


@bookmarks_bp.route("/api/bookmarks/<int:paper_id>", methods=["DELETE"])
def remove_bookmark(paper_id):
    """取消收藏一篇论文
    ---
    tags:
      - 收藏
    parameters:
      - in: path
        name: paper_id
        type: integer
        required: true
        description: 论文 ID
    responses:
      200:
        description: 操作结果
    """
    user_id = _get_user_id()
    if not user_id:
        return api_error("请先登录", code=ErrorCode.UNAUTHORIZED, status=401)

    stmt = user_bookmarks.delete().where(
        user_bookmarks.c.user_id == user_id,
        user_bookmarks.c.paper_id == paper_id,
    )
    result = db.session.execute(stmt)
    db.session.commit()
    return api_success(message="已取消收藏" if result.rowcount else "未找到该收藏")
