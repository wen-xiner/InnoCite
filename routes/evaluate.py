"""
模型评估蓝图：提供创新点提取、关键词提取、分类准确率的量化评估 API 和页面。
"""

import logging

from flask import Blueprint, render_template, request, jsonify
from models import db
from evaluator import Evaluator
from utils.response import api_success, api_error

logger = logging.getLogger("InnoCite")

evaluate_bp = Blueprint("evaluate", __name__, url_prefix="/evaluate")


def _get_evaluator():
    """获取评估器实例"""
    return Evaluator(db)


@evaluate_bp.route("/")
def evaluate_page():
    """模型评估页面"""
    return render_template("evaluate.html")


@evaluate_bp.route("/api/innovation", methods=["GET"])
def api_evaluate_innovation():
    """评估创新点提取质量
    ---
    tags:
      - 模型评估
    responses:
      200:
        description: 创新点评估结果
    """
    try:
        evaluator = _get_evaluator()
        result = evaluator.evaluate_innovation()
        return api_success(data=result)
    except Exception as e:
        logger.exception("创新点评估失败")
        return api_error(str(e), code="eval_error", status=500)


@evaluate_bp.route("/api/keywords", methods=["GET"])
def api_evaluate_keywords():
    """评估关键词提取质量
    ---
    tags:
      - 模型评估
    parameters:
      - in: query
        name: top_k
        type: integer
        description: Top-K 参数
    responses:
      200:
        description: 关键词评估结果
    """
    try:
        top_k = request.args.get("top_k", 5, type=int)
        evaluator = _get_evaluator()
        result = evaluator.evaluate_keywords(top_k=top_k)
        return api_success(data=result)
    except Exception as e:
        logger.exception("关键词评估失败")
        return api_error(str(e), code="eval_error", status=500)


@evaluate_bp.route("/api/classification", methods=["GET"])
def api_evaluate_classification():
    """评估论文分类准确率
    ---
    tags:
      - 模型评估
    responses:
      200:
        description: 分类评估结果
    """
    try:
        evaluator = _get_evaluator()
        result = evaluator.evaluate_classification()
        return api_success(data=result)
    except Exception as e:
        logger.exception("分类评估失败")
        return api_error(str(e), code="eval_error", status=500)


@evaluate_bp.route("/api/report", methods=["GET"])
def api_evaluate_report():
    """获取完整评估报告
    ---
    tags:
      - 模型评估
    responses:
      200:
        description: 完整评估报告
    """
    try:
        evaluator = _get_evaluator()
        from routes.helpers import extractor
        result = evaluator.full_report(extractor=extractor)
        return api_success(data=result)
    except Exception as e:
        logger.exception("评估报告生成失败")
        return api_error(str(e), code="eval_error", status=500)


@evaluate_bp.route("/api/ground-truth", methods=["GET"])
def api_ground_truth_summary():
    """获取标注数据概览
    ---
    tags:
      - 模型评估
    responses:
      200:
        description: 标注数据统计
    """
    try:
        evaluator = _get_evaluator()
        papers = evaluator.ground_truth.get("papers", [])
        categories = set()
        for p in papers:
            if p.get("category"):
                categories.add(p["category"])
        return jsonify({
            "success": True,
            "total_papers": len(papers),
            "categories": sorted(categories),
            "version": evaluator.ground_truth.get("version", "unknown"),
        })
    except Exception as e:
        return api_error(str(e), code="eval_error", status=500)
