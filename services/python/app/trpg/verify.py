"""防遗忘校验纯函数（迁移自 ai4u P2-32/33/35）。

三态：
- missing（缺漏）：事实表有、摘要无 → :func:`verify_gap` 判定（【待记住】补丁）；
- contradiction（矛盾）：摘要与事实表冲突 → :func:`detect_contradiction` 判定；
- consistent：其余。

静态悬空（:func:`detect_dangling`）：任务 active 超窗未提及 / 线索 found 未回收超窗。
纯函数可单测（红线 9），服务层传入已拉取的行 + now + 窗口。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from app.trpg.constants import OPPOSITE_PAIRS
from app.trpg.facts import parse_key

DanglingType = Literal["task", "clue"]


@dataclass
class DanglingItem:
    type: DanglingType
    id: int
    title: str
    last_mentioned_at: Any = None


def _ts(value: Any) -> float:
    """时间 → **毫秒**（与 DANGLING_WINDOW_MS 单位一致，对齐 ai4u Date.getTime()）。"""
    if value is None:
        return 0.0
    if isinstance(value, datetime):
        return value.timestamp() * 1000.0
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return datetime.fromisoformat(str(value)).timestamp() * 1000.0
    except ValueError:
        return 0.0


def detect_dangling(
    tasks: list[dict],
    clues: list[dict],
    now: datetime | float,
    window_ms: float,
) -> list[DanglingItem]:
    """静态悬空项检测（P2-32）：零 LLM 成本，每回合可跑。"""
    now_ts = now if isinstance(now, (int, float)) else now.timestamp() * 1000.0

    def older_than(value: Any) -> bool:
        if value is None:
            return True  # 从未提及 = 悬空
        return now_ts - _ts(value) > window_ms

    out: list[DanglingItem] = []
    for t in tasks:
        if t.get("status") == "active" and older_than(t.get("last_mentioned_at")):
            out.append(
                DanglingItem(
                    type="task",
                    id=int(t["id"]),
                    title=str(t.get("title") or ""),
                    last_mentioned_at=t.get("last_mentioned_at"),
                )
            )
    for c in clues:
        found = c.get("found") if c.get("found") is not None else True
        recovered = c.get("recovered") if c.get("recovered") is not None else False
        if found and not recovered and older_than(c.get("last_mentioned_at")):
            out.append(
                DanglingItem(
                    type="clue",
                    id=int(c["id"]),
                    title=str(c.get("title") or ""),
                    last_mentioned_at=c.get("last_mentioned_at"),
                )
            )
    return out


def title_token(title: str) -> str:
    """标题关键词：去空白后前 4 字（过长截断防噪声匹配）；标题 <4 字用全标题。"""
    t = "".join(str(title or "").split())
    if not t:
        return ""
    return t[: max(2, min(4, len(t)))]


def verify_gap(
    dangling: list[DanglingItem], narrative_summary: str
) -> tuple[bool, list[DanglingItem]]:
    """落差裁决：悬空项是否已被叙事摘要承接（标题前缀包含判定）；返回 (gap, missing)。"""
    summary = narrative_summary or ""
    missing = [d for d in dangling if title_token(d.title) and title_token(d.title) not in summary]
    return (len(missing) > 0, missing)


def opposite_of(value: str) -> str | None:
    """事实 value 的反向词：命中对照表返回反向词，未命中返回 None。"""
    if not value:
        return None
    for a, b in OPPOSITE_PAIRS:
        if a in value:
            return b
        if b in value:
            return a
    return None


def detect_contradiction(summary: str, facts: list[dict]) -> bool:
    """矛盾检测（P2-35）：摘要提到实体 + 出现与事实 value 相反的反向词 → 矛盾。"""
    text = summary or ""
    for f in facts:
        parsed = parse_key(str(f.get("key") or ""))
        if parsed is None or parsed.entity is None:
            continue
        opposite = opposite_of(str(f.get("value") or ""))
        if not opposite:
            continue
        if parsed.entity in text and opposite in text:
            return True
    return False


def build_missing_patch(missing: list[DanglingItem]) -> str | None:
    """【待记住】注入补丁（P2-33：给模型的显式清单，非「提醒注意」）。"""
    if not missing:
        return None
    lines = [
        f"• [{'任务' if m.type == 'task' else '线索'}] {m.title}（进行中/未回收）" for m in missing
    ]
    return "【待记住】以下剧情状态尚未被摘要承接，本回合必须自然提起或推进：\n" + "\n".join(lines)
