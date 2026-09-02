"""掌握度写入单测（local/31 §6.1 A 组关联 + local/29 §3 派生链）。"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from app.db import get_session_factory
from app.mastery.service import update_session_mastery
from app.models import (
    Attempt,
    Scenario,
    ScenarioMessage,
    User,
    UserCorpusMastery,
    UserMastery,
)
from app.models import (
    Session as DbSession,
)
from app.models.base import AttemptKinds, SessionKinds, SessionStatus
from sqlalchemy import select


def _seed_dialog_session(
    user_id: int, scores: list[tuple[float, float]], hits: list[dict]
) -> tuple[int, int]:
    """建 1 个 dialog 会话：scenario + attempts + user 消息 corpus_hits。"""
    db = get_session_factory()()
    try:
        scenario = Scenario(
            title="s",
            scene_type="cafe",
            difficulty=2,
            system_prompt="p",
            opening_line="o",
            target_corpus="How much is it?|多少钱\nThank you so much.|谢谢",
        )
        db.add(scenario)
        db.flush()
        session = DbSession(
            user_id=user_id,
            kind=SessionKinds.DIALOG,
            scenario_id=scenario.id,
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
                    kind=AttemptKinds.DIALOG_SPEECH,
                    pron_score=Decimal(str(p)),
                    flu_score=Decimal(str(f)),
                )
            )
        # 两条 user 消息，各自带 corpus_hits
        for i, h in enumerate(hits, start=1):
            db.add(
                ScenarioMessage(
                    session_id=session.id, seq=i, role="user", content="hi", meta={"corpus_hits": h}
                )
            )
        db.commit()
        return int(session.id), int(scenario.id)
    finally:
        db.close()


def test_session_mastery_writes_scene_and_corpus() -> None:
    """句级 + 场景级掌握度：达标句 mastered、待纠错句 not_mastered；场景级按均值判定。"""
    db = get_session_factory()()
    try:
        uid = User(username=f"m{uuid4().hex[:8]}", nickname="m", password_hash="x")
        db.add(uid)
        db.flush()
        u = int(uid.id)
    finally:
        db.close()

    # pron=80,flu=75 → S=78 ≥ 75（达标）；pron=88,flu=90 → S=88.8（达标）
    sess_id, scen_id = _seed_dialog_session(
        u,
        [(80, 75), (88, 90)],
        [
            [{"phrase": "How much is it?", "state": "ok"}],
            [{"phrase": "Thank you so much.", "state": "fix"}],
        ],
    )

    db = get_session_factory()()
    try:
        update_session_mastery(db, sess_id)
        db.commit()

        # 场景级
        mrow = db.execute(
            select(UserMastery).where(
                UserMastery.user_id == u,
                UserMastery.content_type == "scene",
                UserMastery.content_id == scen_id,
            )
        ).scalar_one()
        assert mrow.attempt_count == 2
        assert float(mrow.mastery_score) == 83.4  # (78+88.8)/2
        assert mrow.pass_count == 1  # 达标按会话级（均值 83.4≥75），1 次会话
        assert mrow.status == "in_progress"  # 需 ≥2 次达标才 mastered；本次 in_progress

        # 句级
        rows = (
            db.execute(
                select(UserCorpusMastery).where(
                    UserCorpusMastery.user_id == u, UserCorpusMastery.scenario_id == scen_id
                )
            )
            .scalars()
            .all()
        )
        by_line = {r.line_index: r for r in rows}
        assert by_line[1].status == "mastered"  # ok 句
        assert by_line[2].status == "not_mastered"  # fix 句
        assert by_line[1].mastery_score == 100
        assert by_line[2].mastery_score == 30
    finally:
        db.close()
