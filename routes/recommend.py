"""
跨学科推荐蓝图：基于向量相似度的跨学科论文推荐。
"""

import logging

from flask import Blueprint, render_template, request, jsonify
from models import db, Paper, Recommendation
from routes.helpers import get_recommender
from utils.response import api_success, api_error, ErrorCode

logger = logging.getLogger("InnoCite")

recommend_bp = Blueprint("recommend", __name__)


@recommend_bp.route("/recommend")
def recommend_page():
    """跨学科推荐页"""
    papers = Paper.query.order_by(Paper.title).all()
    return render_template("recommend.html", papers=papers)


@recommend_bp.route("/api/recommend")
def api_recommend():
    """获取指定论文的跨学科推荐
    ---
    tags:
      - 跨学科推荐
    parameters:
      - in: query
        name: paper_id
        type: integer
        required: true
        description: 源论文 ID
      - in: query
        name: top_n
        type: integer
        description: 推荐条数
      - in: query
        name: force_refresh
        type: string
        description: 设为 "1" 强制重新计算
    responses:
      200:
        description: 推荐结果
    """
    paper_id = request.args.get("paper_id", type=int)
    top_n = request.args.get("top_n", 3, type=int)
    force = request.args.get("force_refresh", "0") == "1"

    if not paper_id:
        return api_error("请指定 paper_id", code=ErrorCode.VALIDATION_ERROR)

    paper = Paper.query.get(paper_id)
    if not paper:
        return api_error("论文不存在", code=ErrorCode.NOT_FOUND, status=404)

    recommender = get_recommender()
    results = recommender.recommend(paper_id, top_n=top_n, force_refresh=force)

    return api_success(data={
        "source_paper": paper.to_dict(),
        "recommendations": results,
    })


@recommend_bp.route("/api/recommend-sample")
def api_recommend_sample():
    """自动选择最优论文生成推荐示例（报告页专用）
    ---
    tags:
      - 跨学科推荐
    parameters:
      - in: query
        name: top_n
        type: integer
        description: 推荐条数
    responses:
      200:
        description: 自动选择的推荐结果
    """
    top_n = request.args.get("top_n", 3, type=int)

    source_paper = None

    # 策略1：有缓存推荐的论文
    cached = (
        db.session.query(Recommendation.source_paper_id)
        .group_by(Recommendation.source_paper_id)
        .order_by(db.func.count(Recommendation.id).desc())
        .first()
    )
    if cached:
        source_paper = Paper.query.get(cached.source_paper_id)

    # 策略2：有创新点且有摘要的论文
    if not source_paper:
        from models import Innovation
        source_paper = (
            Paper.query.join(Innovation)
            .filter(Paper.abstract.isnot(None))
            .order_by(Innovation.confidence.desc())
            .first()
        )

    # 策略3：任意有摘要的论文
    if not source_paper:
        source_paper = Paper.query.filter(Paper.abstract.isnot(None)).first()

    if not source_paper:
        return api_error(
            "数据库中没有可用的论文，请先导入论文",
            code=ErrorCode.NOT_FOUND, status=404,
        )

    recommender = get_recommender()
    results = recommender.recommend(source_paper.id, top_n=top_n)

    return api_success(data={
        "source_paper": source_paper.to_dict(),
        "recommendations": results,
    })
