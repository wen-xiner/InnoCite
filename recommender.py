"""
跨学科推荐系统模块。
优先使用 SentenceTransformer 生成论文向量，
网络不可用时自动回退到 TF-IDF 向量进行相似度计算。
"""

import logging
import numpy as np
from datetime import datetime
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.feature_extraction.text import TfidfVectorizer

from utils.sbert_manager import sbert_manager

logger = logging.getLogger("InnoCite.Recommender")

from models import db, Paper, PaperEmbedding, Recommendation


class Recommender:
    """跨学科论文推荐器"""

    def __init__(self, db_session=None):
        self.db = db_session or db
        self._tfidf_vectorizer = None
        self._tfidf_matrix = None
        self._tfidf_paper_ids = None
        self.similarity_threshold = 0.05  # 跨学科TF-IDF相似度通常较低

    @property
    def use_sbert(self):
        """检查 SBERT 是否可用（由全局 SBERTManager 统一管理）。"""
        return sbert_manager.available

    @property
    def model(self):
        """获取共享的 SentenceTransformer 模型实例。"""
        return sbert_manager.model

    @property
    def embedding_dim(self):
        """获取 SBERT 模型的实际嵌入维度（动态获取，消除魔法数字）。

        all-MiniLM-L6-v2 输出 384 维；不同模型维度不同，
        统一从模型实例查询，避免硬编码导致的缓存永不命中。
        """
        if not self.use_sbert:
            return None
        model = self.model
        if model is None:
            return None
        try:
            # 兼容新旧 API：get_sentence_embedding_dimension → get_embedding_dimension
            getter = getattr(model, "get_embedding_dimension", None) \
                or getattr(model, "get_sentence_embedding_dimension", None)
            if getter is None:
                return 384
            return getter()
        except Exception:
            logger.warning("无法获取 SBERT 嵌入维度，回退默认 384", exc_info=True)
            return 384

    def _paper_to_text(self, paper):
        """将论文转换为模型输入文本（标题 + 摘要 + 创新点方法 + 正文章节节选）。

        通篇分析：有正文时额外注入 Method 章节（方法细节对跨学科迁移推荐
        最关键），带长度上限避免正文淹没摘要语义。无正文时自动降级。
        """
        parts = []
        if paper.title:
            parts.append(paper.title)
        if paper.abstract:
            parts.append(paper.abstract)
        if paper.innovation and paper.innovation.method and paper.innovation.method != "待补充":
            parts.append(paper.innovation.method)

        # 通篇：注入正文章节（Method 优先，其次 Experiments/Conclusion）
        if paper.full_text and len(paper.full_text.strip()) > 50:
            sections = self._extract_sections(paper.full_text)
            body_parts = []
            budget = 2000  # 正文章节总预算（字符）
            # 优先级：Method > Approach > Framework > Model > Experiments > Conclusion
            priority = ["Method", "Approach", "Framework", "Model",
                        "Experiments", "Results", "Evaluation", "Conclusion"]
            for name in priority:
                if budget <= 0:
                    break
                body = sections.get(name, "")
                if body:
                    chunk = body[:1200].strip()
                    if chunk:
                        body_parts.append(chunk)
                        budget -= len(chunk)
            if body_parts:
                parts.append(" ".join(body_parts))

        return " ".join(parts)

    @staticmethod
    def _extract_sections(full_text):
        """提取正文各章节文本，返回 {章节名: 内容}。复用 LLM 客户端的分节逻辑。"""
        try:
            from llm_client import LLMClient
            return dict(LLMClient._split_full_text(full_text))
        except Exception:
            # 兜底：无法分节时整段作为 Method 处理
            return {"FullText": full_text[:2000]}

    def compute_embedding(self, paper):
        """使用 SBERT 计算单篇论文的向量嵌入（维度由模型动态决定）"""
        if not self.use_sbert:
            return None

        text = self._paper_to_text(paper)
        if not text.strip():
            return None

        embedding = sbert_manager.encode(text, show_progress_bar=False)
        return embedding.astype(np.float32)

    def get_embedding(self, paper):
        """获取论文的 SBERT 向量嵌入（优先缓存，否则计算）"""
        if not self.use_sbert:
            return None

        emb_record = PaperEmbedding.query.filter_by(paper_id=paper.id).first()
        if emb_record:
            embedding = np.frombuffer(emb_record.embedding, dtype=np.float32)
            if len(embedding) == self.embedding_dim:
                return embedding.reshape(1, -1)

        embedding = self.compute_embedding(paper)
        if embedding is None:
            return None

        if emb_record:
            emb_record.embedding = embedding.tobytes()
        else:
            emb_record = PaperEmbedding(paper_id=paper.id, embedding=embedding.tobytes())
            self.db.session.add(emb_record)
        self.db.session.commit()

        return embedding.reshape(1, -1)

    def compute_all_embeddings(self):
        """批量计算所有论文的 SBERT 向量嵌入"""
        if not self.use_sbert:
            return 0

        papers = Paper.query.filter(Paper.abstract.isnot(None)).all()
        count = 0
        for paper in papers:
            existing = PaperEmbedding.query.filter_by(paper_id=paper.id).first()
            if existing:
                continue
            embedding = self.compute_embedding(paper)
            if embedding is not None:
                emb_record = PaperEmbedding(paper_id=paper.id, embedding=embedding.tobytes())
                self.db.session.add(emb_record)
                count += 1

        self.db.session.commit()
        return count

    # ─── TF-IDF 回退方案 ──────────────────────────────

    def _build_tfidf_matrix(self, papers=None):
        """构建 TF-IDF 矩阵（当 SBERT 不可用时使用）"""
        if papers is None:
            papers = Paper.query.filter(Paper.abstract.isnot(None)).all()

        corpus = [self._paper_to_text(p) for p in papers]
        paper_ids = [p.id for p in papers]

        self._tfidf_vectorizer = TfidfVectorizer(
            max_features=3000, min_df=1, max_df=0.95,
            stop_words="english",
        )
        self._tfidf_matrix = self._tfidf_vectorizer.fit_transform(corpus)
        self._tfidf_paper_ids = paper_ids

        return self._tfidf_matrix, paper_ids

    def _get_tfidf_vector(self, paper):
        """获取单篇论文的 TF-IDF 向量"""
        if self._tfidf_matrix is None:
            self._build_tfidf_matrix()

        # 尝试在已构建的矩阵中找到该论文
        try:
            idx = self._tfidf_paper_ids.index(paper.id)
            return self._tfidf_matrix[idx]
        except (ValueError, AttributeError):
            # 论文不在矩阵中，单独向量化
            text = self._paper_to_text(paper)
            vec = self._tfidf_vectorizer.transform([text])
            return vec

    # ─── 推荐核心逻辑 ────────────────────────────────

    def recommend(self, source_paper_id, top_n=3, force_refresh=False, exclude_same_category=True):
        """
        为指定论文推荐跨学科的相关论文。

        优先使用 SBERT（批量矩阵运算），不可用时回退到 TF-IDF（稀疏矩阵
        一次计算全量相似度后排序取 top N）。时间复杂度从 O(N²) 降为 O(N)。
        """
        # 检查缓存
        if not force_refresh:
            cached = Recommendation.query.filter_by(
                source_paper_id=source_paper_id
            ).order_by(Recommendation.similarity.desc()).limit(top_n).all()
            if cached:
                return [r.to_dict() for r in cached]

        source_paper = self.db.session.get(Paper, source_paper_id)
        if not source_paper:
            return []

        candidate_papers = Paper.query.filter(
            Paper.id != source_paper_id,
            Paper.abstract.isnot(None),
        ).all()

        if not candidate_papers:
            return []

        # 筛选不同学科
        if exclude_same_category:
            candidates = [p for p in candidate_papers if p.category != source_paper.category]
            if not candidates:
                candidates = candidate_papers
        else:
            candidates = candidate_papers

        # ── 计算相似度（批量矩阵运算）──
        similarities = self._compute_similarities_batch(source_paper, candidates)

        # 排序取 top_n
        similarities.sort(key=lambda x: x[1], reverse=True)
        top_candidates = similarities[:top_n]

        # 生成推荐结果
        results = []
        for target_paper, sim in top_candidates:
            reason = self._generate_reason(source_paper, target_paper)
            results.append({
                "source_paper_id": source_paper_id,
                "target_paper_id": target_paper.id,
                "similarity": round(sim, 4),
                "reason": reason,
                "target_title": target_paper.title,
                "target_authors": target_paper.get_authors_list(),
                "target_year": target_paper.year,
                "target_category": target_paper.category,
            })

        # 缓存结果
        for r in results:
            existing = Recommendation.query.filter_by(
                source_paper_id=r["source_paper_id"],
                target_paper_id=r["target_paper_id"],
            ).first()
            if not existing:
                rec = Recommendation(
                    source_paper_id=r["source_paper_id"],
                    target_paper_id=r["target_paper_id"],
                    similarity=r["similarity"],
                    reason=r["reason"],
                )
                self.db.session.add(rec)

        self.db.session.commit()
        return results

    # ─── 批量相似度计算 ────────────────────────────

    def _compute_similarities_batch(self, source_paper, candidates):
        """批量计算源论文与所有候选论文的相似度。

        使用矩阵运算一次性完成所有对比，避免逐对循环。
        优先 SBERT，不可用时回退到 TF-IDF 稀疏矩阵。
        """
        similarities = []

        # ── SBERT 路径：批量加载 + 矩阵余弦 ──
        if self.use_sbert:
            source_emb = self.get_embedding(source_paper)
            if source_emb is not None:
                # 批量加载所有候选向量
                candidate_vecs = self._load_embeddings_batch(candidates)
                if candidate_vecs is not None and len(candidate_vecs) > 0:
                    # 一次性计算全部相似度
                    sims = cosine_similarity(source_emb, candidate_vecs)[0]
                    for i, sim in enumerate(sims):
                        if float(sim) >= self.similarity_threshold:
                            similarities.append((candidates[i], float(sim)))
                    if similarities:
                        return similarities

        # ── TF-IDF 路径：稀疏矩阵一次计算 ──
        if self._tfidf_matrix is None:
            self._build_tfidf_matrix()

        if self._tfidf_matrix is None or self._tfidf_matrix.shape[0] == 0:
            return []

        # 找到源论文和候选论文在 TF-IDF 矩阵中的位置
        source_idx = None
        candidate_indices = []   # 矩阵行索引
        valid_candidates = []    # 对应的 Paper 对象

        for i, pid in enumerate(self._tfidf_paper_ids):
            if pid == source_paper.id:
                source_idx = i
                break

        if source_idx is None:
            # 源论文不在矩阵中，单独向量化
            source_vec = self._get_tfidf_vector(source_paper)
            if source_vec is None:
                return []
            # 对候选论文逐个处理（数量不大时影响有限）
            for candidate in candidates:
                target_vec = self._get_tfidf_vector(candidate)
                if target_vec is None:
                    continue
                sim = cosine_similarity(source_vec, target_vec)[0][0]
                if float(sim) >= self.similarity_threshold:
                    similarities.append((candidate, float(sim)))
            return similarities

        # 批量：收集所有候选在矩阵中的索引
        candidate_id_set = {c.id for c in candidates}
        for i, pid in enumerate(self._tfidf_paper_ids):
            if pid in candidate_id_set:
                # 找到对应的 Paper 对象
                paper = next((c for c in candidates if c.id == pid), None)
                if paper:
                    candidate_indices.append(i)
                    valid_candidates.append(paper)

        if not candidate_indices:
            return []

        # 一次矩阵乘法计算全部相似度
        source_vec = self._tfidf_matrix[source_idx]
        candidate_matrix = self._tfidf_matrix[candidate_indices]
        sims = cosine_similarity(source_vec, candidate_matrix)[0]

        for i, sim in enumerate(sims):
            if float(sim) >= self.similarity_threshold:
                similarities.append((valid_candidates[i], float(sim)))

        return similarities

    def _load_embeddings_batch(self, papers):
        """批量从数据库加载论文的 SBERT 向量，拼接成 (N, dim) 的 np.ndarray。

        dim 由模型动态决定（如 all-MiniLM-L6-v2 为 384 维）。
        返回 None 表示批量加载失败，调用方应回退到 TF-IDF。
        """
        if not self.use_sbert:
            return None

        paper_ids = [p.id for p in papers]
        records = PaperEmbedding.query.filter(
            PaperEmbedding.paper_id.in_(paper_ids)
        ).all()

        if not records:
            return None

        record_map = {r.paper_id: r for r in records}
        vectors = []

        for paper in papers:
            rec = record_map.get(paper.id)
            if rec:
                emb = np.frombuffer(rec.embedding, dtype=np.float32)
                if len(emb) == self.embedding_dim:
                    vectors.append(emb)
                    continue

            # 补算缺失的嵌入
            emb = self.compute_embedding(paper)
            if emb is not None:
                vectors.append(emb)
            else:
                return None  # 有任何一个失败就回退

        if not vectors:
            return None

        return np.stack(vectors, axis=0)

    def _generate_reason(self, source_paper, target_paper):
        """生成推荐理由（LLM 优先，模板回退）"""
        # ── 路径 1：LLM 生成 ──
        llm_reason = self._generate_reason_llm(source_paper, target_paper)
        if llm_reason:
            return llm_reason

        # ── 路径 2：模板回退 ──
        return self._generate_reason_template(source_paper, target_paper)

    def _generate_reason_llm(self, source_paper, target_paper):
        """使用 LLM 生成推荐理由"""
        import os
        if not os.environ.get("LLM_REASON_ENABLED", "1") == "1":
            return None

        try:
            from llm_client import get_llm_client
            llm = get_llm_client()
            if not llm or not llm.available:
                return None
            reason = llm.generate_recommendation_reason(source_paper, target_paper)
            if reason:
                logger.info("推荐理由由 LLM 生成 (backend=%s)", llm.active_backend)
                return reason
        except Exception:
            logger.debug("LLM 推荐理由生成失败，使用模板回退", exc_info=True)

        return None

    def _generate_reason_template(self, source_paper, target_paper):
        """生成推荐理由（模板化回退方案）"""
        source_innovation = source_paper.innovation
        target_innovation = target_paper.innovation

        if target_innovation and target_innovation.method != "待补充":
            target_method = target_innovation.get_method_short(80)
            source_problem = ""
            if source_innovation and source_innovation.problem != "待补充":
                source_problem = source_innovation.problem[:80]

            if source_problem:
                return (
                    f"《{target_paper.title}》使用了 {target_method}，"
                    f"该方法可能迁移到你的领域 {source_paper.category or '未知'} "
                    f"以解决 {source_problem} 问题。"
                )
            else:
                return (
                    f"《{target_paper.title}》采用了 {target_method}，"
                    f"该方法可能对你的 {source_paper.category or '未知'} 领域研究有启发。"
                )

        source_keywords_hint = ""
        if source_innovation and source_innovation.method != "待补充":
            source_keywords_hint = f"其创新点 {source_innovation.get_method_short(50)}"

        return (
            f"尽管《{target_paper.title}》属于 {target_paper.category or '未知'}，"
            f"但其研究内容与你关注的 {source_paper.category or '未知'} 领域"
            f"{source_keywords_hint} 有潜在关联。"
        )

    def get_cached_recommendations(self, source_paper_id):
        """获取缓存的推荐结果"""
        return Recommendation.query.filter_by(
            source_paper_id=source_paper_id
        ).order_by(Recommendation.similarity.desc()).all()
