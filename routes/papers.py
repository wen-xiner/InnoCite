"""
论文管理蓝图：首页列表、论文导入、查看详情、删除、CSV模板、重新处理。
"""

import os
import logging
from utils.task_queue import executor, batch_extract_async
from utils.response import api_success, api_error, ErrorCode
from datetime import datetime

from flask import Blueprint, render_template, request, jsonify, send_file

from models import db, Paper, Innovation
from routes.helpers import (
    parser, extract_innovation_for_paper, get_filtered_papers,
)

logger = logging.getLogger("InnoCite")

papers_bp = Blueprint("papers", __name__)


# ═══════════════════════════════════════════
# 页面路由
# ═══════════════════════════════════════════

@papers_bp.route("/")
def index():
    """首页 - 论文管理与导入"""
    query = request.args.get("q", "")
    category_filter = request.args.get("category", "")
    page = request.args.get("page", 1, type=int)
    per_page = 20

    papers_query = Paper.query

    if query:
        papers_query = papers_query.filter(
            db.or_(
                Paper.title.contains(query),
                Paper.abstract.contains(query),
                Paper.authors.contains(query),
            )
        )

    if category_filter:
        papers_query = papers_query.filter(Paper.category == category_filter)

    papers_query = papers_query.order_by(Paper.created_at.desc())

    total = papers_query.count()
    papers = papers_query.offset((page - 1) * per_page).limit(per_page).all()

    categories = [
        r[0] for r in db.session.query(Paper.category).distinct().all()
        if r[0]
    ]

    return render_template(
        "index.html",
        papers=papers,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=(total + per_page - 1) // per_page,
        query=query,
        category_filter=category_filter,
        categories=sorted(categories),
        current_year=datetime.now().year,
    )


@papers_bp.route("/papers/<int:paper_id>")
def paper_detail(paper_id):
    """论文详情页"""
    paper = Paper.query.get_or_404(paper_id)
    innovation = paper.innovation
    return render_template("paper_detail.html", paper=paper, innovation=innovation)


# ═══════════════════════════════════════════
# 论文导入 API
# ═══════════════════════════════════════════

@papers_bp.route("/import/arxiv-id", methods=["POST"])
def import_arxiv_id():
    """通过arXiv ID导入单篇论文
    ---
    tags:
      - 论文导入
    parameters:
      - in: body
        name: body
        required: true
        schema:
          properties:
            arxiv_id:
              type: string
              description: arXiv 论文 ID（如 2101.00123）
    responses:
      200:
        description: 导入结果
    """
    data = request.get_json() or {}
    arxiv_id = data.get("arxiv_id", "").strip()

    if not arxiv_id:
        return api_error("请输入 arXiv ID", code=ErrorCode.VALIDATION_ERROR)

    success, message, paper = parser.import_arxiv_by_id(arxiv_id)

    if success and paper:
        # 创新点提取移至后台线程，不阻塞 API 响应
        from utils.task_queue import extract_innovation_async
        executor.submit(extract_innovation_async, paper)

    return api_success(
        data=paper.to_dict() if paper else None,
        message=message,
    )


@papers_bp.route("/import/arxiv-search", methods=["POST"])
def import_arxiv_search():
    """通过关键词搜索arXiv导入论文
    ---
    tags:
      - 论文导入
    parameters:
      - in: body
        name: body
        required: true
        schema:
          properties:
            query:
              type: string
              description: 搜索关键词
            max_results:
              type: integer
              description: 最大导入篇数
            year_from:
              type: integer
              description: 起始年份
            year_to:
              type: integer
              description: 结束年份
    responses:
      200:
        description: 导入结果
    """
    data = request.get_json() or {}
    query = data.get("query", "").strip()
    max_results = min(data.get("max_results", 20), 100)
    year_from = data.get("year_from")
    year_to = data.get("year_to")

    if not query:
        return api_error("请输入搜索关键词", code=ErrorCode.VALIDATION_ERROR)

    if year_from:
        year_from = int(year_from)
    if year_to:
        year_to = int(year_to)

    success, message, imported_count, papers = parser.search_arxiv(
        query, max_results=max_results,
        year_from=year_from, year_to=year_to,
    )

    if success:
        # 创新点提取移至后台线程池，批量提交不阻塞 API 响应
        batch_extract_async(papers)

    return api_success(
        message=message,
        imported_count=imported_count,
    )


