"""
创新点智能提炼模块。

双轨策略：
  1. LLM 提取（优先）— DeepSeek API / Ollama 本地模型，精准理解论文语义
  2. 规则引擎（回退）— 触发词+正则，LLM 不可用时自动启用

LLM 对 JSON 结构化输出支持优秀，特别适合 {problem, method, effect} 格式提取；
规则引擎在无网络/无 API Key 时保证系统基础可用。
"""

import re
import logging
from utils import (
    tokenize_with_pos,
    split_sentences,
    find_conclusion_section,
    has_numeric_indicator,
    extract_noun_phrases,
    clean_text,
)

logger = logging.getLogger("InnoCite.InnovationExtractor")


class RuleInnovationExtractor:
    """基于规则引擎的创新点提取器（原有实现，作为 LLM 回退方案）"""

    # ─── 触发词词典 ───
    PROBLEM_TRIGGERS = [
        "challenge", "limitation", "issue", "unresolved", "cannot", "lack",
        "however", "difficult", "problem", "bottleneck", "suffer", "struggle",
        "hinders", "insufficient", "remains difficult", "remains a challenge",
        "limited by", "restricted by", "poor performance", "fails to",
        "shortcoming", "drawback", "deficiency", "gap",
        "瓶颈", "不足", "难以", "困难", "挑战", "问题", "局限",
        "无法", "缺乏", "缺失", "尚未解决", "仍存在", "制约",
        "缺陷", "不够", "有待", "无法满足", "需要解决",
    ]

    METHOD_TRIGGERS = [
        "propose", "introduce", "develop", "design", "employ", "use", "adopt",
        "present", "we propose", "we introduce", "we develop", "we design",
        "we present", "we employ", "we adopt", "our method", "our approach",
        "our framework", "the proposed", "this paper proposes",
        "this paper introduces", "this paper presents", "we describe",
        "we formulate", "we construct", "we build", "we implement",
        "提出", "采用", "设计", "引入", "构建", "实现", "开发",
        "我们提出", "本文提出", "本文采用", "我们设计", "我们构建",
        "该方法", "该框架", "该模型",
    ]

    EFFECT_TRIGGERS_PREFIX = [
        "achieve", "outperform", "improve", "increase", "reduce", "reach",
        "state-of-the-art", "SOTA", "surpass", "exceed", "boost",
        "our method achieves", "our approach achieves", "the proposed method achieves",
        "experiments demonstrate", "experimental results show", "results show",
        "we achieve", "we obtain", "we reach",
        "达到", "优于", "超过", "超越", "提升", "提高", "降低", "减少",
        "实验表明", "实验结果", "结果证明", "实现了",
    ]

    # 效果数值提取模式
    NUMERIC_EFFECT_PATTERN = re.compile(
        r'(?:'
        r'(?:accuracy|precision|recall|F1|BLEU|mAP|AUC|PSNR|SSIM|top-\d)\s*(?:of|:|=|is|达到|为)\s*\d+\.?\d*%?|'
        r'(?:achieve[sd]?\s*|reach(?:es|ed)?\s*|obtain[sd]?\s*)\s*\d+\.?\d*\s*%?|'
        r'(?:improve[sd]?\s*by|increase[sd]?\s*by|reduce[sd]?\s*by|boost[sd]?\s*by|提升|提高|降低|减少|增加)\s*\d+\.?\d*\s*%?|'
        r'(?:outperform[sd]?\s*(?:by|all|previous))|'
        r'(?:new\s*)?state-of-the-art|'
        r'(?:significant|substantial|remarkable)\s*(?:improvement|gain|boost)'
        r')',
        re.IGNORECASE
    )

    def extract(self, paper):
        """从 Paper 对象提取创新点（规则引擎）"""
        text_source = self._get_text_source(paper)
        if not text_source:
            return self._empty_result()

        sentences = split_sentences(text_source)
        problem = self._extract_problem(sentences, text_source)
        method = self._extract_method(sentences, text_source)
        effect = self._extract_effect(sentences, text_source)
        confidence = self.calculate_confidence(problem, method, effect)

        return {
            "problem": problem,
            "method": method,
            "effect": effect,
            "confidence": confidence,
            "source": "rule",  # 标记提取来源
        }

    def _empty_result(self):
        return {"problem": "待补充", "method": "待补充", "effect": "待补充",
                 "confidence": 0.0, "source": "rule"}

    def _get_text_source(self, paper):
        text_parts = []
        if paper.abstract:
            text_parts.append(paper.abstract)
        if paper.full_text:
            conclusion = find_conclusion_section(paper.full_text)
            if conclusion:
                text_parts.append(conclusion)
        return " ".join(text_parts)

    def _extract_problem(self, sentences, full_text):
        candidates = []
        full_text_lower = full_text.lower()
        for sentence in sentences:
            sent_lower = sentence.lower()
            for trigger in self.PROBLEM_TRIGGERS:
                if trigger.lower() in sent_lower:
                    phrases = extract_noun_phrases(sentence)
                    candidates.append((sentence, len(phrases)))
                    break
        if candidates:
            return candidates[0][0][:500]
        for trigger in ["challenge", "limitation", "however", "瓶颈", "不足"]:
            idx = full_text_lower.find(trigger.lower())
            if idx >= 0:
                start = max(0, idx - 100)
                end = min(len(full_text), idx + 400)
                return full_text[start:end].strip()[:500]
        return "待补充"

    def _extract_method(self, sentences, full_text):
        candidates = []
        full_text_lower = full_text.lower()
        for sentence in sentences:
            sent_lower = sentence.lower()
            for trigger in self.METHOD_TRIGGERS:
                if trigger.lower() in sent_lower:
                    candidates.append(sentence)
                    break
        if candidates:
            candidates.sort(key=len, reverse=True)
            return candidates[0][:500]
        for trigger in ["propose", "we propose", "提出", "本文提出"]:
            idx = full_text_lower.find(trigger.lower())
            if idx >= 0:
                start = max(0, idx - 50)
                end = min(len(full_text), idx + 450)
                return full_text[start:end].strip()[:500]
        return "待补充"

    def _extract_effect(self, sentences, full_text):
        candidates = []
        full_text_lower = full_text.lower()
        for sentence in sentences:
            sent_lower = sentence.lower()
            has_prefix = any(t.lower() in sent_lower for t in self.EFFECT_TRIGGERS_PREFIX)
            has_numeric = bool(self.NUMERIC_EFFECT_PATTERN.search(sentence))
            if has_prefix or has_numeric:
                candidates.append((sentence, has_numeric))
        if candidates:
            candidates.sort(key=lambda x: (x[1], len(x[0])), reverse=True)
            return candidates[0][0][:500]
        for trigger in ["achieve", "outperform", "reduced by", "improved by", "达到", "提升"]:
            idx = full_text_lower.find(trigger.lower())
            if idx >= 0:
                start = max(0, idx - 50)
                end = min(len(full_text), idx + 450)
                return full_text[start:end].strip()[:500]
        return "待补充"

    def calculate_confidence(self, problem, method, effect):
        """计算创新点提取置信度（公共 API）。

        规则：
        - 每提取一个维度 +1/3 基础分；
        - 效果含数值指标 +0.1；
        - 三维齐全且方法含多个名词短语 +0.05。

        供路由层（编辑后重算）与测试复用，替代原私有方法。
        """
        extracted = sum(1 for x in [problem, method, effect] if x != "待补充")
        base_score = extracted / 3.0
        if has_numeric_indicator(effect if effect != "待补充" else ""):
            base_score = min(base_score + 0.1, 1.0)
        if extracted == 3:
            method_phrases = extract_noun_phrases(method) if method != "待补充" else []
            if len(method_phrases) >= 2:
                base_score = min(base_score + 0.05, 1.0)
        return round(base_score, 2)


