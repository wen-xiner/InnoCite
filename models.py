"""
SQLAlchemy 数据模型定义。
包含 Paper, Innovation, PaperEmbedding, Recommendation 四个模型。
"""

from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def _utcnow():
    """返回 UTC 时间，替代已废弃的 datetime.utcnow()"""
    return datetime.now(timezone.utc)


class Paper(db.Model):
    """论文元数据模型"""
    __tablename__ = "papers"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    arxiv_id = db.Column(db.String(50), nullable=True, index=True)
    title = db.Column(db.Text, nullable=False)
    authors = db.Column(db.Text, nullable=True)  # 分号分隔
    year = db.Column(db.Integer, nullable=True)
    venue = db.Column(db.String(255), nullable=True)
    abstract = db.Column(db.Text, nullable=True)
    full_text = db.Column(db.Text, nullable=True)
    category = db.Column(db.String(100), nullable=True, index=True)  # 如 cs.CV
    source_type = db.Column(db.String(20), default="arXiv")  # arXiv / CSV / PDF
    status = db.Column(db.String(20), default="success")  # success / failed
    created_at = db.Column(db.DateTime, default=_utcnow)

    # 关联
    innovation = db.relationship("Innovation", backref="paper", uselist=False, cascade="all, delete-orphan")
    embedding = db.relationship("PaperEmbedding", backref="paper", uselist=False, cascade="all, delete-orphan")

    def get_authors_list(self):
        """返回作者列表"""
        if self.authors:
            return [a.strip() for a in self.authors.split(";") if a.strip()]
        return []

    def set_authors_list(self, authors):
        """设置作者列表"""
        if isinstance(authors, list):
            self.authors = "; ".join(authors)
        else:
            self.authors = str(authors)

    def to_dict(self):
        return {
            "id": self.id,
            "arxiv_id": self.arxiv_id,
            "title": self.title,
            "authors": self.get_authors_list(),
            "year": self.year,
            "venue": self.venue,
            "abstract": self.abstract[:300] + "..." if self.abstract and len(self.abstract) > 300 else self.abstract,
            "category": self.category,
            "source_type": self.source_type,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def to_dict_full(self):
        d = self.to_dict()
        d["abstract"] = self.abstract
        d["full_text"] = self.full_text
        if self.innovation:
            d["innovation"] = self.innovation.to_dict()
        return d


class Innovation(db.Model):
    """创新点模型"""
    __tablename__ = "innovations"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    paper_id = db.Column(db.Integer, db.ForeignKey("papers.id"), nullable=False, unique=True)
    problem = db.Column(db.Text, default="待补充")
    method = db.Column(db.Text, default="待补充")
    effect = db.Column(db.Text, default="待补充")
    full_statement = db.Column(db.Text, default="")
    confidence = db.Column(db.Float, default=0.0)
    is_verified = db.Column(db.Boolean, default=False)
    updated_at = db.Column(db.DateTime, default=_utcnow)

    def build_full_statement(self):
        """构建完整的创新点陈述语句"""
        parts = []
        if self.problem and self.problem != "待补充":
            parts.append(f"【问题】{self.problem}")
        if self.method and self.method != "待补充":
            parts.append(f"【方法】{self.method}")
        if self.effect and self.effect != "待补充":
            parts.append(f"【效果】{self.effect}")
        self.full_statement = "；".join(parts) if parts else "待补充"

    def get_method_short(self, max_len=60):
        """获取方法简述（截取前N字符）"""
        if self.method and self.method != "待补充":
            return self.method[:max_len] + ("..." if len(self.method) > max_len else "")
        return "未提取方法"

    def to_dict(self):
        return {
            "id": self.id,
            "paper_id": self.paper_id,
            "problem": self.problem,
            "method": self.method,
            "effect": self.effect,
            "full_statement": self.full_statement,
            "confidence": round(self.confidence, 2),
            "is_verified": self.is_verified,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "method_short": self.get_method_short(),
        }


class PaperEmbedding(db.Model):
    """论文向量存储模型（预计算缓存）"""
    __tablename__ = "paper_embeddings"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    paper_id = db.Column(db.Integer, db.ForeignKey("papers.id"), nullable=False, unique=True, index=True)
    embedding = db.Column(db.LargeBinary, nullable=False)  # float32 二进制存储（维度由 SBERT 模型动态决定，如 all-MiniLM-L6-v2 为 384 维）
    created_at = db.Column(db.DateTime, default=_utcnow)


class Recommendation(db.Model):
    """跨学科推荐结果缓存"""
    __tablename__ = "recommendations"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    source_paper_id = db.Column(db.Integer, db.ForeignKey("papers.id"), nullable=False, index=True)
    target_paper_id = db.Column(db.Integer, db.ForeignKey("papers.id"), nullable=False)
    similarity = db.Column(db.Float, nullable=False)
    reason = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow)

    __table_args__ = (
        db.UniqueConstraint("source_paper_id", "target_paper_id", name="uq_source_target"),
    )

    # 目标论文关联
    target_paper = db.relationship("Paper", foreign_keys=[target_paper_id])
    source_paper = db.relationship("Paper", foreign_keys=[source_paper_id])

    def to_dict(self):
        return {
            "id": self.id,
            "source_paper_id": self.source_paper_id,
            "target_paper_id": self.target_paper_id,
            "similarity": round(self.similarity, 4),
            "reason": self.reason,
            "target_title": self.target_paper.title if self.target_paper else "",
            "target_authors": self.target_paper.get_authors_list() if self.target_paper else [],
            "target_year": self.target_paper.year if self.target_paper else None,
            "target_category": self.target_paper.category if self.target_paper else "",
        }


