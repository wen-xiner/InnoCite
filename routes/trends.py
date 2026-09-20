"""
关键词趋势蓝图：热度计算、时序曲线、TOP 排名。
"""

import logging

from flask import Blueprint, render_template, request, jsonify
from routes.helpers import get_trend_analyzer
from utils.response import api_success, api_error

logger = logging.getLogger("InnoCite")

trends_bp = Blueprint("trends", __name__)


@trends_bp.route("/trends")
def trends():
    """关键词热度曲线页"""
    return render_template("trends.html")


@trends_bp.route("/api/keywords")
def api_keywords():
    """获取所有关键词及热度矩阵数据
    ---
    tags:
      - 关键词趋势
    responses:
      200:
        description: 关键词热度矩阵
    """
    analyzer = get_trend_analyzer()
    data = analyzer.compute_heatmap()
    return api_success(data={
        "keywords": data["keywords"],
        "years": data["years"],
        "heatmap": data["heatmap"],
        "all_keywords": data["all_keywords_list"],
    })


@trends_bp.route("/api/trend", methods=["POST"])
def api_trend():
    """获取指定关键词的热度时序数据
    ---
    tags:
      - 关键词趋势
    parameters:
      - in: body
        name: body
        required: true
        schema:
          properties:
            selected_keywords:
              type: array
              items:
                type: string
              description: 关键词列表
    responses:
      200:
        description: 时序数据数组
    """
    req_data = request.get_json() or {}
    selected_keywords = req_data.get("selected_keywords", [])

    if not selected_keywords:
        return api_success(data={"trends": []})

    analyzer = get_trend_analyzer()
    trends = analyzer.get_trend_data(selected_keywords)
    return api_success(data={"trends": trends})


@trends_bp.route("/api/top-keywords")
def api_top_keywords():
    """获取热度排名 TOP N 的关键词
    ---
    tags:
      - 关键词趋势
    parameters:
      - in: query
        name: n
        type: integer
        description: 前 N 个
    responses:
      200:
        description: 排名列表
    """
    n = request.args.get("n", 20, type=int)
    analyzer = get_trend_analyzer()
    top = analyzer.get_top_keywords(n=n)
    return api_success(data={
        "top_keywords": [{"keyword": kw, "avg_heat": heat} for kw, heat in top],
    })


@trends_bp.route("/api/trend/predict", methods=["POST"])
def api_trend_predict():
    """获取指定关键词的未来趋势预测
    ---
    tags:
      - 关键词趋势
    parameters:
      - in: body
        name: body
        required: true
        schema:
          properties:
            keyword:
              type: string
              description: 关键词
            forecast_years:
              type: integer
              description: 预测年数（默认 2）
    responses:
      200:
        description: 趋势预测结果，包含历史数据、预测值、趋势方向
    """
    req_data = request.get_json() or {}
    keyword = req_data.get("keyword", "").strip()
    forecast_years = req_data.get("forecast_years", 2)

    if not keyword:
        return api_error("请指定关键词", code="validation_error")

    analyzer = get_trend_analyzer()
    result = analyzer.predict_trend(keyword, forecast_years=forecast_years)

    if result is None:
        return api_success(data=None, message=f"关键词「{keyword}」数据不足，无法预测")

    return api_success(data=result)


# ═══════════════════════════════════════════
# 河流图 / 方法迁移 API
# ═══════════════════════════════════════════

@trends_bp.route("/api/trend/river-chart")
def api_river_chart():
    """获取关键词热度河流图数据（堆叠面积图）
    ---
    tags:
      - 关键词趋势
    parameters:
      - in: query
        name: top_n
        type: integer
        description: 展示 TOP N 关键词
    responses:
      200:
        description: 河流图数据
    """
    top_n = request.args.get("top_n", 6, type=int)
    analyzer = get_trend_analyzer()
    result = analyzer.compute_river_chart(top_n=top_n)
    return api_success(data=result)


@trends_bp.route("/api/trend/migration", methods=["GET"])
def api_method_migration():
    """追踪研究方法跨学科迁移路径
    ---
    tags:
      - 关键词趋势
    parameters:
      - in: query
        name: keyword
        type: string
        required: true
        description: 方法关键词
      - in: query
        name: min_year
        type: integer
        description: 最早年份
    responses:
      200:
        description: 迁移路径数据
    """
    keyword = request.args.get("keyword", "").strip()
    if not keyword:
        return api_error("请指定方法关键词", code="validation_error")

    min_year = request.args.get("min_year", 2015, type=int)
    analyzer = get_trend_analyzer()
    result = analyzer.trace_method_migration(keyword, min_year=min_year)
    return api_success(data=result)