class InnovationExtractor:
    """创新点提取器（双轨制：LLM 优先 + 规则回退）

    用法：
        extractor = InnovationExtractor(app_config)
        result = extractor.extract(paper)
        # result: {"problem": ..., "method": ..., "effect": ..., "confidence": ..., "source": "llm"|"rule"}
    """

    def __init__(self, app_config=None):
        self._rule_extractor = RuleInnovationExtractor()
        self._app_config = app_config
        self._llm_client = None

    def _resolve_config(self):
        """解析配置：显式传入 > 当前应用上下文 > None。

        模块级实例化时不传 app_config（routes/helpers.py），若直接使用
        self._app_config 读取开关，会导致 LLM_INNOVATION_ENABLED 配置失效。
        统一在此解析，保证在任何时机都能读到当前应用配置；
        无应用上下文（后台线程）时返回 None，退化为默认行为。
        """
        if self._app_config is not None:
            return self._app_config
        try:
            from flask import current_app
            return current_app.config
        except (RuntimeError, ImportError):
            return None

    @property
    def llm_client(self):
        """延迟加载 LLM 客户端（可能为 None，需调用方判空）"""
        if self._llm_client is None:
            from llm_client import get_llm_client
            self._llm_client = get_llm_client(self._resolve_config())
        return self._llm_client

    @property
    def llm_enabled(self):
        """检查 LLM 功能是否启用（LLM 客户端不可用时自动回退到规则引擎）。

        不缓存：每次基于当前配置实时评估（LLMClient.available 内部有缓存，
        此处开销可忽略），避免早期无应用上下文时评估为 False 后永久禁用。
        """
        config = self._resolve_config()
        enabled = True
        if config is not None:
            enabled = config.get("LLM_INNOVATION_ENABLED", True)
        client = self.llm_client
        # 防御性判空：LLM 客户端未初始化时安全回退
        return bool(enabled and client is not None and client.available)

    def extract(self, paper):
        """从 Paper 对象提取创新点。

        优先使用 LLM，不可用时自动回退到规则引擎。
        """
        # ── 路径 1：LLM 提取 ──
        if self.llm_enabled:
            try:
                result = self._extract_with_llm(paper)
                if result and self._is_valid_result(result):
                    logger.info(
                        "论文 %d 创新点由 LLM 提取成功 (backend=%s)",
                        paper.id, self.llm_client.active_backend
                    )
                    return result
            except Exception:
                logger.warning("LLM 创新点提取异常，回退到规则引擎", exc_info=True)

        # ── 路径 2：规则引擎回退 ──
        logger.info("论文 %d 使用规则引擎提取创新点", paper.id if paper else 0)
        return self._rule_extractor.extract(paper)

    def calculate_confidence(self, problem, method, effect):
        """计算创新点置信度（公共 API，委托给规则引擎的评分逻辑）。

        路由层在用户手动编辑创新点后需要重算置信度，
        通过本方法统一访问，避免依赖私有实现。
        """
        return self._rule_extractor.calculate_confidence(problem, method, effect)

    def _extract_with_llm(self, paper):
        """使用 LLM 提取创新点（通篇分析：摘要 + 正文分节）"""
        title = paper.title or ""
        abstract = paper.abstract or ""
        full_text = paper.full_text or None

        llm_result = self.llm_client.extract_innovation(title, abstract, full_text)
        if not llm_result:
            return None

        # 计算置信度（LLM 提取默认高置信度，但有数值指标时额外加分）
        confidence = 0.75  # LLM 提取基础置信度
        effect_text = llm_result.get("effect", "")
        if has_numeric_indicator(effect_text if effect_text != "待补充" else ""):
            confidence = min(confidence + 0.15, 1.0)
        # 三个维度都提取到
        if all(llm_result.get(k, "待补充") != "待补充" for k in ["problem", "method", "effect"]):
            confidence = min(confidence + 0.05, 1.0)

        return {
            "problem": llm_result.get("problem", "待补充")[:500],
            "method": llm_result.get("method", "待补充")[:500],
            "effect": llm_result.get("effect", "待补充")[:500],
            "confidence": round(confidence, 2),
            "source": "llm",
        }

    def _is_valid_result(self, result):
        """检查提取结果是否有效（至少有一个维度被提取到）"""
        if not result:
            return False
        valid_count = sum(
            1 for k in ["problem", "method", "effect"]
            if result.get(k) and result[k] != "待补充" and len(result[k]) > 5
        )
        return valid_count >= 1
