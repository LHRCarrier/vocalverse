"""学习经验（XP）后端聚合（docs/53 P5）：等级/经验由服务端从事实表计算，前端只展示。

口径（docs/35 §5 演示规则的后端化基线；数值即规则，明写可审计）：
- 完成一次评分练习（``attempts`` 一行）：+15；
- 完成一次跟唱评分（``sing_attempts`` 一行）：+15；
- 自由对话回合（``events: free_chat_turn``）：+5（docs/35 原「自由回合 +5」）；
- 完成一次练习会话（``events: practice_complete``）：+15。

等级表与前端原 ``stores/progress.ts`` 完全一致（LV1~LV5），**本接口为唯一真源**：
LV1 英语新手 0 / LV2 口语学徒 100 / LV3 对话能手 250 / LV4 表达达人 500 / LV5 流利大师 900。
返回 ``breakdown``（各规则计数 × 权重）便于复算（与 P2 指标「分子分母同存」同纪律）。
"""

from __future__ import annotations

from typing import Any

from app.models.analytics import Event
from app.models.practice import Attempt, SingAttempt
from sqlalchemy import func, select
from sqlalchemy.orm import Session

LEVELS: tuple[dict[str, Any], ...] = (
    {"level": 1, "title": "英语新手", "xp": 0},
    {"level": 2, "title": "口语学徒", "xp": 100},
    {"level": 3, "title": "对话能手", "xp": 250},
    {"level": 4, "title": "表达达人", "xp": 500},
    {"level": 5, "title": "流利大师", "xp": 900},
)

XP_RULES: dict[str, int] = {
    "attempt": 15,
    "sing_attempt": 15,
    "free_chat_turn": 5,
    "practice_complete": 15,
}


def _count(db: Session, model, user_id: int) -> int:
    return int(
        db.execute(select(func.count()).select_from(model).where(model.user_id == user_id)).scalar()
        or 0
    )


def _event_counts(db: Session, user_id: int) -> dict[str, int]:
    rows = db.execute(
        select(Event.event_type, func.count())
        .where(
            Event.user_id == user_id,
            Event.event_type.in_(("free_chat_turn", "practice_complete")),
        )
        .group_by(Event.event_type)
    ).all()
    return {str(t): int(n) for t, n in rows}


def xp_summary(db: Session, user_id: int) -> dict[str, Any]:
    """用户当前 XP / 等级 / 下一级门槛（前端进度条直接消费）。"""
    attempts = _count(db, Attempt, user_id)
    sings = _count(db, SingAttempt, user_id)
    events = _event_counts(db, user_id)
    free_turns = events.get("free_chat_turn", 0)
    practice_done = events.get("practice_complete", 0)

    breakdown = {
        "attempt": attempts,
        "sing_attempt": sings,
        "free_chat_turn": free_turns,
        "practice_complete": practice_done,
    }
    xp = sum(breakdown[key] * weight for key, weight in XP_RULES.items())

    cur = LEVELS[0]
    nxt: dict[str, Any] | None = None
    for level in LEVELS:
        if xp >= level["xp"]:
            cur = level
        else:
            nxt = level
            break
    return {
        "xp": xp,
        "level": cur["level"],
        "title": cur["title"],
        "base": cur["xp"],
        "next": nxt["xp"] if nxt else None,
        "breakdown": breakdown,
        "rules": [{"key": key, "xp": weight} for key, weight in XP_RULES.items()],
    }