class User(db.Model):
    """系统用户模型"""
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    display_name = db.Column(db.String(100), default="")
    is_active = db.Column(db.Boolean, default=True)
    is_admin = db.Column(db.Boolean, default=False)  # 管理员角色（管理接口鉴权）
    created_at = db.Column(db.DateTime, default=_utcnow)

    def set_password(self, password):
        """使用 werkzeug 安全哈希设置密码"""
        from werkzeug.security import generate_password_hash
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """验证密码是否匹配"""
        from werkzeug.security import check_password_hash
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "display_name": self.display_name,
            "is_active": self.is_active,
            "is_admin": self.is_admin,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ── 用户论文收藏关联表 ──
user_bookmarks = db.Table(
    "user_bookmarks",
    db.Column("user_id", db.Integer, db.ForeignKey("users.id"), primary_key=True),
    db.Column("paper_id", db.Integer, db.ForeignKey("papers.id"), primary_key=True),
    db.Column("created_at", db.DateTime, default=_utcnow),
)


class KeywordCache(db.Model):
    """关键词热力图缓存 — 避免每次请求都重算 TF-IDF。

    当且仅当论文数量或内容发生变化，或分词/停用词配置变更时触发重算。
    """
    __tablename__ = "keyword_cache"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    cache_key = db.Column(db.String(80), unique=True, nullable=False, index=True)
    cache_data = db.Column(db.Text, nullable=False)  # JSON 格式的完整热力图数据
    paper_count = db.Column(db.Integer, nullable=False, default=0)
    config_version = db.Column(db.String(16), nullable=True)  # 配置哈希，变更时自动失效
    updated_at = db.Column(db.DateTime, default=_utcnow)


class LLMCache(db.Model):
    """LLM 响应持久化缓存 — 重启不丢失，避免重复调用 API 产生费用。

    与 llm_client 的内存 LRU 缓存配合：内存命中直接返回；
    内存未命中时回查数据库并回填内存。仅在存在 Flask 应用上下文时
    落库（后台线程无上下文则跳过，仅内存缓存）。
    """
    __tablename__ = "llm_cache"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    cache_key = db.Column(db.String(64), unique=True, nullable=False, index=True)
    cache_type = db.Column(db.String(20), nullable=False, default="general")  # innovation / reason / ...
    cache_data = db.Column(db.Text, nullable=False)  # JSON 序列化后的响应
    created_at = db.Column(db.DateTime, default=_utcnow)
