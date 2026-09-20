"""
LLM 大语言模型统一客户端。

优先级：DeepSeek API（主力）→ 规则引擎（兜底）

DeepSeek API 兼容 OpenAI SDK，对 JSON 结构化输出支持优秀，
特别适合创新点的 {problem, method, effect} 格式提取。
"""

import hashlib
import json
import logging
import time
import re
from collections import OrderedDict

logger = logging.getLogger("InnoCite.LLM")


class LLMClient:
    """LLM 统一调用客户端。

    自动检测可用后端：
    1. DeepSeek API（远程，兼容 OpenAI SDK）
    2. 不可用（调用方回退到规则引擎）

    内置 LRU 风格响应缓存，避免重复 API 调用。
    """

    # 缓存上限
    _CACHE_MAX_SIZE = 200

    # 创新点提取 Prompt
    INNOVATION_SYSTEM_PROMPT = """你是一个学术论文分析专家。请通读论文的摘要与正文（Introduction / Method / Experiments / Conclusion），从中精确提取"问题-方法-效果"三维创新点。

要求：
1. 每个维度一句话概括，简洁精准，不超过200字
2. 优先从正文中寻找更具体的方法细节和实验数据（摘要可能省略细节）
3. 保留原文中的关键技术术语和性能指标
4. 如果某维度无法从摘要或正文中提取，填写"待补充"
5. 严格按JSON格式输出，不要添加额外解释"""

    INNOVATION_USER_PROMPT = """论文标题：{title}
论文摘要：{abstract}
{full_text_section}
请提取该论文的创新点，输出JSON格式：
{{"problem": "...", "method": "...", "effect": "..."}}"""

    # 推荐理由生成 Prompt
    REASON_SYSTEM_PROMPT = """你是一个跨学科学术推荐专家。为推荐结果撰写简洁有力的推荐理由。

要求：
- 80字以内
- 指出被推荐论文的方法如何启发源领域的问题
- 使用具体的学术术语"""

    REASON_USER_PROMPT = """源论文（{source_category}领域）：{source_title}
源论文要解决的问题：{source_problem}

推荐论文（{target_category}领域）：{target_title}
推荐论文的核心方法：{target_method}

请生成跨学科推荐理由（80字以内）："""

    # 论文分类 Prompt
    CLASSIFY_SYSTEM_PROMPT = """你是一个学术论文学科分类专家。根据论文标题和摘要判断其所属学科。

可选学科：计算机视觉(cs.CV)、自然语言处理(cs.CL)、机器学习(cs.LG)、
人工智能(cs.AI)、信息检索(cs.IR)、机器人学(cs.RO)、人机交互(cs.HC)、
神经网络(cs.NE)

只输出学科代码（如 cs.CV），不要其他内容。"""

    CLASSIFY_USER_PROMPT = """标题：{title}
摘要：{abstract}

学科代码："""

    # 文献综述生成 Prompt
    REVIEW_SYSTEM_PROMPT = """你是一个学术文献综述专家。请根据提供的论文发展脉络，撰写一段专业的文献综述。

要求：
1. 按时间线梳理关键发展和突破
2. 分析该方向的核心挑战和解决思路
3. 总结当前趋势和未来可能方向
4. 500-800 字，学术风格但清晰易懂
5. 使用 Markdown 格式，包含小标题"""

    REVIEW_USER_PROMPT = """主题：{topic}

该方向的论文发展脉络：
{timeline}

请撰写文献综述："""

    def __init__(self, app_config=None):
        self._config = app_config or {}
        self._client = None
        self._active_backend = None
        self._checked = False
        self._available = None
        self._cache = OrderedDict()  # LRU 风格响应缓存

    def _cache_key(self, *parts):
        """生成缓存键（MD5 哈希）。"""
        raw = "||".join(str(p)[:500] for p in parts)
        return hashlib.md5(raw.encode()).hexdigest()

    def _cache_get(self, key, cache_type="general"):
        """从缓存读取。

        内存命中时返回并移到末尾（LRU）；
        内存未命中时回查数据库持久化缓存并回填内存（重启后仍可命中）。
        """
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        # 内存未命中 → 回查数据库
        value = self._cache_load_db(key)
        if value is not None:
            self._cache[key] = value
            self._cache.move_to_end(key)
            logger.debug("LLM 缓存命中（数据库回填）")
            return value
        return None

    def _cache_set(self, key, value, cache_type="general"):
        """写入缓存，超出上限时淘汰最旧条目（LRU），并持久化到数据库。"""
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = value
        while len(self._cache) > self._CACHE_MAX_SIZE:
            self._cache.popitem(last=False)
        # 持久化到数据库（失败不影响主流程）
        self._cache_save_db(key, value, cache_type)

    # ── 数据库持久化 ────────────────────────

    @staticmethod
    def _has_db_context():
        """判断当前线程是否存在 Flask 应用上下文（落库的前提）。"""
        try:
            from flask import has_app_context
            return has_app_context()
        except ImportError:
            return False

    def _cache_load_db(self, key):
        """从数据库加载持久化缓存（无 app context 时跳过）。"""
        if not self._has_db_context():
            return None
        try:
            from models import db, LLMCache
            record = LLMCache.query.filter_by(cache_key=key).first()
            if record:
                return json.loads(record.cache_data)
        except Exception:
            logger.debug("LLM 持久化缓存读取失败", exc_info=True)
        return None

    def _cache_save_db(self, key, value, cache_type):
        """将缓存写入数据库（幂等 upsert；无 app context 或失败时静默跳过）。"""
        if not self._has_db_context():
            return
        try:
            from models import db, LLMCache
            record = LLMCache.query.filter_by(cache_key=key).first()
            serialized = json.dumps(value, ensure_ascii=False)
            if record:
                record.cache_data = serialized
                record.cache_type = cache_type
            else:
                db.session.add(LLMCache(
                    cache_key=key,
                    cache_type=cache_type,
                    cache_data=serialized,
                ))
            db.session.commit()
        except Exception:
            logger.debug("LLM 持久化缓存写入失败", exc_info=True)
            try:
                db.session.rollback()
            except Exception:
                pass

    # ── 属性读取 ────────────────────────────

    def _cfg(self, key, default=None):
        """安全读取配置值（config 对象 > 环境变量 > 默认值）"""
        val = default
        if hasattr(self._config, 'get'):
            val = self._config.get(key, default)
        elif isinstance(self._config, dict):
            val = self._config.get(key, default)
        # 回退到环境变量
        import os
        return val if val != default else os.environ.get(key, default)

    @property
    def available(self):
        """检测 DeepSeek API 是否可用（仅在首次调用时检测）"""
        if not self._checked:
            self._active_backend = self._detect_backend()
            self._checked = True
            self._available = self._active_backend is not None
            if self._available:
                logger.info("LLM 后端已就绪: %s", self._active_backend)
            else:
                logger.info("DeepSeek API 未配置，将使用规则引擎回退")
        return self._available

    @property
    def active_backend(self):
        """返回当前使用的后端名称"""
        self.available
        return self._active_backend

    # ── 后端检测 ────────────────────────────

    def _detect_backend(self):
        """检测可用的 LLM 后端"""
        backend = self._cfg("LLM_BACKEND", "auto")

        if backend == "off":
            return None
        if backend == "auto":
            return "deepseek" if self._cfg("DEEPSEEK_API_KEY") else None

        return None

    # ── 核心调用方法 ──────────────────────────

    def _call_deepseek(self, system_prompt, user_prompt, temperature=None,
                       response_format=None, model=None):
        """调用 DeepSeek API（兼容 OpenAI SDK）

        参数:
            model: 指定模型，为 None 时使用默认 flash 模型
        """
        from openai import OpenAI

        api_key = self._cfg("DEEPSEEK_API_KEY")
        base_url = self._cfg("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        timeout = self._cfg("LLM_TIMEOUT", 30)
        temp = temperature if temperature is not None else self._cfg("LLM_TEMPERATURE", 0.3)

        # 选择模型：未指定时用 flash（快速任务），pro 用于深度推理
        if model is None:
            model = self._cfg("DEEPSEEK_MODEL", "deepseek-v4-flash")

        client = OpenAI(api_key=api_key, base_url=base_url)
        kwargs = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temp,
            "max_tokens": 1024,
            "timeout": timeout,
        }
        if response_format:
            kwargs["response_format"] = response_format

        response = client.chat.completions.create(**kwargs)
        return response.choices[0].message.content.strip()

    def _call_llm(self, system_prompt, user_prompt, temperature=None,
                  response_format=None, model=None):
        """统一 LLM 调用入口，内置重试"""
        if not self.available:
            return None

        max_retries = self._cfg("LLM_MAX_RETRIES", 2)
        last_error = None

        for attempt in range(max_retries + 1):
            try:
                return self._call_deepseek(
                    system_prompt, user_prompt, temperature, response_format, model
                )
            except Exception as e:
                last_error = e
                logger.warning(
                    "DeepSeek API 调用失败 (模型=%s, 尝试=%d/%d): %s",
                    model or self._cfg("DEEPSEEK_MODEL", "deepseek-v4-flash"),
                    attempt + 1, max_retries + 1, e
                )
                if attempt < max_retries:
                    time.sleep(1 * (attempt + 1))
                continue

        logger.error("DeepSeek API 调用最终失败: %s", last_error)
        return None

    # ── 公共 API ────────────────────────────

    def extract_innovation(self, title, abstract, full_text=None):
        """从论文标题、摘要和正文中提取创新点（通篇分析）。

        参数:
            title: 论文标题
            abstract: 论文摘要
            full_text: 论文正文（可选）。提供后按章节截断注入 prompt，
                       LLM 可从中提取更具体的方法与实验细节。

        返回:
            dict: {"problem": str, "method": str, "effect": str} 或 None（需回退）
        """
        if not abstract:
            return None

        # ── 缓存检查（基于标题+摘要+正文哈希）──
        cache_key = self._cache_key(title, abstract, full_text or "", "innovation")
        cached = self._cache_get(cache_key, "innovation")
        if cached is not None:
            logger.debug("LLM 创新点缓存命中")
            return cached

        # 正文分节注入（截断控制 token 成本）
        full_text_section = ""
        if full_text and len(full_text.strip()) > 50:
            # 按章节截断：每节最多 1200 字符，总计最多 3600 字符
            sections = self._split_full_text(full_text)
            section_lines = []
            budget = 3600
            for name, body in sections:
                if budget <= 0:
                    break
                chunk = body[:1200].strip()
                if chunk:
                    section_lines.append(f"[{name}]\n{chunk}")
                    budget -= len(chunk)
            full_text_section = (
                "论文正文（节选）：\n" + "\n\n".join(section_lines)
            ) if section_lines else ""

        user_prompt = self.INNOVATION_USER_PROMPT.format(
            title=title or "未知标题",
            abstract=abstract[:4000],
            full_text_section=full_text_section,
        )

        # 创新点提取使用 pro 模型（深度推理，精准结构化）
        pro_model = self._cfg("DEEPSEEK_MODEL_PRO", "deepseek-v4-pro")
        raw = self._call_llm(
            self.INNOVATION_SYSTEM_PROMPT,
            user_prompt,
            temperature=0.2,
            response_format={"type": "json_object"},
            model=pro_model,
        )

        result = self._parse_innovation_json(raw) if raw else None
        if result is not None:
            self._cache_set(cache_key, result, "innovation")
        return result

    @staticmethod
    def _split_full_text(full_text):
        """将论文正文按章节拆分为 [(章节名, 内容), ...]。

        识别 Introduction / Method / Experiments / Conclusion 等常见章节标题，
        无法识别时整段作为一个 Method 节处理。
        """
        import re as _re
        # 章节标题模式：数字序号 + 标题（如 "1. Introduction"），标题独占一行或后跟冒号
        pattern = _re.compile(
            r"(?m)^\s*(?:\d+\.?\s*)?(Introduction|Background|Related Work|"
            r"Method|Approach|Framework|Model|Experiments|Results|Evaluation|"
            r"Discussion|Conclusion|Analysis)\b[:\s]*$",
            _re.IGNORECASE,
        )
        matches = list(pattern.finditer(full_text))
        sections = []
        if matches:
            for i, m in enumerate(matches):
                name = m.group(1).strip()
                start = m.start()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(full_text)
                body = full_text[start:end]
                sections.append((name, body.strip()))
        else:
            sections.append(("FullText", full_text.strip()))
        return sections

    def _parse_innovation_json(self, raw_text):
        """从 LLM 响应中解析创新点 JSON"""
        try:
            data = json.loads(raw_text)
            return {
                "problem": data.get("problem", "待补充")[:500],
                "method": data.get("method", "待补充")[:500],
                "effect": data.get("effect", "待补充")[:500],
            }
        except json.JSONDecodeError:
            pass

        # 尝试从文本中提取 JSON 块
        json_match = re.search(r'\{[^{}]*"problem"[^{}]*\}', raw_text, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group())
                return {
                    "problem": data.get("problem", "待补充")[:500],
                    "method": data.get("method", "待补充")[:500],
                    "effect": data.get("effect", "待补充")[:500],
                }
            except json.JSONDecodeError:
                pass

        logger.warning("无法从 LLM 响应中解析 JSON: %s", raw_text[:200])
        return None

    def generate_recommendation_reason(self, source_paper, target_paper):
        """生成跨学科推荐理由。

        返回:
            str: 推荐理由，或 None（需回退）
        """
        source_innovation = source_paper.innovation
        target_innovation = target_paper.innovation

        source_problem = (
            source_innovation.problem
            if source_innovation and source_innovation.problem != "待补充"
            else "未明确提取"
        )
        target_method = (
            target_innovation.get_method_short(100)
            if target_innovation and target_innovation.method != "待补充"
            else "未明确提取"
        )

        # ── 缓存检查 ──
        cache_key = self._cache_key(
            source_paper.id, target_paper.id, "reason"
        )
        cached = self._cache_get(cache_key, "reason")
        if cached is not None:
            logger.debug("LLM 推荐理由缓存命中")
            return cached

        user_prompt = self.REASON_USER_PROMPT.format(
            source_category=source_paper.category or "未知",
            source_title=(source_paper.title or "")[:100],
            source_problem=source_problem[:150],
            target_category=target_paper.category or "未知",
            target_title=(target_paper.title or "")[:100],
            target_method=target_method[:150],
        )

        raw = self._call_llm(self.REASON_SYSTEM_PROMPT, user_prompt, temperature=0.5)

        result = raw[:200] if (raw and len(raw) >= 10) else None
        if result is not None:
            self._cache_set(cache_key, result, "reason")
        return result

    def classify_paper(self, title, abstract):
        """自动对论文进行学科分类。

        返回:
            str: 学科代码（如 cs.CV），或 None
        """
        user_prompt = self.CLASSIFY_USER_PROMPT.format(
            title=title or "未知标题",
            abstract=(abstract or "")[:1500],
        )

        raw = self._call_llm(self.CLASSIFY_SYSTEM_PROMPT, user_prompt, temperature=0.1)

        if raw:
            raw = raw.strip().rstrip('.。')
            match = re.search(r'(cs\.[A-Z]{2,3}|stat\.[A-Z]{2,3}|math\.[A-Z]{2,3})', raw)
            if match:
                return match.group(1)
        return None

    def generate_literature_review(self, topic, papers_data):
        """为指定主题自动生成文献综述草稿。

        参数:
            topic: 综述主题关键词
            papers_data: list of dict，每个包含 title/year/innovation/problem/method/effect

        返回:
            str: Markdown 格式的文献综述，或 None（需回退）
        """
        if not papers_data or not self.available:
            return None

        # 构建时间线
        lines = []
        for p in sorted(papers_data, key=lambda x: x.get("year") or 0):
            year = p.get("year", "?")
            title = (p.get("title") or "未知")[:80]
            method = ""
            if p.get("innovation") and isinstance(p["innovation"], dict):
                method = p["innovation"].get("method", "")
                if not method or method == "待补充":
                    method = p["innovation"].get("problem", "")
            elif p.get("method"):
                method = p["method"]
            method = (method or "")[:100]
            lines.append(f"- **{year}** — *{title}* — {method}")

        timeline = "\n".join(lines)

        user_prompt = self.REVIEW_USER_PROMPT.format(
            topic=topic,
            timeline=timeline[:4000],
        )

        raw = self._call_llm(
            self.REVIEW_SYSTEM_PROMPT,
            user_prompt,
            temperature=0.5,
            model=self._cfg("DEEPSEEK_MODEL_PRO", "deepseek-v4-pro"),
        )

        if raw and len(raw) >= 100:
            return raw
        return None

    def check_availability(self):
        """检测后端可用性状态。

        返回:
            dict: {"deepseek": bool, "active": str|None}
        """
        return {
            "deepseek": bool(self._cfg("DEEPSEEK_API_KEY")),
            "active": self.active_backend,
        }


# ── 模块级单例 ──
_llm_client = None


def get_llm_client(app_config=None):
    """获取 LLM 客户端单例。

    参数:
        app_config: Flask 配置对象。为 None 时尝试从当前应用上下文
                    （flask.current_app.config）自动获取，避免调用方
                    因不传配置而拿到 None（如 paper_classifier 内部调用）。
    """
    global _llm_client
    if _llm_client is None:
        if app_config is None:
            try:
                from flask import current_app
                app_config = current_app.config
            except (RuntimeError, ImportError):
                app_config = None
        if app_config is not None:
            _llm_client = LLMClient(app_config)
    return _llm_client


def reset_llm_client():
    """重置 LLM 客户端（用于测试）"""
    global _llm_client
    _llm_client = None
