"""
报告蓝图：综合报告页、统计 API、PDF/CSV/JSON 导出。
"""

import io
import csv
import json
import logging
from datetime import datetime

from flask import Blueprint, render_template, request, jsonify, send_file
from models import db, Paper, Innovation
from routes.helpers import get_filtered_papers, get_report_generator
from utils.response import api_success, api_error, ErrorCode

logger = logging.getLogger("InnoCite")

report_bp = Blueprint("report", __name__)


@report_bp.route("/report")
def report_page():
    """综合报告页"""
    return render_template("report.html")


@report_bp.route("/about")
def about():
    """关于页面"""
    return render_template("about.html")


@report_bp.route("/timeline")
def timeline():
    """创新点时间线视图"""
    innovations = (
        Innovation.query.join(Paper)
        .filter(Innovation.problem != "待补充")
        .order_by(Paper.year.desc())
        .all()
    )
    timeline_data = []
    for inv in innovations:
        if inv.paper and inv.paper.year:
            timeline_data.append({
                "id": inv.id,
                "paper_id": inv.paper_id,
                "title": inv.paper.title,
                "year": inv.paper.year,
                "category": inv.paper.category,
                "problem": inv.problem if inv.problem != "待补充" else "",
                "method": inv.method if inv.method != "待补充" else "",
                "effect": inv.effect if inv.effect != "待补充" else "",
                "confidence": inv.confidence,
            })
    return render_template("timeline.html", innovations=timeline_data)


# ═══════════════════════════════════════════
# 统计 API
# ═══════════════════════════════════════════

# 统计 API 的内存缓存（30 秒 TTL，避免每次请求都执行 4 次 DB 查询）
_stats_cache = {"data": None, "timestamp": 0}
_STATS_CACHE_TTL = 30  # 秒


@report_bp.route("/api/stats")
def api_stats():
    """获取数据库统计摘要（合并查询以减少数据库往返）
    ---
    tags:
      - 统计
    responses:
      200:
        description: 统计数据
    """
    # ── 内存缓存（30s TTL，首页/报告页频繁调用时避免重复 DB 查询）──
    import time as _time
    _now = _time.time()
    if _stats_cache["data"] is not None and (_now - _stats_cache["timestamp"]) < _STATS_CACHE_TTL:
        return api_success(data=_stats_cache["data"])

    # 查询 1：论文状态统计 — 一次扫描拿两个 COUNT
    paper_stats = db.session.query(
        db.func.count().label("total"),
        db.func.sum(db.case((Paper.status == "success", 1), else_=0)).label("success"),
        db.func.sum(db.case((Paper.status == "failed", 1), else_=0)).label("failed"),
    ).first()
    paper_count = paper_stats.success or 0
    failed_count = paper_stats.failed or 0

    # 查询 2：创新点统计 — 一次扫描拿总数、已确认数、平均置信度
    inno_stats = db.session.query(
        db.func.count().label("total"),
        db.func.sum(db.case((Innovation.is_verified == True, 1), else_=0)).label("verified"),
        db.func.avg(Innovation.confidence).label("avg_conf"),
    ).first()
    innovation_count = inno_stats.total or 0
    verified_count = inno_stats.verified or 0
    avg_confidence = float(inno_stats.avg_conf or 0)

    # 查询 3：年份分布
    years = [
        r[0] for r in db.session.query(Paper.year)
        .filter(Paper.year.isnot(None)).distinct().order_by(Paper.year).all()
    ]

    # 查询 4：学科 + 来源分布 — 各自 GROUP BY，各自一次扫描
    categories = dict(
        db.session.query(Paper.category, db.func.count(Paper.id))
        .filter(Paper.category.isnot(None))
        .group_by(Paper.category).all()
    )
    source_types = dict(
        db.session.query(Paper.source_type, db.func.count(Paper.id))
        .group_by(Paper.source_type).all()
    )

    result = {
        "paper_count": paper_count,
        "failed_count": failed_count,
        "innovation_count": innovation_count,
        "verified_count": verified_count,
        "years": sorted(years),
        "year_range": f"{min(years)} - {max(years)}" if years else "N/A",
        "categories": categories,
        "source_types": source_types,
        "avg_confidence": round(avg_confidence, 2),
    }
    _stats_cache["data"] = result
    _stats_cache["timestamp"] = _now
    return api_success(data=result)


# ═══════════════════════════════════════════
# 导出 API
# ═══════════════════════════════════════════

@report_bp.route("/api/export_pdf", methods=["POST"])
def export_pdf():
    """生成并下载 PDF 综合报告
    ---
    tags:
      - 报告
    produces:
      - application/pdf
    responses:
      200:
        description: PDF 文件下载
    """
    try:
        generator = get_report_generator()
        buffer = generator.generate()

        return send_file(
            buffer,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"InnoCite_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
        )
    except Exception as e:
        return api_error(
            f"PDF生成失败: {str(e)}",
            code=ErrorCode.INTERNAL_ERROR, status=500,
        )


