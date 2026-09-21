"""匹配机制：掌握度写入（**Python 写方**；local/31 §2.3 · local/29 §3）。

内容级 ``user_mastery``：mastery_score = 素材近期练习综合分（0.6·pron+0.4·flu）增量均值；
状态判定（local/31 §5.1）：mastered = 达标≥2 且均值≥75；in_progress = 60≤均值<75；
否则 not_mastered。

2026-09-21（酒馆迁移）：英语场景对话移除后，句级 ``user_corpus_mastery`` 不再有新写入
（表保留历史数据）；内容级掌握度仅由影子跟读（shadow）产生。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (
    Attempt,
    UserMastery,
)
from app.models import (
    Session as DbSession,
)
from app.models.base import MasteryStatus

logger = logging.getLogger("vocalverse")

# 状态判定阈值（与统一尺度、锚点同源；local/31 §5.1）
_MASTERED_MIN_SCORE = 75.0
_MASTERED_MIN_PASS = 2
_PROGRESS_MIN_SCORE = 60.0


def _attempt_score(attempt: Attempt) -> float | None:
    """场景级综合分（两维口径）：0.6·pron + 0.4·flu。缺分（非 None）才计。"""
    if attempt.pron_score is None or attempt.flu_score is None:
        return None
    return 0.6 * float(attempt.pron_score) + 0.4 * float(attempt.flu_score)


def _status_from(score: float, attempt_count: int, pass_count: int) -> str:
    """掌握度状态（local/31 §5.1）。"""
    if attempt_count == 0:
        return MasteryStatus.NOT_MASTERED
    if pass_count >= _MASTERED_MIN_PASS and score >= _MASTERED_MIN_SCORE:
        return MasteryStatus.MASTERED
    if score >= _PROGRESS_MIN_SCORE:
        return MasteryStatus.IN_PROGRESS
    return MasteryStatus.NOT_MASTERED


def _upsert_scene_mastery(
    db: Session, user_id: int, content_type: str, content_id: int, attempts: list[Attempt]
) -> None:
    """场景/素材级掌握度：按本会话评分增量更新（mastery_score 均值、attempt/pass 计数、状态）。"""
    scored = [a for a in attempts if _attempt_score(a) is not None]
    if not scored:
        return
    cfg = get_settings()
    row = db.execute(
        select(UserMastery).where(
            UserMastery.user_id == user_id,
            UserMastery.content_type == content_type,
            UserMastery.content_id == content_id,
        )
    ).scalar_one_or_none()
    session_score = sum(_attempt_score(a) for a in scored) / len(scored)  # 本会话综合分（均值）
    session_pass = (
        session_score >= cfg.skill_anchor_score
    )  # 达标口径 = 会话级 S≥锚点（local/31 §5.1）
    if row is None:
        row = UserMastery(
            user_id=user_id,
            content_type=content_type,
            content_id=content_id,
            mastery_score=Decimal(str(round(session_score, 2))),
            attempt_count=len(scored),
            pass_count=1 if session_pass else 0,
            last_score=Decimal(str(round(session_score, 2))),
            last_practiced_at=datetime.now(UTC),
            status=MasteryStatus.NOT_MASTERED,
        )
        db.add(row)
    else:
        prev = float(row.mastery_score)
        new_count = row.attempt_count + len(scored)
        row.mastery_score = Decimal(
            str(round((prev * row.attempt_count + session_score * len(scored)) / new_count, 2))
        )
        row.attempt_count = new_count
        if session_pass:
            row.pass_count += 1
        row.last_score = Decimal(str(round(session_score, 2)))
        row.last_practiced_at = datetime.now(UTC)
    row.status = _status_from(float(row.mastery_score), row.attempt_count, row.pass_count)


def update_session_mastery(db: Session, session_id: int) -> None:
    """会话收尾：写内容级掌握度（shadow 素材；历史 dialog 会话仍可按 scene 类型补写）。"""
    session = db.get(DbSession, session_id)
    if session is None:
        return
    attempts = list(db.execute(select(Attempt).where(Attempt.session_id == session_id)).scalars())
    # 素材级（scene=历史 dialog 行 / shadow）掌握度
    content_type = "scene" if session.scenario_id is not None else "shadow"
    content_id = session.scenario_id or session.shadow_material_id
    if content_id is not None:
        _upsert_scene_mastery(db, int(session.user_id), content_type, int(content_id), attempts)
