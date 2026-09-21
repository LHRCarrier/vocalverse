"""掌握度写入单测（local/31 §6.1 A 组关联 + local/29 §3 派生链）。

2026-09-21（酒馆迁移）：句级 ``user_corpus_mastery`` 写入随英语场景对话移除
（``app/mastery/service.py`` 只保留内容级）；本文件改为 shadow 素材的内容级掌握度回归。
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from app.db import get_session_factory
from app.mastery.service import update_session_mastery
from app.models import (
    Attempt,
    ShadowMaterial,
    User,
    UserMastery,
)
from app.models import (
    Session as DbSession,
)
from app.models.base import AttemptKinds, SessionKinds, SessionStatus
from sqlalchemy import select


def _seed_shadow_session(user_id: int, scores: list[tuple[float, float]]) -> tuple[int, int]:
    """建 1 个 shadow 会话：素材 + attempts（pron/flu 对）；返回 (session_id, material_id)。"""
    db = get_session_factory()()
    try:
        material = ShadowMaterial(
            title="mastery-shadow",
            level=2,
            text_content="How much is it?",
            audio_url="/demo/audio/shadow/mastery.mp3",
            wpm=120,
            duration_s=10,
            interest_tags=[],
            source="demo_only",
            status="published",
        )
        db.add(material)
        db.flush()
        session = DbSession(
            user_id=user_id,
            kind=SessionKinds.SHADOW,
            shadow_material_id=material.id,
            status=SessionStatus.COMPLETED,
            started_at=datetime.now(UTC),
        )
        db.add(session)
        db.flush()
        for p, f in scores:
            db.add(
                Attempt(
                    user_id=user_id,
                    session_id=session.id,
                    kind=AttemptKinds.SHADOW_SPEECH,
                    pron_score=Decimal(str(p)),
                    flu_score=Decimal(str(f)),
                )
            )
        db.commit()
        return int(session.id), int(material.id)
    finally:
        db.close()


def test_session_mastery_writes_shadow_level() -> None:
    """内容级掌握度：会话综合分（0.6·pron+0.4·flu）均值 + 达标计数 + 状态判定。"""
    db = get_session_factory()()
    try:
        uid = User(username=f"m{uuid4().hex[:8]}", nickname="m", password_hash="x")
        db.add(uid)
        db.commit()
        u = int(uid.id)
    finally:
        db.close()

    # pron=80,flu=75 → S=78 ≥ 75（达标）；pron=88,flu=90 → S=88.8（达标）
    sess_id, mid = _seed_shadow_session(u, [(80, 75), (88, 90)])

    db = get_session_factory()()
    try:
        update_session_mastery(db, sess_id)
        db.commit()

        mrow = db.execute(
            select(UserMastery).where(
                UserMastery.user_id == u,
                UserMastery.content_type == "shadow",
                UserMastery.content_id == mid,
            )
        ).scalar_one()
        assert mrow.attempt_count == 2
        assert float(mrow.mastery_score) == 83.4  # (78+88.8)/2
        assert mrow.pass_count == 1  # 达标按会话级（均值 83.4≥75），1 次会话
        assert mrow.status == "in_progress"  # 需 ≥2 次达标才 mastered；本次 in_progress
    finally:
        db.close()
