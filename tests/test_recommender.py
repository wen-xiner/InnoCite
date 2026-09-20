"""
跨学科推荐器最小测试集。
覆盖：Top-N 限制、跨学科过滤、相似度降序、SBERT 不可用时的维度逻辑。

测试通过 monkeypatch 禁用 SBERT（不加载真实模型），强制走 TF-IDF 路径。
"""

import pytest

from models import db, Paper
from recommender import Recommender
from utils.sbert_manager import sbert_manager


def _make_paper(title, abstract, category):
    return Paper(
        title=title,
        authors="Tester",
        year=2020,
        abstract=abstract,
        category=category,
        source_type="CSV",
        status="success",
    )


@pytest.fixture
def papers(app):
    """构建 4 篇论文：cs.CV ×2、cs.CL ×1、cs.AI ×1。

    摘要刻意共享学术通用词汇（neural network model / accuracy / performance），
    保证 TF-IDF 回退路径下相似度能超过阈值 0.05，否则推荐结果恒为空。
    """
    with app.app_context():
        ps = [
            _make_paper(
                "Attention for vision",
                "We propose a deep neural network model for image recognition. "
                "Our method achieves high accuracy and strong performance on visual benchmarks.",
                "cs.CV",
            ),
            _make_paper(
                "Transformer for translation",
                "We introduce a neural network model for language translation. "
                "Our method improves the performance of text processing systems.",
                "cs.CL",
            ),
            _make_paper(
                "RL for robot control",
                "We design a neural network model for intelligent agents. "
                "Our method achieves high accuracy and good performance in planning and decision making.",
                "cs.AI",
            ),
            _make_paper(
                "Segmentation network",
                "We present a neural network model for video analysis. "
                "Our method shows competitive accuracy on visual tasks.",
                "cs.CV",
            ),
        ]
        db.session.add_all(ps)
        db.session.commit()
        for p in ps:
            db.session.refresh(p)
        return ps


@pytest.fixture
def recommender_no_sbert(monkeypatch):
    """禁用 SBERT 的推荐器（走 TF-IDF 回退路径）。"""
    monkeypatch.setattr(sbert_manager, "_available", False)
    monkeypatch.setattr(sbert_manager, "_model", None)
    return Recommender(db)


def test_recommend_cross_category(app, papers, recommender_no_sbert):
    with app.app_context():
        results = recommender_no_sbert.recommend(papers[0].id, top_n=3)
        assert 0 < len(results) <= 3
        # 默认排除同学科：cs.CV 不应出现在结果中
        cats = {r["target_category"] for r in results}
        assert cats <= {"cs.CL", "cs.AI"}


def test_recommend_top_n_limit(app, papers, recommender_no_sbert):
    with app.app_context():
        results = recommender_no_sbert.recommend(papers[0].id, top_n=1)
        assert len(results) == 1


def test_recommend_similarity_descending(app, papers, recommender_no_sbert):
    with app.app_context():
        results = recommender_no_sbert.recommend(papers[0].id, top_n=3)
        sims = [r["similarity"] for r in results]
        assert sims == sorted(sims, reverse=True)


def test_recommend_exclude_same_category_off(app, papers, recommender_no_sbert):
    with app.app_context():
        results = recommender_no_sbert.recommend(
            papers[0].id, top_n=5, exclude_same_category=False
        )
        # 不排除同学科时，可能包含 cs.CV 论文
        assert len(results) > 0


def test_embedding_dim_unavailable(app, recommender_no_sbert):
    with app.app_context():
        assert recommender_no_sbert.use_sbert is False
        assert recommender_no_sbert.embedding_dim is None
