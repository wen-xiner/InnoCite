"""
关键词时序热度分析模块。
使用 jieba 分词 + TF-IDF 提取关键词，计算每年热度，构建时序曲线数据。

结果缓存在 KeywordCache 表中：当论文数量未变时直接返回 JSON 缓存的
热力图，避免每次请求都重跑全量分词和 TF-IDF。
"""

import hashlib
import json
import logging
from collections import defaultdict
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from utils import tokenize

logger = logging.getLogger("InnoCite.KeywordTrend")


class KeywordTrendAnalyzer:
    """关键词提取和热度计算分析器"""

    def __init__(self, db):
        self.db = db
        self._stopwords = None

    def _config_version(self):
        """生成当前关键词提取配置的版本哈希。

        当分词参数、停用词表或 TF-IDF 超参数变化时哈希值改变，
        从而自动失效旧缓存。
        """
        import os
        from utils import BASE_DIR

        fingerprint = {
            "tfidf_max_features": 5000,
            "tfidf_min_df": 1,
            "tfidf_max_df": 0.9,
            "keybert_enabled": self.keybert_enabled,
        }

        # 停用词文件的 MD5
        sw_path = os.path.join(BASE_DIR, "data", "stopwords.txt")
        try:
            with open(sw_path, "rb") as f:
                fingerprint["stopwords_md5"] = hashlib.md5(f.read()).hexdigest()
        except FileNotFoundError:
            fingerprint["stopwords_md5"] = "builtin"

        raw = json.dumps(fingerprint, sort_keys=True, ensure_ascii=False)
        return hashlib.md5(raw.encode()).hexdigest()[:12]

    def build_corpus(self, papers=None):
        """
        构建语料：对每篇论文的 title + abstract 进行分词。
        返回: list of str (分词后的文档)
        """
        from models import Paper

        if papers is None:
            papers = Paper.query.filter(Paper.abstract.isnot(None)).all()

        corpus = []
        for paper in papers:
            text = (paper.title or "") + "。" + (paper.abstract or "")
            words = tokenize(text, remove_stopwords=True)
            if words:
                corpus.append(" ".join(words))

        return corpus

    def extract_keywords_keybert(self, papers=None, top_n=5):
        """使用 KeyBERT 语义提取每篇论文的关键词（优先方案）。

        返回:
            dict: {paper_id: [(keyword, score), ...]}，不可用时返回空 dict
        """
        from models import Paper
        from keybert_extractor import get_keybert_extractor

        extractor = get_keybert_extractor()
        if not extractor.available:
            return {}

        if papers is None:
            papers = Paper.query.filter(Paper.abstract.isnot(None)).all()

        # 构建文档列表
        documents = []
        for paper in papers:
            text = (paper.title or "") + " " + (paper.abstract or "")
            if text.strip():
                documents.append((paper.id, text))

        if not documents:
            return {}

        logger.info("使用 KeyBERT 提取 %d 篇论文的关键词...", len(documents))
        result = extractor.extract_keywords_batch(documents, top_n=top_n)
        logger.info("KeyBERT 成功提取 %d 篇论文的关键词", len(result))
        return result

    def extract_keywords_tfidf(self, papers=None, top_n=5):
        """
        使用 TF-IDF 提取每篇论文的关键词（回退方案）。
        返回:
            dict: {paper_id: [(keyword, tfidf_score), ...]}
        """
        from models import Paper

        if papers is None:
            papers = Paper.query.filter(Paper.abstract.isnot(None)).all()

        if len(papers) < 2:
            return {}

        # 构建语料
        corpus = self.build_corpus(papers)
        paper_ids = [p.id for p in papers]

        # TF-IDF 向量化
        vectorizer = TfidfVectorizer(
            max_features=5000,
            min_df=1,
            max_df=0.9,
            token_pattern=r'(?u)\b\w+\b',
        )

        try:
            tfidf_matrix = vectorizer.fit_transform(corpus)
        except ValueError:
            return {}

        feature_names = vectorizer.get_feature_names_out()

        # 提取每篇论文的 top-N 关键词
        paper_keywords = {}
        for i, paper_id in enumerate(paper_ids):
            row = tfidf_matrix[i].toarray().flatten()
            top_indices = row.argsort()[-top_n:][::-1]
            keywords = [
                (feature_names[idx], float(row[idx]))
                for idx in top_indices
                if row[idx] > 0 and len(feature_names[idx]) >= 2
            ]
            paper_keywords[paper_id] = keywords

        return paper_keywords

    @property
    def keybert_enabled(self):
        """检查 KeyBERT 功能开关"""
        import os
        return os.environ.get("KEYBERT_ENABLED", "1") == "1"

    def get_all_keywords(self, papers=None):
        """
        获取所有论文的关键词（KeyBERT 优先，TF-IDF 回退）。
        返回:
            dict: {paper_id: [keyword1, keyword2, ...]}
        """
        # ── 路径 1：KeyBERT 语义提取 ──
        if self.keybert_enabled:
            paper_kw = self.extract_keywords_keybert(papers)
            if paper_kw:
                return {pid: [kw[0] for kw in kws] for pid, kws in paper_kw.items()}

        # ── 路径 2：TF-IDF 回退 ──
        logger.info("KeyBERT 不可用，回退到 TF-IDF 关键词提取")
        paper_kw = self.extract_keywords_tfidf(papers)
        return {pid: [kw[0] for kw in kws] for pid, kws in paper_kw.items()}

    def compute_heatmap(self, papers=None, force_refresh=False):
        """
        计算关键词的热度矩阵（带数据库缓存）。

        当 force_refresh=False 且论文数量未变时，直接返回缓存的 JSON 结果，
        避免全量分词和 TF-IDF 重算。

        返回:
            dict: {
                "keywords": [kw1, kw2, ...],
                "years": [2018, 2019, ...],
                "heatmap": {kw: {year: heat, ...}, ...},
                "all_keywords_list": [...],
            }
        """
        from models import Paper, KeywordCache

        if papers is None:
            papers = Paper.query.filter(Paper.abstract.isnot(None)).all()

        if not papers:
            return {"keywords": [], "years": [], "heatmap": {}, "all_keywords_list": []}

        paper_count = len(papers)

        # ── 尝试从缓存读取 ──
        config_ver = self._config_version()
        if not force_refresh:
            cache = KeywordCache.query.filter_by(cache_key="heatmap").first()
            if (
                cache
                and cache.paper_count == paper_count
                and cache.config_version == config_ver
            ):
                try:
                    return json.loads(cache.cache_data)
                except (json.JSONDecodeError, TypeError):
                    logger.warning("关键词缓存数据损坏，将重新计算")

        logger.info("关键词热力图缓存未命中（论文数=%d），正在重新计算...", paper_count)

        # 获取每篇论文的关键词
        paper_keywords = self.get_all_keywords(papers)

        # 收集所有论文的年-关键词数据
        year_papers = defaultdict(list)  # year -> [paper_id, ...]
        paper_year = {}

        for paper in papers:
            if paper.year:
                year_papers[paper.year].append(paper.id)
                paper_year[paper.id] = paper.year

        years = sorted(year_papers.keys())

        # 收集所有唯一关键词
        all_keywords = set()
        for kws in paper_keywords.values():
            all_keywords.update(kws)

        # 保留所有关键词（跨学科论文关键词重叠少，放宽过滤条件）
        kw_paper_count = defaultdict(int)
        for paper_id, kws in paper_keywords.items():
            for kw in kws:
                kw_paper_count[kw] += 1

        # 保留所有关键词，但标记出现频次
        filtered_keywords = sorted(all_keywords, key=lambda kw: kw_paper_count.get(kw, 0), reverse=True)

        # 构建热度矩阵
        heatmap = {}
        for kw in filtered_keywords:
            heatmap[kw] = {}
            for year in years:
                total = len(year_papers[year])
                # 计算该年有此关键词的论文数（无论论文数量多少都展示）
                count = sum(
                    1 for pid in year_papers[year]
                    if kw in paper_keywords.get(pid, [])
                )
                heatmap[kw][year] = round(count / total, 4) if total > 0 else 0.0

        # 可选：3点移动平均平滑
        for kw in filtered_keywords:
            values = [heatmap[kw][y] for y in years]
            smoothed = self._moving_average(values, window=3)
            for i, year in enumerate(years):
                if heatmap[kw][year] is not None:
                    heatmap[kw][year] = round(smoothed[i], 4)

        result = {
            "keywords": filtered_keywords,
            "years": years,
            "heatmap": heatmap,
            "all_keywords_list": sorted(all_keywords),
        }

        # ── 写入缓存 ──
        from models import KeywordCache, db
        from datetime import datetime, timezone
        cache = KeywordCache.query.filter_by(cache_key="heatmap").first()
        if not cache:
            cache = KeywordCache(cache_key="heatmap")
            db.session.add(cache)
        cache.cache_data = json.dumps(result, ensure_ascii=False)
        cache.paper_count = paper_count
        cache.config_version = config_ver
        cache.updated_at = datetime.now(timezone.utc)
        db.session.commit()
        logger.info("关键词热力图缓存已更新（%d 篇论文，%.1f KB）",
                     paper_count, len(cache.cache_data) / 1024)

        return result

    def get_top_keywords(self, n=20):
        """
        获取热度排名 TOP N 的关键词。
        返回: [(keyword, avg_heat), ...]
        """
        data = self.compute_heatmap()
        heatmap = data["heatmap"]

        avg_heats = []
        for kw, year_heats in heatmap.items():
            valid_heats = [h for h in year_heats.values() if h is not None]
            if valid_heats:
                avg_heat = sum(valid_heats) / len(valid_heats)
                avg_heats.append((kw, round(avg_heat, 4)))

        avg_heats.sort(key=lambda x: x[1], reverse=True)
        return avg_heats[:n]

    def get_trend_data(self, selected_keywords):
        """
        获取指定关键词的时序数据（供 Plotly 使用）。
        返回:
            list of dict: [
                {"keyword": kw, "x": [years], "y": [heats], "avg": float},
                ...
            ]
        """
        data = self.compute_heatmap()
        heatmap = data["heatmap"]
        # JSON 序列化会将整数年份转为字符串，统一转回 int 后再查找
        years = [int(y) if isinstance(y, str) else y for y in data["years"]]

        result = []
        for kw in selected_keywords:
            if kw in heatmap:
                year_heats = heatmap[kw]
                x_vals = []
                y_vals = []
                for year in years:
                    # JSON 缓存后 heatmap 的 key 可能变成字符串，同时匹配 int 和 str
                    heat = year_heats.get(year) or year_heats.get(str(year))
                    if heat is not None:
                        x_vals.append(year)
                        y_vals.append(float(heat))

                if x_vals:
                    avg = sum(y_vals) / len(y_vals)
                    result.append({
                        "keyword": kw,
                        "x": x_vals,
                        "y": y_vals,
                        "avg": round(avg, 4),
                    })

        return result

    def predict_trend(self, keyword, forecast_years=2):
        """基于历史热度数据，用线性回归预测未来趋势。

        参数:
            keyword: 关键词
            forecast_years: 预测未来年数（默认 2）

        返回:
            dict: {
                "keyword": str,
                "historical": {"x": [years], "y": [heats]},
                "forecast": {"x": [future_years], "y": [predictions]},
                "slope": float,           # 趋势斜率（正=上升，负=下降）
                "trend_direction": str,   # "rising" | "falling" | "stable"
                "r2_score": float,        # 拟合优度
            }
            或 None（数据不足时）
        """
        trend_data = self.get_trend_data([keyword])
        if not trend_data:
            return None

        series = trend_data[0]
        years = series["x"]
        heats = series["y"]

        if len(years) < 3:
            return None

        from sklearn.linear_model import LinearRegression, Ridge

        X = np.array(years).reshape(-1, 1)
        y = np.array(heats)

        # 使用 Ridge 回归防过拟合（仅 3-7 个数据点时普通 LR 可能不稳定）
        if len(years) < 6:
            model = Ridge(alpha=0.5)
        else:
            model = LinearRegression()
        model.fit(X, y)

        # 预测未来
        last_year = max(years)
        future_years = list(range(last_year + 1, last_year + 1 + forecast_years))
        future_X = np.array(future_years).reshape(-1, 1)
        predictions = model.predict(future_X)

        # 预测值裁剪到 [0, 1] 范围
        predictions = np.clip(predictions, 0, 1).tolist()

        # 拟合优度
        r2 = model.score(X, y)

        # 趋势方向
        slope = float(model.coef_[0]) if hasattr(model, 'coef_') else 0.0
        if slope > 0.02:
            direction = "rising"
        elif slope < -0.02:
            direction = "falling"
        else:
            direction = "stable"

        return {
            "keyword": keyword,
            "historical": {"x": years, "y": heats},
            "forecast": {"x": future_years, "y": [round(v, 4) for v in predictions]},
            "slope": round(slope, 6),
            "trend_direction": direction,
            "r2_score": round(float(r2), 4),
        }

    def compute_river_chart(self, top_n=6):
        """计算关键词热度的堆叠面积图数据（河流图）。

        展示 TOP N 关键词在各年份的热度占比（而非绝对值），
        直观反映主题间的此消彼长关系。

        返回:
            dict: {
                "years": [2018, ...],
                "keywords": [kw1, ...],
                "series": [{keyword, x, y}, ...],  # 适合 Plotly 堆叠区域图
            }
        """
        data = self.compute_heatmap()
        heatmap = data["heatmap"]
        years = [int(y) if isinstance(y, str) else y for y in data["years"]]
        all_kw = data["keywords"]

        if len(all_kw) < 2 or len(years) < 2:
            return {"years": years, "keywords": all_kw, "series": []}

        # 取 TOP N 热度关键词
        kw_avg = []
        for kw in all_kw:
            vals = [heatmap[kw].get(y, 0) or heatmap[kw].get(str(y), 0)
                    for y in years]
            kw_avg.append((kw, sum(vals) / len(vals)))
        kw_avg.sort(key=lambda x: x[1], reverse=True)
        top_kw = [kw for kw, _ in kw_avg[:top_n]]

        # 构建占比序列
        series = []
        for kw in top_kw:
            y_vals = []
            for y in years:
                v = heatmap[kw].get(y, 0) or heatmap[kw].get(str(y), 0)
                y_vals.append(round(float(v or 0), 4))
            series.append({"keyword": kw, "x": years, "y": y_vals})

        return {"years": years, "keywords": top_kw, "series": series}

    def trace_method_migration(self, method_keyword, min_year=2015):
        """追踪一个核心方法在不同学科中的首次出现时间。

        构建"方法传播时间线"——展示该方法从哪个学科起源，
        随后被哪些学科采纳。

        参数:
            method_keyword: 方法名（如 'attention' | 'diffusion' | 'transformer'）
            min_year: 最早考虑年份

        返回:
            dict: {
                "keyword": str,
                "migration": [{category, first_year, paper_count, sample_title}, ...]
            }
        """
        from models import Paper

        papers = (
            Paper.query
            .filter(Paper.abstract.isnot(None))
            .filter(Paper.abstract.contains(method_keyword))
            .filter(Paper.year >= min_year)
            .order_by(Paper.year)
            .all()
        )

        if not papers:
            return {"keyword": method_keyword, "migration": []}

        # 按学科分组
        cat_stats = defaultdict(list)
        for p in papers:
            cat = p.category or "unknown"
            cat_stats[cat].append(p)

        migration = []
        for cat, cat_papers in cat_stats.items():
            years = sorted(set(p.year for p in cat_papers if p.year))
            first_year = years[0] if years else None
            sample = cat_papers[0] if cat_papers else None
            migration.append({
                "category": cat,
                "first_year": first_year,
                "paper_count": len(cat_papers),
                "sample_title": (sample.title or "")[:80] if sample else "",
                "sample_year": sample.year if sample else None,
            })

        # 按首次出现年份排序 → 得到迁移路径
        migration.sort(key=lambda x: x["first_year"] or 9999)

        return {
            "keyword": method_keyword,
            "migration": migration,
            "total_papers": len(papers),
        }

    @staticmethod
    def invalidate_cache():
        """清除关键词热力图缓存（论文增删后调用）。"""
        try:
            from models import db, KeywordCache
            KeywordCache.query.filter_by(cache_key="heatmap").delete()
            db.session.commit()
            logger.info("关键词热力图缓存已清除（将在下次查询时自动重建）")
        except Exception:
            logger.warning("清除关键词缓存失败", exc_info=True)

    def _moving_average(self, values, window=3):
        """3点移动平均平滑（首尾保持不变）"""
        if len(values) < window:
            return values

        smoothed = values[:]
        half = window // 2

        for i in range(half, len(values) - half):
            window_vals = [
                v for v in values[i - half:i + half + 1]
                if v is not None
            ]
            if window_vals:
                smoothed[i] = sum(window_vals) / len(window_vals)

        return smoothed