@papers_bp.route("/import/csv", methods=["POST"])
def import_csv():
    """上传CSV文件批量导入论文
    ---
    tags:
      - 论文导入
    consumes:
      - multipart/form-data
    parameters:
      - in: formData
        name: file
        type: file
        required: true
        description: CSV 文件
    responses:
      200:
        description: 导入结果
    """
    from flask import current_app
    from utils import validate_file_type, sanitize_upload_filename

    if "file" not in request.files:
        return api_error("请选择CSV文件", code=ErrorCode.VALIDATION_ERROR)

    file = request.files["file"]
    if file.filename == "" or not file.filename.lower().endswith(".csv"):
        return api_error("请上传有效的CSV文件", code=ErrorCode.VALIDATION_ERROR)

    is_valid, err_msg = validate_file_type(file, "csv")
    if not is_valid:
        return api_error(err_msg, code=ErrorCode.FILE_TYPE_ERROR)

    safe_name = sanitize_upload_filename(file.filename)
    if not safe_name.lower().endswith(".csv"):
        safe_name += ".csv"

    upload_folder = current_app.config["UPLOAD_FOLDER"]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filepath = os.path.join(upload_folder, f"csv_{timestamp}_{safe_name}")
    file.save(filepath)

    success, message, imported_count = parser.import_csv(filepath)

    try:
        os.remove(filepath)
    except Exception:
        logger.warning("清理CSV临时文件失败: %s", filepath, exc_info=True)

    if success:
        # 创新点提取移至后台线程池
        papers_without_innovation = Paper.query.outerjoin(
            Innovation, Paper.id == Innovation.paper_id
        ).filter(Innovation.id == None).all()
        batch_extract_async(papers_without_innovation)

    return api_success(message=message, imported_count=imported_count)


@papers_bp.route("/import/pdf", methods=["POST"])
def import_pdf():
    """上传PDF文件解析导入论文
    ---
    tags:
      - 论文导入
    consumes:
      - multipart/form-data
    parameters:
      - in: formData
        name: file
        type: file
        required: true
        description: PDF 论文文件
    responses:
      200:
        description: 解析结果
    """
    from flask import current_app
    from utils import validate_file_type, sanitize_upload_filename

    if "file" not in request.files:
        return api_error("请选择PDF文件", code=ErrorCode.VALIDATION_ERROR)

    file = request.files["file"]
    if file.filename == "" or not file.filename.lower().endswith(".pdf"):
        return api_error("请上传有效的PDF文件", code=ErrorCode.VALIDATION_ERROR)

    is_valid, err_msg = validate_file_type(file, "pdf")
    if not is_valid:
        return api_error(err_msg, code=ErrorCode.FILE_TYPE_ERROR)

    safe_name = sanitize_upload_filename(file.filename)
    if not safe_name.lower().endswith(".pdf"):
        safe_name += ".pdf"

    upload_folder = current_app.config["UPLOAD_FOLDER"]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filepath = os.path.join(upload_folder, f"pdf_{timestamp}_{safe_name}")
    file.save(filepath)

    success, message, paper = parser.import_pdf(filepath)

    try:
        os.remove(filepath)
    except Exception:
        logger.warning("清理PDF临时文件失败: %s", filepath, exc_info=True)

    if success and paper:
        from utils.task_queue import extract_innovation_async
        executor.submit(extract_innovation_async, paper)

    return api_success(
        data=paper.to_dict() if paper else None,
        message=message,
    )


