"""
规则创新点提取器（RuleInnovationExtractor）最小测试集。
覆盖：中英文提取、空输入回退、置信度计算。
"""

import pytest

from innovation_extractor import RuleInnovationExtractor
from models import Paper


@pytest.fixture
def extractor():
    return RuleInnovationExtractor()


def _paper(abstract, full_text=None):
    return Paper(
        title="Test Paper",
        authors="Tester",
        year=2020,
        abstract=abstract,
        full_text=full_text,
        category="cs.CV",
    )


def test_extract_english(extractor):
    paper = _paper(
        "We propose a novel attention mechanism for image recognition. "
        "Experiments show our method achieves 95% accuracy."
    )
    result = extractor.extract(paper)
    assert result["method"] != "待补充"
    assert "attention" in result["method"].lower()
    assert result["effect"] != "待补充"
    assert result["source"] == "rule"


def test_extract_chinese(extractor):
    paper = _paper(
        "本文提出一种新的语义分割模型，采用Transformer架构。"
        "实验结果表明该方法达到92%的准确率。"
    )
    result = extractor.extract(paper)
    assert result["method"] != "待补充"
    assert result["source"] == "rule"
    # 数值指标应提升效果提取
    assert result["effect"] != "待补充"


def test_empty_input_returns_placeholder(extractor):
    paper = _paper("")
    result = extractor.extract(paper)
    assert result["problem"] == "待补充"
    assert result["method"] == "待补充"
    assert result["effect"] == "待补充"
    assert result["confidence"] == 0.0


def test_calculate_confidence_full_with_numeric(extractor):
    conf = extractor.calculate_confidence("问题", "方法", "效果达到95%")
    assert 0.6 <= conf <= 1.0


def test_calculate_confidence_empty(extractor):
    assert extractor.calculate_confidence("待补充", "待补充", "待补充") == 0.0


def test_calculate_confidence_partial(extractor):
    # 只提取两个维度 → 约 0.67，且不含数值加分
    conf = extractor.calculate_confidence("问题", "方法", "待补充")
    assert conf == round(2 / 3, 2)
