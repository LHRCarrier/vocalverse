"""骰子规则纯函数（迁移自 ai4u dice-rule.util，P2-17/41）。

契约：模型只调用不计算，系统解析判定并落表；文本一个结果两路消费——模型拿文本讲故事，
系统拿 JSON 改状态（``effects`` 增量由 DM 给出，系统做算术，绝不从文本二次解析）。
"""

from __future__ import annotations

import math
import random
import re
from dataclasses import dataclass, field
from typing import Literal

from app.trpg.constants import STATE_DOMAINS
from app.trpg.facts import parse_key

_DICE_RE = re.compile(r"^(\d+)?d(\d+)$", re.IGNORECASE)
_MAX_MODIFIER = 50


@dataclass(frozen=True)
class DiceEffect:
    key: str
    delta: int


@dataclass
class DiceResult:
    rolls: list[int]
    sides: int
    count: int
    modifier: int
    total: int
    vs: int | None
    outcome: Literal["success", "failure"] | None
    deltas: list[DiceEffect] = field(default_factory=list)


def parse_dice(args: dict) -> DiceResult | None:
    """解析骰子入参（宽容 dict，来自工具 JSON）；非法返回 None（调用方给错误文本，绝不静默）。"""
    spec = str(args.get("dice") or "").strip()
    if not spec:
        return None
    m = _DICE_RE.match(spec)
    if not m:
        return None
    sides = int(m.group(2))
    count = int(m.group(1) or "1")
    if not (2 <= sides <= 1000):
        return None
    if not (1 <= count <= 10):
        return None
    raw_mod = args.get("modifier", 0)
    modifier = (
        int(raw_mod) if isinstance(raw_mod, (int, float)) and not isinstance(raw_mod, bool) else 0
    )
    if abs(modifier) > _MAX_MODIFIER:
        return None

    vs_raw = args.get("vs", args.get("dc"))
    vs: int | None = None
    if vs_raw is not None:
        if isinstance(vs_raw, bool) or not isinstance(vs_raw, (int, float)):
            return None
        if vs_raw < 1:
            return None
        vs = int(vs_raw)

    rolls = [1 + random.randint(0, sides - 1) for _ in range(count)]
    total = sum(rolls) + modifier

    deltas: list[DiceEffect] = []
    effects = args.get("effects") or []
    if not isinstance(effects, list):
        return None
    for e in effects:
        if not isinstance(e, dict):
            return None
        key = e.get("key")
        delta = e.get("delta")
        if (
            not isinstance(key, str)
            or isinstance(delta, bool)
            or not isinstance(delta, (int, float))
        ):
            return None
        parsed = parse_key(key)
        if parsed is None or parsed.domain not in STATE_DOMAINS:
            return None
        deltas.append(DiceEffect(key=key, delta=int(delta)))

    outcome: Literal["success", "failure"] | None = None
    if vs is not None:
        outcome = "success" if total >= vs else "failure"
    return DiceResult(
        rolls=rolls,
        sides=sides,
        count=count,
        modifier=modifier,
        total=total,
        vs=vs,
        outcome=outcome,
        deltas=deltas,
    )


def format_dice_text(r: DiceResult) -> str:
    """描述性文本（给模型）：如「掷出 13+2=15，对抗 12，成功」。"""
    modifier_text = f"{r.modifier:+d}" if r.modifier != 0 else ""
    roll_text = f"{'+'.join(str(x) for x in r.rolls)}{modifier_text}"
    total_text = f"{roll_text}={r.total}" if modifier_text else str(r.total)
    if r.vs is None:
        return f"掷出 {total_text}"
    outcome_text = "成功" if r.outcome == "success" else "失败"
    return f"掷出 {total_text}，对抗 {r.vs}，{outcome_text}"


def delta_value(current: str | None, delta: int) -> str | None:
    """State 增量算术（只增量不覆盖用户手改）；current 非纯数字（如 '3/12'）返回 None。

    与 ai4u 的 ``Number(value)`` 口径对齐：空串按 0 计；NaN/Infinity/带单位文本 → None。
    """
    if current is None:
        return None
    text = current.strip()
    if text == "":
        base = 0.0
    else:
        try:
            base = float(text)
        except (TypeError, ValueError):
            return None
    if not math.isfinite(base):
        return None
    result = base + delta
    if result.is_integer():
        return str(int(result))
    return str(result)
