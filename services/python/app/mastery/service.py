"""匹配机制：掌握度写入（**Python 写方**；local/31 §2.3 · local/29 §3）。

派生链：attempts × corpus_hit → user_corpus_mastery（句级）→ 聚合 → user_mastery（场景级）。
两表均 Python 写、会话收尾同事务（由 complete_session 收尾挂钩调用）。

- 场景级 ``user_mastery``：mastery_score = 该场景近期练习综合分（0.6·pron+0.4·flu）增量均值；
- 句级 ``user_corpus_mastery``：按 corpus_hit 的 phrase/state 写入（ok=达标、fix=待纠错）；
- 状态判定（local/31 §5.1）：mastered = 达标≥2 且均值≥75；in_progress = 60≤均值<75；
  否则 not_mastered。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.difficulty.batch import parse_corpus
from app.models import (
    Attempt,
    Scenario,
    ScenarioMessage,
    UserCorpusMastery,
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


def _corpus_line_map(scenario: Scenario) -> dict[str, int]:
    """target_corpus 的 'English|中文' 行 → phrase 序号（1..n）。"""
    return {ph: i + 1 for i, ph in enumerate(parse_corpus(scenario.target_corpus or ""))}


def _upsert_corpus_mastery(
    db: Session, user_id: int, scenario: Scenario, msgs: list[ScenarioMessage]
) -> None:
    """句级掌握度：按 user 消息 meta.corpus_hits 的 {phrase,state} 逐句 upsert。

    ok=100、fix=30（达标/待纠错）；status 按最近命中状态推进。
    """
    line_map = _corpus_line_map(scenario)
    hits: list[tuple[int, str, bool]] = []  # (line_index, phrase, ok)
    for m in msgs:
        if m.role != "user":
            continue
        for h in (m.meta or {}).get("corpus_hits", []) or []:
            phrase = h.get("phrase")
            if not phrase or phrase not in line_map:
                continue
            hits.append((line_map[phrase], phrase, h.get("state") == "ok"))
    for line_index, phrase, ok in hits:
        row = db.execute(
            select(UserCorpusMastery).where(
                UserCorpusMastery.user_id == user_id,
                UserCorpusMastery.scenario_id == int(scenario.id),
                UserCorpusMastery.line_index == line_index,
            )
        ).scalar_one_or_none()
        score = 100.0 if ok else 30.0
        if row is None:
            row = UserCorpusMastery(
                user_id=user_id,
                scenario_id=int(scenario.id),
                line_index=line_index,
                phrase=phrase,
                mastery_score=Decimal(str(score)),
                attempt_count=1,
                pass_count=1 if ok else 0,
                last_score=Decimal(str(score)),
                last_practiced_at=datetime.now(UTC),
                status=MasteryStatus.MASTERED if ok else MasteryStatus.NOT_MASTERED,
            )
            db.add(row)
        else:
            prev = float(row.mastery_score)
            new_count = row.attempt_count + 1
            row.mastery_score = Decimal(
                str(round((prev * row.attempt_count + score) / new_count, 2))
            )
            row.attempt_count = new_count
            if ok:
                row.pass_count += 1
            row.last_score = Decimal(str(score))
            row.last_practiced_at = datetime.now(UTC)
            row.status = (
                MasteryStatus.MASTERED
                if (ok and row.pass_count >= _MASTERED_MIN_PASS)
                else (MasteryStatus.IN_PROGRESS if ok else MasteryStatus.NOT_MASTERED)
            )


def update_session_mastery(db: Session, session_id: int) -> None:
    """会话收尾：写句级 + 场景级掌握度（dialog 场景有 corpus_hits；shadow 只写素材级）。"""
    session = db.get(DbSession, session_id)
    if session is None:
        return
    attempts = list(db.execute(select(Attempt).where(Attempt.session_id == session_id)).scalars())
    # 素材级（scene / shadow）掌握度
    content_type = "scene" if session.scenario_id is not None else "shadow"
    content_id = session.scenario_id or session.shadow_material_id
    if content_id is not None:
        _upsert_scene_mastery(db, int(session.user_id), content_type, int(content_id), attempts)
    # 句级掌握度（仅 dialog 场景）
    if session.kind == "dialog" and session.scenario_id is not None:
        scenario = db.get(Scenario, session.scenario_id)
        if scenario is not None:
            msgs = list(
                db.execute(
                    select(ScenarioMessage).where(ScenarioMessage.session_id == session_id)
                ).scalars()
            )
            _upsert_corpus_mastery(db, int(session.user_id), scenario, msgs)
