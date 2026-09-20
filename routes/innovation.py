"""
创新点蓝图：提取、查看、编辑、汇总。
"""

import logging
from datetime import datetime, timezone

from flask import Blueprint, request, jsonify
from models import db, Paper, Innovation
from routes.helpers import extractor, extract_innovation_for_paper
from utils.response import api_success, api_error, api_paginated, ErrorCode

logger = logging.getLogger("InnoCite")

innovation_bp = Blueprint("innovation", __name__)


@innovation_bp.route("/papers/<int:paper_id>/innovation", methods=["GET"])
def get_innovation(paper_id):
    """获取论文的创新点（不存在则自动提取）
    ---
    tags:
      - 创新点
    parameters:
      - in: path
        name: paper_id
        type: integer
        required: true
        description: 论文 ID
    responses:
      200:
        description: 创新点对象
    """
    paper = Paper.query.get_or_404(paper_id)
    innovation = paper.innovation

    if not innovation:
        extract_innovation_for_paper(paper)
        db.session.commit()
        innovation = paper.innovation

    return jsonify(innovation.to_dict() if innovation else {})


@innovation_bp.route("/papers/<int:paper_id>/innovation", methods=["POST"])
def save_innovation(paper_id):
    """保存/编辑论文的创新点
    ---
    tags:
      - 创新点
    parameters:
      - in: path
        name: paper_id
        type: integer
        required: true
        description: 论文 ID
      - in: body
        name: body
        required: true
        schema:
          properties:
            problem:
              type: string
            method:
              type: string
            effect:
              type: string
            is_verified:
              type: boolean
    responses:
      200:
        description: 保存结果
    """
    paper = Paper.query.get_or_404(paper_id)
    data = request.get_json() or {}

    innovation = paper.innovation
    if not innovation:
        innovation = Innovation(paper_id=paper.id)
        db.session.add(innovation)

    innovation.problem = data.get("problem", innovation.problem)
    innovation.method = data.get("method", innovation.method)
    innovation.effect = data.get("effect", innovation.effect)
    innovation.is_verified = data.get("is_verified", True)
    innovation.updated_at = datetime.now(timezone.utc)

    if not innovation.is_verified:
        innovation.confidence = extractor.calculate_confidence(
            innovation.problem, innovation.method, innovation.effect
        )

    innovation.build_full_statement()
    db.session.commit()

    return api_success(data=innovation.to_dict(), message="创新点已保存")


@innovation_bp.route("/api/innovations")
def api_innovations():
    """分页获取创新点汇总列表
    ---
    tags:
      - 创新点
    parameters:
      - in: query
        name: page
        type: integer
        description: 页码
      - in: query
        name: per_page
        type: integer
        description: 每页条数
    responses:
      200:
        description: 分页创新点列表
    """
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)

    query = Innovation.query.join(Paper).order_by(
        Paper.year.desc(), Innovation.confidence.desc()
    )
    total = query.count()
    innovations = query.offset((page - 1) * per_page).limit(per_page).all()

    items = [
            {
                **inv.to_dict(),
                "paper_title": inv.paper.title if inv.paper else "",
                "paper_year": inv.paper.year if inv.paper else None,
                "paper_category": inv.paper.category if inv.paper else "",
            }
            for inv in innovations
        ]

    return api_paginated(items, page, per_page, total)