@report_bp.route("/api/export/csv")
def export_csv():
    """导出论文数据为 CSV 文件（含创新点）
    ---
    tags:
      - 报告
    parameters:
      - in: query
        name: q
        type: string
        description: 搜索关键词
      - in: query
        name: category
        type: string
        description: 学科分类
    responses:
      200:
        description: CSV 文件下载
    """
    papers = get_filtered_papers(request.args)

    buffer = io.StringIO()
    buffer.write("﻿")  # UTF-8 BOM

    writer = csv.writer(buffer)
    writer.writerow([
        "标题", "作者", "年份", "发表场合", "学科分类", "arXiv ID",
        "来源", "问题", "方法", "效果", "完整陈述", "置信度", "已确认",
    ])

    for paper in papers:
        inv = paper.innovation
        writer.writerow([
            paper.title or "",
            paper.authors or "",
            paper.year or "",
            paper.venue or "",
            paper.category or "",
            paper.arxiv_id or "",
            paper.source_type or "",
            inv.problem if inv and inv.problem != "待补充" else "",
            inv.method if inv and inv.method != "待补充" else "",
            inv.effect if inv and inv.effect != "待补充" else "",
            inv.full_statement if inv else "",
            f"{inv.confidence:.0%}" if inv else "",
            "是" if (inv and inv.is_verified) else "否",
        ])

    buffer.seek(0)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return send_file(
        io.BytesIO(buffer.getvalue().encode("utf-8")),
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"InnoCite_Export_{timestamp}.csv",
    )


@report_bp.route("/api/export/json")
def export_json():
    """导出论文数据为 JSON 文件（含创新点完整信息）
    ---
    tags:
      - 报告
    parameters:
      - in: query
        name: q
        type: string
        description: 搜索关键词
      - in: query
        name: category
        type: string
        description: 学科分类
    responses:
      200:
        description: JSON 文件下载
    """
    papers = get_filtered_papers(request.args)

    export_data = []
    for paper in papers:
        d = paper.to_dict()
        if paper.innovation:
            d["innovation"] = paper.innovation.to_dict()
        else:
            d["innovation"] = None
        export_data.append(d)

    result = json.dumps(export_data, ensure_ascii=False, indent=2)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    return send_file(
        io.BytesIO(result.encode("utf-8")),
        mimetype="application/json",
        as_attachment=True,
        download_name=f"InnoCite_Export_{timestamp}.json",
    )


# ═══════════════════════════════════════════
# 文献综述生成 API
# ═══════════════════════════════════════════

@report_bp.route("/api/review/generate", methods=["POST"])
def api_generate_review():
    """基于论文库数据自动生成文献综述草稿
    ---
    tags:
      - 报告
    parameters:
      - in: body
        name: body
        required: true
        schema:
          properties:
            topic:
              type: string
              description: 综述主题（搜索关键词）
            max_papers:
              type: integer
              description: 最大引用篇数
    responses:
      200:
        description: Markdown 格式的综述草稿
    """
    data = request.get_json() or {}
    topic = data.get("topic", "").strip()
    max_papers = data.get("max_papers", 15)

    if not topic:
        return api_error("请指定综述主题", code=ErrorCode.VALIDATION_ERROR)

    # 搜索相关论文
    from models import Paper
    papers = (
        Paper.query
        .filter(Paper.abstract.isnot(None))
        .filter(
            db.or_(
                Paper.title.contains(topic),
                Paper.abstract.contains(topic),
            )
        )
        .order_by(Paper.year)
        .limit(max_papers)
        .all()
    )

    if not papers:
        return api_success(
            data=None,
            message=f"未找到与「{topic}」相关的论文，请尝试其他关键词",
        )

    # 组装论文数据
    papers_data = []
    for p in papers:
        pd_dict = {
            "title": p.title,
            "year": p.year,
        }
        if p.innovation:
            pd_dict["innovation"] = {
                "problem": p.innovation.problem if p.innovation.problem != "待补充" else "",
                "method": p.innovation.method if p.innovation.method != "待补充" else "",
                "effect": p.innovation.effect if p.innovation.effect != "待补充" else "",
            }
        else:
            pd_dict["abstract"] = (p.abstract or "")[:300]
        papers_data.append(pd_dict)

    # 尝试 LLM 生成
    try:
        from routes.helpers import get_llm_client
        llm = get_llm_client()
        if llm and llm.available:
            review = llm.generate_literature_review(topic, papers_data)
            if review:
                return api_success(data={
                    "topic": topic,
                    "review": review,
                    "format": "markdown",
                    "paper_count": len(papers),
                    "source": "llm",
                })
    except Exception:
        logger.warning("LLM 综述生成失败，使用模板回退", exc_info=True)

    # 模板回退
    lines = [f"## {topic} 研究概览", ""]
    lines.append(f"共找到 {len(papers)} 篇相关论文。", "")
    for i, p in enumerate(papers, 1):
        title = (p.title or "未知")[:100]
        year = p.year or "?"
        lines.append(f"{i}. **[{year}]** {title}")
        if p.innovation and p.innovation.method != "待补充":
            lines.append(f"   - 方法：{p.innovation.get_method_short(120)}")
        lines.append("")

    return api_success(data={
        "topic": topic,
        "review": "\n".join(lines),
        "format": "markdown",
        "paper_count": len(papers),
        "source": "template",
    })
