"""
数据库初始化脚本：创建所有表并填充示例数据。
运行方式：python init_db.py
"""

import json
import datetime
import os
import sys
import logging
from logging.handlers import RotatingFileHandler

# 确保项目根目录在路径中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils import BASE_DIR

# 设置日志（同时输出到控制台和文件，文件滚动归档）
log_dir = os.path.join(BASE_DIR, "instance")
os.makedirs(log_dir, exist_ok=True)

fmt = logging.Formatter("[%(asctime)s] %(levelname)s %(message)s", datefmt="%H:%M:%S")

stream_handler = logging.StreamHandler()
stream_handler.setFormatter(fmt)

file_handler = RotatingFileHandler(
    os.path.join(log_dir, "innocite.log"),
    maxBytes=10 * 1024 * 1024,  # 10MB
    backupCount=10,
    encoding="utf-8",
)
file_handler.setFormatter(fmt)

logging.basicConfig(level=logging.INFO, handlers=[stream_handler, file_handler])
logger = logging.getLogger("InnoCite.InitDB")

from app import create_app
from models import db, Paper, Innovation, PaperEmbedding, Recommendation, User
from innovation_extractor import InnovationExtractor
from recommender import Recommender
from config import get_config


# ──────────────────────────────────────────
# 20篇示例论文数据（3个学科，2018-2024）— 演示用合成数据
# 数据来源: data/sample_papers.json（全部为自创标题/作者/指标，无真实论文引用）
# ──────────────────────────────────────────
import json as _json

def _load_json(name):
    _p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", name)
    with open(_p, "r", encoding="utf-8") as _f:
        return _json.load(_f)

SAMPLE_PAPERS = _load_json("sample_papers.json")


# ──────────────────────────────────────────
# 预置创新点（为前3篇论文）— 演示用合成数据
# ──────────────────────────────────────────
PRESET_INNOVATIONS = _load_json("preset_innovations.json")


def create_sample_data():
    """创建示例数据并填充到数据库（幂等：按 arxiv_id 跳过已存在论文）。"""
    logger.info("正在创建示例论文数据...")

    # 已存在的示例论文 arxiv_id（幂等去重，重复运行不会制造重复数据）
    existing_ids = set(
        arxiv_id
        for (arxiv_id,) in db.session.query(Paper.arxiv_id)
        .filter(Paper.arxiv_id.isnot(None)).all()
    )

    created = 0
    skipped = 0
    for paper_data in SAMPLE_PAPERS:
        if paper_data["arxiv_id"] in existing_ids:
            skipped += 1
            continue
        paper = Paper(
            arxiv_id=paper_data["arxiv_id"],
            title=paper_data["title"],
            authors=paper_data["authors"],
            year=paper_data["year"],
            venue=paper_data["venue"],
            abstract=paper_data["abstract"],
            full_text=paper_data.get("full_text"),
            category=paper_data["category"],
            source_type=paper_data["source_type"],
            status=paper_data["status"],
        )
        db.session.add(paper)
        existing_ids.add(paper_data["arxiv_id"])  # 防同批内重复
        created += 1
        logger.info("添加: %s... [%s]", paper_data['title'][:50], paper_data['category'])

    db.session.commit()
    if created:
        logger.info("已添加 %d 篇示例论文", created)
    if skipped:
        logger.info("跳过 %d 篇已存在的示例论文（幂等去重）", skipped)


def create_preset_innovations():
    """创建预置创新点"""
    logger.info("正在设置预置创新点...")

    extractor = InnovationExtractor()

    for preset in PRESET_INNOVATIONS:
        paper = Paper.query.filter_by(arxiv_id=preset["paper_arxiv_id"]).first()
        if not paper:
            continue

        existing = Innovation.query.filter_by(paper_id=paper.id).first()
        if existing:
            logger.info("跳过已存在创新点: %s...", paper.title[:40])
            continue

        innovation = Innovation(
            paper_id=paper.id,
            problem=preset["problem"],
            method=preset["method"],
            effect=preset["effect"],
            is_verified=preset["is_verified"],
            confidence=1.0,
        )
        innovation.build_full_statement()
        db.session.add(innovation)

    db.session.commit()
    logger.info("预置创新点设置完成")


def extract_innovations_for_all():
    """为没有创新点的论文自动提取创新点"""
    logger.info("正在为其他论文提取创新点...")

    extractor = InnovationExtractor()
    papers_without_innovation = Paper.query.outerjoin(
        Innovation, Paper.id == Innovation.paper_id
    ).filter(Innovation.id == None).all()

    for paper in papers_without_innovation:
        try:
            if paper.abstract:
                result = extractor.extract(paper)
                innovation = Innovation(
                    paper_id=paper.id,
                    problem=result["problem"],
                    method=result["method"],
                    effect=result["effect"],
                    confidence=result["confidence"],
                    is_verified=False,
                )
                innovation.build_full_statement()
                db.session.add(innovation)
                logger.info("提取: %s... (置信度: %.1f%%)", paper.title[:50], result['confidence'] * 100)
            else:
                logger.info("跳过(无摘要): %s...", paper.title[:40])
        except Exception as e:
            logger.warning("提取失败: %s... - %s", paper.title[:40], e)

    db.session.commit()
    logger.info("创新点提取完成")


