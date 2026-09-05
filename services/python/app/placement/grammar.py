"""LLM（DeepSeek）语法判定 + QA 相关度标签 —— 考试域 read/qa 诊断（A1 / B2 / C1）。

依据：
- docs/06 §9.3：语法由 LLM 对转写文本判定（0-100 + 错误类型 + 改法）；
- C1 拍板：语法**仅作 QA 答案质量/诊断**（进报告与教练反馈），**不进两维 S 权重**；
- local/34 A-2：``kind='qa'`` 只 ASR 不 ISE；read/qa 均补调 LLM 语法；
- local/34 B-2：QA 答案另给**相关度标签**（related/partial/off_topic），落 ``details.qa``；
- 控 LLM 次数（local/16：入学测试 ≈1~2 次调用）：QA 用**一次**调用同时产出 grammar + relevance。

输出契约（与场景路径 META 的 grammar 字段一致）：``grammar={score:0-100, errors:[{word,fix}]}``。
**fail-open**：LLM 不可用/无 Key/输出非 JSON/解析失败 → 返回 ``None``，不阻塞结算、
不伪造分数（docs/10 §4.3 attempts.error 语义）；grammar 缺失由上层置 ``gram_score=None``。
"""

from __future__ import annotations

import json
import logging

from app.audio.base import get_llm_client

logger = logging.getLogger("vocalverse")

# 语法判定 prompt（read/qa 共用；要求仅输出 JSON）
_SYSTEM = (
    "You are a strict but kind English grammar checker for a speaking practice app. "
    "Judge the grammar of the learner's transcribed speech, considering the prompt/reference. "
    "Return ONLY valid JSON with these keys: "
    '{"score": <integer 0-100>, "errors": [{"word": "<word>", "fix": "<correction>"}]}. '
    "If the grammar is acceptable, errors=[]. Do not output any other text."
)

# QA 相关度判定 prompt（一次调用同时给 grammar + relevance）
_SYSTEM_QA = (
    "You are grading an English open-ended speaking answer for a practice test. "
    "Judge two things from the learner's speech vs the question: "
    "(1) grammar accuracy — same JSON schema {score:0-100, errors:[{word,fix}]}; "
    "(2) relevance — is the answer on-topic and coherent? Use exactly one of "
    '"related" (answers the question), "partial" (touches it but incomplete), '
    '"off_topic" (does not address the question). '
    'Return ONLY valid JSON: {"grammar": {"score": <int>, "errors": [...]}, '
    '"relevance": "related"|"partial"|"off_topic"}. Do not output any other text.'
)

# QA 相关度枚举（落 details.qa.relevance）
RELEVANCE = ("related", "partial", "off_topic")


def _extract_json(text: str) -> dict | None:
    """宽松抽取首个 {...} 并校验为 dict；失败返回 None。"""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _coerce_grammar(grammar: dict | None) -> dict | None:
    """规范化 grammar 结构；缺 score → None（不产出无效诊断）。"""
    if not isinstance(grammar, dict):
        return None
    score = grammar.get("score")
    if score is None:
        return None
    try:
        score = int(float(score))
    except (TypeError, ValueError):
        return None
    errors = grammar.get("errors")
    if not isinstance(errors, list):
        errors = []
    return {"score": max(0, min(100, score)), "errors": errors}


def _coerce_relevance(value) -> str | None:
    return value if value in RELEVANCE else None


async def judge_grammar(transcript: str, reference: str) -> dict | None:
    """LLM 判语法（A1，read/qa 通用）。transcript 为空 → None；任何异常/解析失败 → None。"""
    if not transcript:
        return None
    client = get_llm_client()
    messages = [
        {"role": "system", "content": _SYSTEM},
        {
            "role": "user",
            "content": f"Prompt/reference:\n{reference}\n\nLearner speech (ASR):\n{transcript}",
        },
    ]
    try:
        # temperature=0：判定类输出要求稳定可复现；response_format=json 由 client 内自动启用
        raw = await client.chat(messages, temperature=0.0, max_tokens=200)
    except Exception as exc:  # noqa: BLE001 - fail-open：语法不可用不阻塞入学测试
        logger.warning("placement grammar LLM 判定失败，fail-open 到 None：%s", exc)
        return None
    grammar = _extract_json(raw)
    if grammar is None:
        logger.warning("placement grammar LLM 输出非合法 JSON，fail-open 到 None")
        return None
    return _coerce_grammar(grammar)


async def judge_qa_answer(transcript: str, reference: str) -> dict | None:
    """QA 答案综合判定（B2）：一次调用产出 ``{"grammar": {...}, "relevance": <label>}``。

    任何失败 → None（fail-open，grammar 与 relevance 均按缺失处理，不阻塞结算）。
    """
    if not transcript:
        return None
    client = get_llm_client()
    messages = [
        {"role": "system", "content": _SYSTEM_QA},
        {
            "role": "user",
            "content": f"Question:\n{reference}\n\nLearner answer (ASR):\n{transcript}",
        },
    ]
    try:
        raw = await client.chat(messages, temperature=0.0, max_tokens=220)
    except Exception as exc:  # noqa: BLE001 - fail-open
        logger.warning("placement QA LLM 判定失败，fail-open 到 None：%s", exc)
        return None
    data = _extract_json(raw)
    if data is None:
        logger.warning("placement QA LLM 输出非合法 JSON，fail-open 到 None")
        return None
    grammar = _coerce_grammar(data.get("grammar"))
    relevance = _coerce_relevance(data.get("relevance"))
    return {"grammar": grammar, "relevance": relevance}


__all__ = ["RELEVANCE", "judge_grammar", "judge_qa_answer"]
