"""
评估器（ROUGE-L / LCS）最小测试集。
"""

from evaluator import Evaluator
from models import db


def _evaluator():
    return Evaluator(db)


def test_rouge_l_exact_match():
    ev = _evaluator()
    text = "我们提出一个注意力模型"
    assert ev._compute_rouge_l(text, text) == 1.0


def test_rouge_l_no_match():
    ev = _evaluator()
    # 纯英文文本，确保无任何共同 token（中文 bigram 容易意外重叠）
    assert ev._compute_rouge_l(
        "This is a completely different topic",
        "quantum entanglement research",
    ) == 0.0


def test_rouge_l_empty():
    ev = _evaluator()
    assert ev._compute_rouge_l("", "参考文本") == 0.0
    assert ev._compute_rouge_l("预测文本", "") == 0.0


def test_rouge_l_partial_between_zero_and_one():
    ev = _evaluator()
    score = ev._compute_rouge_l("我们提出一个注意力模型提升精度", "我们提出一个注意力模型")
    assert 0.0 < score < 1.0


def test_lcs_length():
    assert Evaluator._lcs_length("abcde", "ace") == 3
    assert Evaluator._lcs_length("abc", "def") == 0
    assert Evaluator._lcs_length("", "abc") == 0
    assert Evaluator._lcs_length("xyz", "xyzxyz") == 3
