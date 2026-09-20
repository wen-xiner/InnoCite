"""
路由共享辅助函数。
提供各蓝图共用的服务实例和工具函数。
"""

import logging
from models import db, Paper, Innovation, PaperEmbedding, Recommendation
from paper_parser import PaperParser
from innovation_extractor import InnovationExtractor
from keyword_trend import KeywordTrendAnalyzer
from recommender import Recommender
from report_generator import ReportGenerator
from llm_client import get_llm_client as _get_llm_client

logger = logging.getLogger("InnoCite")

# 无状态服务（可在模块级实例化）
parser = PaperParser()
extractor = InnovationExtractor()  # 不传 config，自动从环境变量读取

# 需要 db session 的服务（延迟初始化）
_trend_analyzer = None
_recommender = None
_report_generator = None


def get_trend_analyzer():
    """延迟初始化关键词趋势分析器"""
    global _trend_analyzer
    if _trend_analyzer is None:
        _trend_analyzer = KeywordTrendAnalyzer(db)
    return _trend_analyzer


def get_recommender():
    """获取推荐器实例"""
    global _recommender
    if _recommender is None:
        _recommender = Recommender(db)
    return _recommender


def get_report_generator():
    """获取报告生成器实例"""
    global _report_generator
    if _report_generator is None:
        _report_generator = ReportGenerator(db)
    return _report_generator


def get_llm_client():
    """获取 LLM 客户端实例。

    委托 llm_client 模块级单例（共用同一全局缓存），配置自动从当前应用上下文读取。
    收敛前此处有独立缓存变量，导致 reset_llm_client() 只能重置一半（测试隔离缺陷）。
    """
    return _get_llm_client()


def extract_innovation_for_paper(paper):
    """为单篇论文提取并保存创新点（公共函数）。
    如果论文已有创新点则跳过，提取成功返回 True，失败返回 False。
    """
    if paper.innovation:
        return False
    if not paper.abstract:
        return False
    try:
        result = extractor.extract(paper)
        innovation = Innovation(
            paper_id=paper.id,
            problem=result["problem"],
            method=result["method"],
            effect=result["effect"],
            confidence=result["confidence"],
        )
        innovation.build_full_statement()
        db.session.add(innovation)
        return True
    except Exception:
        logger.warning("论文 %d 创新点提取失败", paper.id, exc_info=True)
        return False


def get_filtered_papers(request_args):
    """根据请求参数筛选论文的辅助函数。
    参数:
        request_args: Flask request.args 或类似字典
    返回:
        list of Paper
    """
    query = request_args.get("q", "").strip() if hasattr(request_args, 'get') else ""
    category_filter = request_args.get("category", "").strip() if hasattr(request_args, 'get') else ""

    papers_query = Paper.query.filter_by(status="success")

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

    return papers_query.order_by(Paper.created_at.desc()).all()