@papers_bp.route("/import/enw", methods=["POST"])
def import_enw():
    """上传EndNote (.enw) 文件批量导入论文（知网/万方导出格式兼容）
    ---
    tags:
      - 论文导入
    consumes:
      - multipart/form-data
    parameters:
      - in: formData
        name: file
        type: file
        required: true
        description: EndNote (.enw) 文件
    responses:
      200:
        description: 导入结果，包含 imported_count
    """
    from flask import current_app
    from utils import sanitize_upload_filename

    if "file" not in request.files:
        return api_error("请选择 .enw 文件", code=ErrorCode.VALIDATION_ERROR)

    file = request.files["file"]
    if file.filename == "":
        return api_error("请选择 .enw 文件", code=ErrorCode.VALIDATION_ERROR)
    if not file.filename.lower().endswith((".enw", ".txt", ".endnote", ".ris")):
        return api_error("请上传 .enw / .txt 格式的 EndNote 文件", code=ErrorCode.VALIDATION_ERROR)

    safe_name = sanitize_upload_filename(file.filename)
    upload_folder = current_app.config["UPLOAD_FOLDER"]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filepath = os.path.join(upload_folder, f"enw_{timestamp}_{safe_name}")
    file.save(filepath)

    success, message, imported_count = parser.import_enw(filepath)

    try:
        os.remove(filepath)
    except Exception:
        logger.warning("清理ENW临时文件失败: %s", filepath, exc_info=True)

    if success:
        # 创新点提取移至后台线程池
        from models import Paper, Innovation
        papers_without_innovation = Paper.query.outerjoin(
            Innovation, Paper.id == Innovation.paper_id
        ).filter(Innovation.id == None).all()
        batch_extract_async(papers_without_innovation)

    return api_success(message=message, imported_count=imported_count)


@papers_bp.route("/import/bibtex", methods=["POST"])
def import_bibtex():
    """上传 BibTeX (.bib) 文件批量导入论文（Google Scholar / DBLP / ACM 导出）
    ---
    tags:
      - 论文导入
    consumes:
      - multipart/form-data
    parameters:
      - in: formData
        name: file
        type: file
        required: true
        description: BibTeX (.bib) 文件
    responses:
      200:
        description: 导入结果，包含 imported_count
    """
    from flask import current_app
    from utils import sanitize_upload_filename

    if "file" not in request.files:
        return api_error("请选择 .bib 文件", code=ErrorCode.VALIDATION_ERROR)

    file = request.files["file"]
    if file.filename == "":
        return api_error("请选择 .bib 文件", code=ErrorCode.VALIDATION_ERROR)
    if not file.filename.lower().endswith(".bib"):
        return api_error("请上传 .bib 格式的 BibTeX 文件", code=ErrorCode.VALIDATION_ERROR)

    safe_name = sanitize_upload_filename(file.filename)
    upload_folder = current_app.config["UPLOAD_FOLDER"]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filepath = os.path.join(upload_folder, f"bib_{timestamp}_{safe_name}")
    file.save(filepath)

    success, message, imported_count = parser.import_bibtex(filepath)

    try:
        os.remove(filepath)
    except Exception:
        logger.warning("清理BibTeX临时文件失败: %s", filepath, exc_info=True)

    if success:
        from models import Paper, Innovation
        papers_without_innovation = Paper.query.outerjoin(
            Innovation, Paper.id == Innovation.paper_id
        ).filter(Innovation.id == None).all()
        batch_extract_async(papers_without_innovation)

    return api_success(message=message, imported_count=imported_count)


@papers_bp.route("/api/csv-template")
def csv_template():
    """下载CSV导入模板文件
    ---
    tags:
      - 论文导入
    responses:
      200:
        description: CSV 模板文件
    """
    content = parser.get_csv_template()
    return content, 200, {
        "Content-Type": "text/csv",
        "Content-Disposition": "attachment; filename=paper_template.csv",
    }


@papers_bp.route("/api/reprocess/<int:paper_id>", methods=["POST"])
def reprocess_paper(paper_id):
    """重新处理失败的论文（手动补全元数据）
    ---
    tags:
      - 论文导入
    parameters:
      - in: path
        name: paper_id
        type: integer
        required: true
        description: 论文 ID
    """
    data = request.get_json() or {}
    manual_data = data.get("manual_data")
    success, message = parser.reprocess_failed_paper(paper_id, manual_data)
    return api_success(message=message)