def compute_embeddings():
    """计算所有论文的向量嵌入（仅当 SBERT 可用时）"""
    logger.info("检查向量嵌入...")

    recommender = Recommender(db)
    if recommender.use_sbert:
        try:
            count = recommender.compute_all_embeddings()
            logger.info("已为 %d 篇论文计算向量嵌入", count)
        except Exception as e:
            logger.warning("向量嵌入计算失败: %s，将使用 TF-IDF 回退", e)
    else:
        logger.warning("SentenceTransformer 不可用（网络受限），推荐将使用 TF-IDF")


def precompute_recommendations():
    """预计算全部论文的跨学科推荐。

    使用批量矩阵运算：TF-IDF 矩阵只构建一次，每篇论文通过一次矩阵乘法
    获得所有候选的相似度。总时间复杂度为 O(N)，远优于旧版逐对计算的 O(N²)。
    """
    logger.info("正在预计算跨学科推荐（批量矩阵运算模式）...")

    try:
        recommender = Recommender(db)
        papers = Paper.query.filter(Paper.abstract.isnot(None)).all()
        if len(papers) < 2:
            logger.info("论文数不足，跳过推荐预计算")
            return

        # 预热 TF-IDF 矩阵（只构建一次，后续 recommend() 复用缓存）
        recommender._build_tfidf_matrix(papers)
        logger.info("TF-IDF 矩阵已构建（%d 篇论文，%d 维特征）",
                     len(papers), recommender._tfidf_matrix.shape[1])

        count = 0
        for i, paper in enumerate(papers):
            try:
                results = recommender.recommend(paper.id, top_n=3, force_refresh=True)
                count += len(results)
                if (i + 1) % 10 == 0 or i == len(papers) - 1:
                    logger.info("  预计算进度: %d/%d", i + 1, len(papers))
            except Exception as e:
                logger.warning("预计算推荐失败 (paper_id=%d): %s", paper.id, e)

        logger.info("已预计算 %d 条跨学科推荐（覆盖 %d 篇论文）", count, len(papers))
    except Exception as e:
        logger.error("推荐预计算失败: %s", e)


def create_admin_user():
    """创建默认管理员账户（如不存在）"""
    config = get_config()
    username = config.DEFAULT_ADMIN_USERNAME
    password = config.DEFAULT_ADMIN_PASSWORD

    admin = User.query.filter_by(username=username).first()
    if admin:
        logger.info("管理员账户 '%s' 已存在，跳过创建", username)
        return

    admin = User(
        username=username,
        display_name="管理员",
        is_active=True,
        is_admin=True,
    )
    admin.set_password(password)
    db.session.add(admin)
    db.session.commit()
    logger.info("已创建默认管理员: %s / %s（请尽快修改默认密码）", username, password)


def main():
    """主入口"""
    banner = "=" * 60 + "\n[===] InnoCite 数据库初始化\n" + "=" * 60
    logger.info(banner)

    app = create_app()

    with app.app_context():
        # 1. 应用数据库迁移（Alembic），fallback 到 create_all
        migrations_dir = os.path.join(BASE_DIR, "migrations")
        if os.path.isdir(migrations_dir):
            from flask_migrate import upgrade as _migrate_upgrade
            _migrate_upgrade()
            logger.info("数据库迁移已应用（Alembic upgrade）")
        else:
            db.create_all()
            logger.info("migrations/ 目录不存在，已使用 db.create_all() 建表")

        # 2. 创建管理员账户
        create_admin_user()

        # 3. 创建示例论文
        create_sample_data()

        # 4. 设置预置创新点
        create_preset_innovations()

        # 5. 为其余论文自动提取创新点
        extract_innovations_for_all()

        # 6. 计算向量嵌入
        compute_embeddings()

        # 7. 预计算推荐
        precompute_recommendations()

        # 8. 统计
        paper_count = Paper.query.count()
        innovation_count = Innovation.query.count()
        user_count = User.query.count()
        categories = dict(
            db.session.query(Paper.category, db.func.count(Paper.id))
            .group_by(Paper.category).all()
        )

        logger.info("=" * 60)
        logger.info("数据库统计: 论文=%d, 创新点=%d, 用户=%d, 学科=%s",
                     paper_count, innovation_count, user_count, categories)
        logger.info("数据库初始化完成！运行 python app.py 启动应用。")


if __name__ == "__main__":
    main()
