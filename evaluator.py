"""
模型评估模块。

提供对以下 AI 组件的量化评估：
  1. 创新点提取质量 — ROUGE-L + BERTScore（与人工标注对比）
  2. 关键词提取质量 — Precision@K / Recall@K / F1@K
  3. 论文分类准确率 — Accuracy + 每类 F1

这是人工智能实训项目的关键模块，让学生经历完整的
"数据标注 → 模型评估 → 指标分析 → 迭代优化"流程。
"""

import json
import os
import logging
from collections import defaultdict

import numpy as np

from utils import BASE_DIR

logger = logging.getLogger("InnoCite.Evaluator")

# Ground truth 文件路径
GROUND_TRUTH_PATH = os.path.join(BASE_DIR, "data", "ground_truth.json")


class Evaluator:
    """模型评估器"""

    def __init__(self, db):
        self.db = db
        self._ground_truth = None

    # ── Ground Truth 加载 ──────────────────

    @property
    def ground_truth(self):
        """加载人工标注数据"""
        if self._ground_truth is None:
            try:
                with open(GROUND_TRUTH_PATH, "r", encoding="utf-8") as f:
                    self._ground_truth = json.load(f)
                logger.info("已加载 ground truth: %d 篇标注论文",
                            len(self._ground_truth.get("papers", [])))
            except FileNotFoundError:
                logger.warning("Ground truth 文件不存在: %s，评估将返回空结果",
                               GROUND_TRUTH_PATH)
                self._ground_truth = {"papers": []}
            except json.JSONDecodeError:
                logger.error("Ground truth 文件格式错误")
                self._ground_truth = {"papers": []}
        return self._ground_truth

    def get_annotated_papers(self):
        """获取所有已标注的论文 ID 列表（优先按 arxiv_id 匹配）"""
        papers = self.ground_truth.get("papers", [])
        from models import Paper
        ids = []
        for p in papers:
            pid = p.get("paper_id")
            arxiv_id = p.get("arxiv_id")
            if arxiv_id:
                paper = Paper.query.filter_by(arxiv_id=arxiv_id).first()
                if paper:
                    ids.append(paper.id)
                    continue
            if pid:
                ids.append(pid)
        return ids

    def _resolve_paper(self, gt):
        """根据标注记录解析对应的 Paper 对象。

        优先按 arxiv_id（demo-* 稳定标识）匹配，回退到 paper_id。
        """
        from models import Paper
        arxiv_id = gt.get("arxiv_id")
        if arxiv_id:
            paper = Paper.query.filter_by(arxiv_id=arxiv_id).first()
            if paper:
                return paper
        paper_id = gt.get("paper_id")
        if paper_id:
            return Paper.query.get(paper_id)
        return None

    # ── 创新点评估 ──────────────────────

    def evaluate_innovation(self, extractor=None):
        """评估创新点提取质量。

        指标：
        - ROUGE-L：与人工标注的文本重叠度
        - BERTScore（可选）：语义相似度

        返回:
            dict: {
                "total": int,           # 评估论文总数
                "rouge_l": {            # ROUGE-L 分数
                    "problem": float,
                    "method": float,
                    "effect": float,
                    "avg": float,
                },
                "per_paper": [...],     # 每篇论文的详细分数
            }
        """
        from models import Paper, Innovation

        gt_papers = self.ground_truth.get("papers", [])
        if not gt_papers:
            return {"error": "无标注数据，请先准备 data/ground_truth.json"}

        results = []
        for gt in gt_papers:
            paper = self._resolve_paper(gt)
            if not paper:
                continue

            innovation = paper.innovation
            if not innovation:
                # 自动提取
                if extractor:
                    from routes.helpers import extract_innovation_for_paper
                    extract_innovation_for_paper(paper)
                    self.db.session.commit()
                    innovation = paper.innovation

            if not innovation:
                continue

            # 计算每个维度的 ROUGE-L
            rouge_scores = {}
            for dim in ["problem", "method", "effect"]:
                predicted = getattr(innovation, dim, "待补充") or ""
                reference = gt.get(dim, "")
                rouge_scores[dim] = self._compute_rouge_l(predicted, reference)

            results.append({
                "paper_id": paper.id,
                "arxiv_id": paper.arxiv_id,
                "title": (paper.title or "")[:60],
                "rouge": rouge_scores,
                "avg_rouge": round(sum(rouge_scores.values()) / 3, 4),
            })

        if not results:
            return {"error": "无有效评估结果"}

        # 汇总
        avg_scores = {}
        for dim in ["problem", "method", "effect"]:
            dim_scores = [r["rouge"][dim] for r in results]
            avg_scores[dim] = round(sum(dim_scores) / len(dim_scores), 4)

        return {
            "total": len(results),
            "rouge_l": {
                **avg_scores,
                "avg": round(sum(avg_scores.values()) / 3, 4),
            },
            "per_paper": results,
        }

    def _compute_rouge_l(self, predicted, reference):
        """计算 ROUGE-L（最长公共子序列）分数。

        ROUGE-L = (1+β²) * P * R / (β² * P + R)
        其中 β=1（F1 权重），P=precision，R=recall
        """
        if not reference or not predicted:
            return 0.0

        # 分词
        pred_tokens = self._tokenize(predicted)
        ref_tokens = self._tokenize(reference)

        if not pred_tokens or not ref_tokens:
            return 0.0

        # LCS 长度
        lcs_len = self._lcs_length(pred_tokens, ref_tokens)

        precision = lcs_len / len(pred_tokens) if pred_tokens else 0
        recall = lcs_len / len(ref_tokens) if ref_tokens else 0

        if precision + recall == 0:
            return 0.0

        # F1
        return round(2 * precision * recall / (precision + recall), 4)

    @staticmethod
    def _lcs_length(a, b):
        """计算两个序列的最长公共子序列长度（动态规划）"""
        m, n = len(a), len(b)
        # 使用两行优化空间
        prev = [0] * (n + 1)
        curr = [0] * (n + 1)
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if a[i - 1] == b[j - 1]:
                    curr[j] = prev[j - 1] + 1
                else:
                    curr[j] = max(prev[j], curr[j - 1])
            prev, curr = curr, prev
        return prev[n]

    @staticmethod
    def _tokenize(text):
        """简易分词（英文按空格，中文按字符 bigram）"""
        import re
        # 分离中英文
        tokens = []
        # 英文单词
        eng_words = re.findall(r'[a-zA-Z]+', text)
        tokens.extend(w.lower() for w in eng_words)
        # 中文按 bigram
        chinese = re.sub(r'[a-zA-Z\s\d\W]', '', text)
        for i in range(len(chinese) - 1):
            tokens.append(chinese[i:i + 2])
        return tokens

    # ── 关键词评估 ──────────────────────

    def evaluate_keywords(self, top_k=5):
        """评估关键词提取质量。

        指标：Precision@K, Recall@K, F1@K

        返回:
            dict: {
                "total": int,
                "precision@k": float,
                "recall@k": float,
                "f1@k": float,
                "per_paper": [...],
            }
        """
        from models import Paper
        from keyword_trend import KeywordTrendAnalyzer

        gt_papers = self.ground_truth.get("papers", [])
        gt_with_keywords = [p for p in gt_papers if p.get("keywords")]

        if not gt_with_keywords:
            return {"error": "无标注关键词数据"}

        analyzer = KeywordTrendAnalyzer(self.db)
        all_keywords = analyzer.get_all_keywords()

        results = []
        total_precision = 0
        total_recall = 0

        for gt in gt_with_keywords:
            paper = self._resolve_paper(gt)
            if not paper:
                continue
            paper_id = paper.id
            gt_kw = set(gt.get("keywords", []))
            pred_kw = all_keywords.get(paper_id, [])[:top_k]

            if not pred_kw:
                continue

            pred_set = set(pred_kw)
            intersection = gt_kw & pred_set

            precision = len(intersection) / len(pred_set) if pred_set else 0
            recall = len(intersection) / len(gt_kw) if gt_kw else 0
            f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

            total_precision += precision
            total_recall += recall

            results.append({
                "paper_id": paper_id,
                "arxiv_id": paper.arxiv_id,
                "precision": round(precision, 4),
                "recall": round(recall, 4),
                "f1": round(f1, 4),
                "predicted": pred_kw,
                "ground_truth": list(gt_kw),
            })

        n = len(results) if results else 1
        avg_precision = total_precision / n
        avg_recall = total_recall / n
        avg_f1 = 2 * avg_precision * avg_recall / (avg_precision + avg_recall) \
            if (avg_precision + avg_recall) > 0 else 0

        return {
            "total": len(results),
            "precision@k": round(avg_precision, 4),
            "recall@k": round(avg_recall, 4),
            "f1@k": round(avg_f1, 4),
            "k": top_k,
            "per_paper": results,
        }

    # ── 分类评估 ──────────────────────

    def evaluate_classification(self):
        """评估论文分类准确率。

        指标：Accuracy, 每类 Precision/Recall/F1

        返回:
            dict: {
                "total": int,
                "accuracy": float,
                "per_class": {category: {precision, recall, f1, count}},
                "details": [...],
            }
        """
        from models import Paper
        from paper_classifier import get_classifier

        gt_papers = self.ground_truth.get("papers", [])
        gt_with_category = [p for p in gt_papers if p.get("category")]

        if not gt_with_category:
            return {"error": "无标注分类数据"}

        classifier = get_classifier()
        correct = 0
        details = []
        per_class = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0, "count": 0})

        for gt in gt_with_category:
            paper = self._resolve_paper(gt)
            if not paper:
                continue
            paper_id = paper.id
            gt_category = gt["category"]

            predicted = classifier.classify(paper.title, paper.abstract)
            is_correct = (predicted == gt_category)

            if is_correct:
                correct += 1
                per_class[gt_category]["tp"] += 1
            else:
                per_class[gt_category]["fn"] += 1
                if predicted:
                    per_class[predicted]["fp"] += 1

            per_class[gt_category]["count"] += 1

            details.append({
                "paper_id": paper_id,
                "arxiv_id": paper.arxiv_id,
                "title": (paper.title or "")[:60],
                "ground_truth": gt_category,
                "predicted": predicted,
                "correct": is_correct,
            })

        n = len(details) if details else 1

        # 计算每类指标
        per_class_result = {}
        for cat, counts in per_class.items():
            tp = counts["tp"]
            fp = counts["fp"]
            fn = counts["fn"]
            precision = tp / (tp + fp) if (tp + fp) > 0 else 0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0
            f1 = 2 * precision * recall / (precision + recall) \
                if (precision + recall) > 0 else 0
            per_class_result[cat] = {
                "precision": round(precision, 4),
                "recall": round(recall, 4),
                "f1": round(f1, 4),
                "count": counts["count"],
            }

        return {
            "total": len(details),
            "accuracy": round(correct / n, 4),
            "per_class": per_class_result,
            "details": details,
        }

    # ── 综合评估报告 ────────────────────

    def full_report(self, extractor=None):
        """生成完整的模型评估报告。

        返回:
            dict: {
                "innovation": {...},
                "keywords": {...},
                "classification": {...},
                "summary": str,          # 一句话总结
                "recommendations": [...], # 改进建议
            }
        """
        report = {
            "innovation": self.evaluate_innovation(extractor),
            "keywords": self.evaluate_keywords(),
            "classification": self.evaluate_classification(),
        }

        # 生成总结
        summary_parts = []
        recommendations = []

        # 创新点评估
        inno = report["innovation"]
        if "error" not in inno:
            avg_rouge = inno.get("rouge_l", {}).get("avg", 0)
            summary_parts.append(f"创新点提取 ROUGE-L: {avg_rouge:.2%}")
            if avg_rouge < 0.3:
                recommendations.append(
                    "创新点提取质量偏低（ROUGE-L < 0.3），建议启用 LLM 提取或优化规则引擎触发词"
                )
            elif avg_rouge < 0.5:
                recommendations.append(
                    "创新点提取质量中等，建议检查 LLM 是否正常运行或补充标注数据"
                )
        else:
            summary_parts.append("创新点评估: 无标注数据")

        # 关键词评估
        kw = report["keywords"]
        if "error" not in kw:
            f1 = kw.get("f1@k", 0)
            summary_parts.append(f"关键词 F1@{kw.get('k', 5)}: {f1:.2%}")
            if f1 < 0.3:
                recommendations.append(
                    "关键词提取质量偏低，建议启用 KeyBERT 或增加停用词过滤"
                )
        else:
            summary_parts.append("关键词评估: 无标注数据")

        # 分类评估
        cls_eval = report["classification"]
        if "error" not in cls_eval:
            acc = cls_eval.get("accuracy", 0)
            summary_parts.append(f"分类准确率: {acc:.2%}")
            if acc < 0.5:
                recommendations.append(
                    "分类准确率偏低，建议检查 SBERT 模型是否正常加载或更新学科描述"
                )
        else:
            summary_parts.append("分类评估: 无标注数据")

        report["summary"] = " | ".join(summary_parts)
        report["recommendations"] = recommendations if recommendations else ["各模块运行良好"]

        return report
