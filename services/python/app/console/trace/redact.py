"""内容脱敏（docs/50 §7.5：写入前过 ``redact()``，命中置 ``redacted=true``）。

节奏：**在写入 ``llm_span_contents`` 之前**对所有正文做一次替换，命中即把该行标记
``redacted=True``（让「这份内容被处理过」可自证，而不是只能靠日志倒推）。

覆盖（与 docs/50 §7.5 表一致）：
邮箱 / 手机号（含 + 国际号）/ ``sk-*`` 形态密钥 / ``Bearer <token>`` / 长数字串。

**边界声明**：脱敏只处理"可枚举的凭据与联系方式形态"，**不能**脱敏论文正文/对话正文这类
开放文本 —— 所以真正的护栏是「内容捕获默认关 + defense 类 kind 硬禁采」（见 recorder），
而不是本模块。本模块只降低"顺手把 Key 抄进 prompt"这类事故的爆炸半径。
"""

from __future__ import annotations

import re
from typing import Any

MASK = "***"

#: 替换规则（顺序无关；每条独立扫描）
_PATTERNS: tuple[re.Pattern[str], ...] = (
    # 邮箱
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]{2,}"),
    # Bearer 凭据（含 JWT 形态：点分段 + base64url 字符集）
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}"),
    # sk-* 形态密钥（DeepSeek/OpenAI 同族）
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}"),
    # 长数字串（手机号/身份证/卡号；11 位起，避开日期 "2026-09-10" 这类带分隔的短串）
    re.compile(r"(?<!\d)\d{11,19}(?!\d)"),
    # 带 + 号的国际号码（允许空格/连字符/括号分隔）
    re.compile(r"\+\d[\d\s\-()]{6,}\d"),
)


def redact(text: str | None) -> tuple[str | None, bool]:
    """返回 ``(脱敏后文本, 是否命中)``；``None``/空串原样返回、命中为 False。"""
    if not text:
        return text, False
    out = text
    hit = False
    for pattern in _PATTERNS:
        out, n = pattern.subn(MASK, out)
        if n:
            hit = True
    return out, hit


def redact_messages(
    messages: list[dict[str, Any]] | None,
) -> tuple[list[dict[str, Any]] | None, bool]:
    """按 role 逐条脱敏（结构保持不变，只动 ``content`` 文本）。"""
    if not messages:
        return messages, False
    hit_any = False
    out: list[dict[str, Any]] = []
    for m in messages:
        content, hit = redact(m.get("content") if isinstance(m.get("content"), str) else None)
        hit_any = hit_any or hit
        item = dict(m)
        if content is not None:
            item["content"] = content
        out.append(item)
    return out, hit_any


__all__ = ["MASK", "redact", "redact_messages"]