# ── SQLAlchemy 事件：论文表变更时自动失效全部派生数据 ──
def _on_paper_changed(mapper, connection, target):
    """论文插入/更新/删除后，一次性失效所有依赖该论文的缓存与派生数据。

    失效范围（与 V4 优化方案 P1 对齐）：
      1. 关键词热度缓存（heatmap）—— 论文增删改都会改变热度统计；
      2. 该论文的向量嵌入 PaperEmbedding —— 内容变化后旧向量作废；
      3. 以该论文为源或目标的推荐缓存 Recommendation —— 否则残留脏数据；
      4. Recommender 的 TF-IDF 内存矩阵 —— 触发下次请求重建。
    """
    from models import KeywordCache, PaperEmbedding, Recommendation
    paper_id = getattr(target, "id", None)
    try:
        # 1. 关键词热度缓存（全量失效，简单可靠）
        connection.execute(
            KeywordCache.__table__.delete().where(
                KeywordCache.cache_key == "heatmap"
            )
        )
        # 2-3. 该论文的向量嵌入 + 相关推荐缓存
        if paper_id is not None:
            connection.execute(
                PaperEmbedding.__table__.delete().where(
                    PaperEmbedding.paper_id == paper_id
                )
            )
            connection.execute(
                Recommendation.__table__.delete().where(
                    (Recommendation.source_paper_id == paper_id)
                    | (Recommendation.target_paper_id == paper_id)
                )
            )
    except Exception:
        logger.warning(
            "派生数据自动失效失败（嵌入/推荐/热度缓存将按需重建）",
            exc_info=True,
        )

    # 4. Recommender 的 TF-IDF 矩阵（进程内缓存，失效后下次请求重建）
    try:
        from routes.helpers import get_recommender
        recommender = get_recommender()
        recommender._tfidf_matrix = None
        recommender._tfidf_paper_ids = None
    except Exception:
        logger.debug("TF-IDF 矩阵重置失败（将于下次请求时惰性重建）", exc_info=True)


def _register_cache_invalidation():
    """注册缓存失效事件监听（在 app 上下文中调用一次）。"""
    from sqlalchemy import event
    from models import Paper
    event.listen(Paper, "after_insert", _on_paper_changed)
    event.listen(Paper, "after_update", _on_paper_changed)
    event.listen(Paper, "after_delete", _on_paper_changed)