@papers_bp.route("/papers/<int:paper_id>/delete", methods=["POST"])
def delete_paper(paper_id):
    """删除指定论文及其关联数据
    ---
    tags:
      - 论文导入
    parameters:
      - in: path
        name: paper_id
        type: integer
        required: true
        description: 论文 ID
    responses:
      200:
        description: 删除结果
    """
    paper = Paper.query.get(paper_id)
    if not paper:
        return api_error("论文不存在", code=ErrorCode.NOT_FOUND, status=404)

    title_snippet = (paper.title or "未知")[:60]

    try:
        from models import Recommendation, PaperEmbedding, KeywordCache

        # 1. 清理关联推荐记录
        Recommendation.query.filter(
            db.or_(
                Recommendation.source_paper_id == paper_id,
                Recommendation.target_paper_id == paper_id,
            )
        ).delete(synchronize_session="fetch")

        # 2. 清理向量嵌入（防御性：虽有 cascade 但 LargeBinary 需显式处理）
        PaperEmbedding.query.filter_by(paper_id=paper_id).delete()

        # 3. 删除论文（级联删除 Innovation）
        db.session.delete(paper)

        # 4. 失效关键词缓存
        KeywordCache.query.filter_by(cache_key="heatmap").delete()

        db.session.commit()

        return api_success(message=f"已删除: {title_snippet}")
    except Exception as e:
        db.session.rollback()
        return api_error(
            f"删除失败: {str(e)}",
            code=ErrorCode.INTERNAL_ERROR, status=500
        )


# ═══════════════════════════════════════════
# 批量操作 API
# ═══════════════════════════════════════════

@papers_bp.route("/api/papers/batch", methods=["POST"])
def batch_operation():
    """批量操作论文
    ---
    tags:
      - 论文导入
    parameters:
      - in: body
        name: body
        required: true
        schema:
          properties:
            paper_ids:
              type: array
              items:
                type: integer
            action:
              type: string
              enum: [delete, re-extract, set-category]
            category:
              type: string
              description: 当 action=set-category 时的新学科
    responses:
      200:
        description: 操作结果
    """
    data = request.get_json() or {}
    paper_ids = data.get("paper_ids", [])
    action = data.get("action", "")

    if not paper_ids or not action:
        return api_error("请选择论文并指定操作", code=ErrorCode.VALIDATION_ERROR)

    valid_ids = []
    for pid in paper_ids:
        try:
            valid_ids.append(int(pid))
        except (ValueError, TypeError):
            pass

    if not valid_ids:
        return api_error("无效的论文 ID", code=ErrorCode.VALIDATION_ERROR)

    papers = Paper.query.filter(Paper.id.in_(valid_ids)).all()
    if not papers:
        return api_error("未找到指定的论文", code=ErrorCode.NOT_FOUND, status=404)

    try:
        if action == "delete":
            from models import Recommendation, PaperEmbedding, KeywordCache, Innovation
            for paper in papers:
                Recommendation.query.filter(
                    db.or_(
                        Recommendation.source_paper_id == paper.id,
                        Recommendation.target_paper_id == paper.id,
                    )
                ).delete(synchronize_session="fetch")
                PaperEmbedding.query.filter_by(paper_id=paper.id).delete()
                db.session.delete(paper)
            KeywordCache.query.filter_by(cache_key="heatmap").delete()
            db.session.commit()
            return api_success(
                message=f"已批量删除 {len(papers)} 篇论文",
                count=len(papers),
            )

        elif action == "re-extract":
            from routes.helpers import extract_innovation_for_paper
            from utils.task_queue import batch_extract_async
            batch_extract_async(papers)
            return api_success(
                message=f"已提交 {len(papers)} 篇论文的创新点后台提取",
                count=len(papers),
            )

        elif action == "set-category":
            category = (data.get("category") or "").strip()
            if not category:
                return api_error("请指定目标学科", code=ErrorCode.VALIDATION_ERROR)
            for paper in papers:
                paper.category = category
            db.session.commit()
            return api_success(
                message=f"已将 {len(papers)} 篇论文设为 {category}",
                count=len(papers),
            )

        else:
            return api_error(f"不支持的操作: {action}", code=ErrorCode.VALIDATION_ERROR)

    except Exception as e:
        db.session.rollback()
        return api_error(
            f"批量操作失败: {str(e)}",
            code=ErrorCode.INTERNAL_ERROR, status=500,
        )
