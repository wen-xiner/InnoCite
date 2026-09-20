# -*- coding: utf-8 -*-
"""真实论文对比评估：仅摘要 vs 通篇分析（摘要+正文）

对 3 篇真实 arXiv 论文分别用两种配置提取创新点，
与人工标注 ground truth 对比 ROUGE-L，量化通篇分析的收益。
"""
import json
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as appmod

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s %(message)s")
logger = logging.getLogger("RealEval")

app = appmod.create_app()
GROUND_TRUTH = json.load(open("data/ground_truth_real.json", encoding="utf-8"))["papers"]


def compute_rouge_l(predicted, reference):
    """ROUGE-L（LCS），与 evaluator 逻辑一致。"""
    import re

    def _tokenize(text):
        tokens = []
        eng_words = re.findall(r"[a-zA-Z]+", text)
        tokens.extend(w.lower() for w in eng_words)
        chinese = re.sub(r"[a-zA-Z\s\d\W]", "", text)
        for i in range(len(chinese) - 1):
            tokens.append(chinese[i:i + 2])
        return tokens

    if not reference or not predicted:
        return 0.0
    pred_tokens = _tokenize(predicted)
    ref_tokens = _tokenize(reference)
    if not pred_tokens or not ref_tokens:
        return 0.0

    m, n = len(pred_tokens), len(ref_tokens)
    prev = [0] * (n + 1)
    curr = [0] * (n + 1)
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if pred_tokens[i - 1] == ref_tokens[j - 1]:
                curr[j] = prev[j - 1] + 1
            else:
                curr[j] = max(prev[j], curr[j - 1])
        prev, curr = curr, prev
    lcs_len = prev[n]

    precision = lcs_len / len(pred_tokens) if pred_tokens else 0
    recall = lcs_len / len(ref_tokens) if ref_tokens else 0
    if precision + recall == 0:
        return 0.0
    return round(2 * precision * recall / (precision + recall), 4)


def evaluate(gt, title, abstract, full_text):
    """对单篇论文用给定配置提取创新点并算 ROUGE-L。"""
    from llm_client import get_llm_client
    from flask import current_app
    llm = get_llm_client(current_app.config)

    result = llm.extract_innovation(title, abstract, full_text)
    if not result:
        return None

    dims = ["problem", "method", "effect"]
    scores = {d: compute_rouge_l(result.get(d, ""), gt.get(d, "")) for d in dims}
    avg = round(sum(scores.values()) / 3, 4)
    return scores, avg, result


with app.app_context():
    from models import Paper

    rows = []
    for gt in GROUND_TRUTH:
        paper = Paper.query.filter_by(arxiv_id=gt["arxiv_id"].split("v")[0]).first()
        if not paper:
            paper = Paper.query.filter(Paper.arxiv_id.like(gt["arxiv_id"] + "%")).first()
        if not paper:
            logger.warning("未找到论文: %s", gt["arxiv_id"])
            continue

        title = paper.title
        abstract = paper.abstract
        full_text = paper.full_text

        logger.info("评估论文: %s", title[:50])
        logger.info("  摘要 %d 字符 | 正文 %d 字符", len(abstract or ""), len(full_text or ""))

        # 配置 A：仅摘要
        r_abs = evaluate(gt, title, abstract, None)
        # 配置 B：通篇（摘要+正文）
        r_full = evaluate(gt, title, abstract, full_text)

        rows.append({
            "arxiv_id": gt["arxiv_id"],
            "title": title,
            "abstract_only": r_abs,
            "fulltext": r_full,
        })
        logger.info("  仅摘要: %s | 通篇: %s",
                    r_abs[1] if r_abs else None,
                    r_full[1] if r_full else None)

    # ── 汇总 ──
    print("\n" + "=" * 70)
    print("真实论文对比评估结果")
    print("=" * 70)
    print(f"{'论文':<38s} {'仅摘要':>8s} {'通篇':>8s} {'Δ':>7s}")
    print("-" * 70)
    totals_abs = []
    totals_full = []
    for r in rows:
        a = r["abstract_only"][1] if r["abstract_only"] else 0
        f = r["fulltext"][1] if r["fulltext"] else 0
        totals_abs.append(a)
        totals_full.append(f)
        print(f"{r['title'][:38]:<38s} {a:>7.1%} {f:>7.1%} {f-a:>+6.1%}")

    avg_abs = sum(totals_abs) / len(totals_abs)
    avg_full = sum(totals_full) / len(totals_full)
    print("-" * 70)
    print(f"{'平均':<38s} {avg_abs:>7.1%} {avg_full:>7.1%} {avg_full-avg_abs:>+6.1%}")

    # 分维度
    print("\n分维度明细（平均）:")
    dims = ["problem", "method", "effect"]
    for d in dims:
        a_scores = [r["abstract_only"][0][d] for r in rows if r["abstract_only"]]
        f_scores = [r["fulltext"][0][d] for r in rows if r["fulltext"]]
        a_avg = sum(a_scores) / len(a_scores) if a_scores else 0
        f_avg = sum(f_scores) / len(f_scores) if f_scores else 0
        print(f"  {d:<10s} 仅摘要 {a_avg:>7.1%} | 通篇 {f_avg:>7.1%} | Δ {f_avg-a_avg:>+6.1%}")

    # 保存结果
    output = {
        "date": "2026-08-19",
        "per_paper": rows,
        "summary": {
            "avg_abstract_only": round(avg_abs, 4),
            "avg_fulltext": round(avg_full, 4),
            "delta": round(avg_full - avg_abs, 4),
        },
    }
    with open("output/evaluation_real_comparison.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print("\n已保存: output/evaluation_real_comparison.json")
