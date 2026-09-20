"""
KeyBERT 关键词提取模块。

使用 SBERT 语义向量进行关键词提取，比纯 TF-IDF 更精准：
- 文档级向量 & 候选词向量 → 余弦相似度排序 → Top-N 关键词
- 使用全局 SBERTManager 共享模型（与推荐系统、分类器一致）
- 不可用时自动回退到 TF-IDF

原理等价于 KeyBERT 库，但不引入额外依赖，直接用 SBERT + sklearn 实现。
"""

import logging
import numpy as np
from collections import Counter

from utils.sbert_manager import sbert_manager

logger = logging.getLogger("InnoCite.KeyBERT")


class KeyBERTExtractor:
    """基于 SBERT 语义相似度的关键词提取器。

    实现方式（等价于 KeyBERT 核心算法）：
    1. 使用 SBERT 编码整篇文档 → 文档级向量
    2. 提取候选词/短语（jieba 分词 + n-gram）
    3. 使用 SBERT 编码每个候选词 → 词级向量
    4. 计算文档向量与每个候选词向量的余弦相似度
    5. 排序取 Top-N

    优势：基于语义理解，而非纯统计频率。例如 "neural network"
    和 "deep learning" 即使字面不同，也能因为语义相似而关联。
    """

    def __init__(self):
        """初始化提取器。"""
        self._stopwords = None

    @property
    def available(self):
        """检查 SBERT 是否可用（由全局 SBERTManager 统一管理）。"""
        return sbert_manager.available

    @property
    def model(self):
        """获取共享的 SBERT 模型实例。"""
        return sbert_manager.model

    def extract_keywords(self, doc_text, top_n=5, diverse=True,
                         diversity_threshold=0.7):
        """从单篇文档中提取关键词。

        参数:
            doc_text: 文档文本
            top_n: 返回的关键词数量
            diverse: 是否启用多样性过滤（MMR 算法）
            diversity_threshold: MMR 多样性阈值（0~1，越大越多样）

        返回:
            list of (keyword, score) 元组，按分数降序
        """
        if not self.available or not doc_text or not doc_text.strip():
            return []

        # 1. 提取候选词
        candidates = self._extract_candidates(doc_text)
        if not candidates:
            return []

        # 2. SBERT 编码（经 SBERTManager 线程安全封装）
        try:
            doc_embedding = sbert_manager.encode(
                [doc_text], show_progress_bar=False, convert_to_numpy=True
            )[0]
            candidate_embeddings = sbert_manager.encode(
                candidates, show_progress_bar=False, convert_to_numpy=True
            )
        except Exception:
            logger.warning("KeyBERT 编码失败")
            return []

        # 3. 余弦相似度计算
        doc_norm = doc_embedding / (np.linalg.norm(doc_embedding) + 1e-10)
        cand_norms = candidate_embeddings / (
            np.linalg.norm(candidate_embeddings, axis=1, keepdims=True) + 1e-10
        )
        similarities = np.dot(cand_norms, doc_norm)

        # 4. 排序 + 多样性过滤
        if diverse and len(candidates) > top_n:
            keywords = self._mmr_diverse(
                candidates, candidate_embeddings, similarities,
                top_n=top_n, lambda_param=1 - diversity_threshold
            )
        else:
            # 简单排序
            indices = np.argsort(similarities)[::-1][:top_n]
            keywords = [(candidates[i], float(similarities[i])) for i in indices]

        return [(kw, round(score, 4)) for kw, score in keywords if score > 0]

    def extract_keywords_batch(self, documents, top_n=5):
        """批量提取多篇文档的关键词。

        参数:
            documents: list of (paper_id, doc_text) 元组
            top_n: 每篇文档的关键词数量

        返回:
            dict: {paper_id: [(keyword, score), ...]}
        """
        if not self.available:
            return {}

        valid_docs = [(pid, text) for pid, text in documents if text and text.strip()]
        if not valid_docs:
            return {}

        result = {}
        for paper_id, doc_text in valid_docs:
            keywords = self.extract_keywords(doc_text, top_n=top_n)
            if keywords:
                result[paper_id] = keywords

        return result

    def _extract_candidates(self, text):
        """从文本中提取候选关键词（jieba 分词 + 词性过滤）"""
        from utils import tokenize, tokenize_with_pos

        # 方法 1：使用词性标注提取名词/动词
        pos_pairs = tokenize_with_pos(text)
        noun_verbs = []
        for word, flag in pos_pairs:
            if flag.startswith("n") or flag.startswith("v") or flag in {"eng"}:
                if len(word) >= 2:
                    noun_verbs.append(word)

        # 方法 2：普通分词作为补充
        tokens = tokenize(text)

        # 合并去重
        candidates = list(dict.fromkeys(noun_verbs + tokens))

        # 过滤过短或过长的候选词
        candidates = [c for c in candidates if 2 <= len(c) <= 30]

        # 限制候选词数量（避免 SBERT 编码过慢）
        if len(candidates) > 500:
            # 按频率取前 500
            freq = Counter(tokens)
            candidates.sort(key=lambda w: freq.get(w, 0), reverse=True)
            candidates = candidates[:500]

        return candidates

    def _mmr_diverse(self, candidates, embeddings, similarities,
                     top_n=5, lambda_param=0.3):
        """MMR（最大边际相关性）多样性排序算法。

        在相关性和多样性之间取得平衡：
        - lambda_param 越小 → 越多样化（避免重复关键词）
        - lambda_param 越大 → 越相关

        参数:
            candidates: 候选词列表
            embeddings: 候选词向量矩阵
            similarities: 各候选词与文档的相似度数组
            top_n: 返回数量
            lambda_param: 相关性权重（0~1）
        """
        n = len(candidates)
        if n <= top_n:
            indices = np.argsort(similarities)[::-1][:top_n]
            return [(candidates[i], float(similarities[i])) for i in indices]

        # 归一化相似度
        sims = similarities.copy()
        sims_max = sims.max()
        if sims_max > 0:
            sims = sims / sims_max

        # MMR 贪心选择
        selected = []
        remaining = list(range(n))

        while len(selected) < top_n and remaining:
            mmr_scores = []
            for idx in remaining:
                relevance = sims[idx]
                if selected:
                    # 已选择关键词的嵌入矩阵
                    selected_embs = embeddings[selected]
                    cand_emb = embeddings[idx].reshape(1, -1)
                    redundancy = np.dot(cand_emb, selected_embs.T).max()
                else:
                    redundancy = 0
                mmr = lambda_param * relevance - (1 - lambda_param) * redundancy
                mmr_scores.append(mmr)

            best_local = np.argmax(mmr_scores)
            best_global_idx = remaining[best_local]
            selected.append(best_global_idx)
            remaining.pop(best_local)

        return [(candidates[i], float(similarities[i])) for i in selected]


# ── 模块级单例 ──
_keybert_extractor = None


def get_keybert_extractor():
    """获取 KeyBERT 提取器单例"""
    global _keybert_extractor
    if _keybert_extractor is None:
        _keybert_extractor = KeyBERTExtractor()
    return _keybert_extractor
