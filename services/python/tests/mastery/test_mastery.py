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
    ShadowMaterial,
    User,
    UserCorpusMastery,
    UserMastery,
)
from app.models import (
    Session as DbSession,
)
from app.models.base import AttemptKinds, MasteryStatus, SessionKinds, SessionStatus
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


def test_none_pron_flu_skips_scene_mastery() -> None:
    """缺分（pron/flu 任一 None）的 attempt 不计分：全部缺分 → 不建场景级；句级仍写。"""
    db = get_session_factory()()
    try:
        u = User(username=f"m{uuid4().hex[:8]}", nickname="m", password_hash="x")
        db.add(u)
        db.flush()
        uid = int(u.id)
        scen = Scenario(
            title="s",
            scene_type="cafe",
            difficulty=2,
            system_prompt="p",
            opening_line="o",
            target_corpus="Hi|你好",
        )
        db.add(scen)
        db.flush()
        s = DbSession(
            user_id=uid,
            kind=SessionKinds.DIALOG,
            scenario_id=scen.id,
            status=SessionStatus.COMPLETED,
            started_at=datetime.now(UTC),
        )
        db.add(s)
        db.flush()
        # 一个两维均缺分，一个 flu 缺分 → 场景级 scored 为空
        db.add(
            Attempt(
                user_id=uid,
                session_id=s.id,
                kind=AttemptKinds.DIALOG_SPEECH,
                pron_score=None,
                flu_score=None,
            )
        )
        db.add(
            Attempt(
                user_id=uid,
                session_id=s.id,
                kind=AttemptKinds.DIALOG_SPEECH,
                pron_score=Decimal("70"),
                flu_score=None,
            )
        )
        db.add(
            ScenarioMessage(
                session_id=s.id,
                seq=1,
                role="user",
                content="hi",
                meta={"corpus_hits": [{"phrase": "Hi", "state": "ok"}]},
            )
        )
        db.commit()
        update_session_mastery(db, int(s.id))
        db.commit()
        # 场景级：无有效分 → 不建行
        row = db.execute(
            select(UserMastery).where(
                UserMastery.user_id == uid,
                UserMastery.content_type == "scene",
                UserMastery.content_id == scen.id,
            )
        ).scalar_one_or_none()
        assert row is None, "全部缺分时不应写场景级 UserMastery"
        # 句级：仍写入（受缺分影响）
        crows = (
            db.execute(
                select(UserCorpusMastery).where(
                    UserCorpusMastery.user_id == uid,
                    UserCorpusMastery.scenario_id == scen.id,
                )
            )
            .scalars()
            .all()
        )
        assert crows and crows[0].status == "mastered"
    finally:
        db.close()


def test_shadow_session_writes_content_mastery() -> None:
    """shadow 会话：写场景级(素材级) UserMastery content_type='shadow'，不写句级。"""
    db = get_session_factory()()
    try:
        u = User(username=f"m{uuid4().hex[:8]}", nickname="m", password_hash="x")
        db.add(u)
        db.flush()
        uid = int(u.id)
        sm = ShadowMaterial(
            title="sh",
            level=2,
            text_content="Hi.",
            audio_url="/d/a.mp3",
            wpm=120,
            duration_s=10,
            interest_tags=[],
            source="demo_only",
            status="published",
        )
        db.add(sm)
        db.flush()
        s = DbSession(
            user_id=uid,
            kind=SessionKinds.SHADOW,
            scenario_id=None,
            shadow_material_id=sm.id,
            status=SessionStatus.COMPLETED,
            started_at=datetime.now(UTC),
        )
        db.add(s)
        db.flush()
        # S = 0.6*70 + 0.4*80 = 74 → in_progress（未达标 75）
        db.add(
            Attempt(
                user_id=uid,
                session_id=s.id,
                kind=AttemptKinds.SHADOW_SPEECH,
                pron_score=Decimal("70"),
                flu_score=Decimal("80"),
            )
        )
        db.commit()
        update_session_mastery(db, int(s.id))
        db.commit()
        row = db.execute(
            select(UserMastery).where(
                UserMastery.user_id == uid,
                UserMastery.content_type == "shadow",
                UserMastery.content_id == sm.id,
            )
        ).scalar_one()
        assert row.attempt_count == 1
        assert float(row.mastery_score) == 74.0
        assert row.status == MasteryStatus.IN_PROGRESS
        assert row.pass_count == 0  # 74 < 75 未达标
        # 无句级（非 dialog）
        assert (
            db.execute(select(UserCorpusMastery).where(UserCorpusMastery.user_id == uid)).first()
            is None
        )
    finally:
        db.close()


def test_update_session_mastery_nonexistent_noop() -> None:
    """不存在的 session_id → 直接返回，不抛。"""
    db = get_session_factory()()
    try:
        update_session_mastery(db, 999_999)  # 不抛
    finally:
        db.close()


def test_mastery_accumulates_to_mastered() -> None:
    """同一素材跨两会话均达标 → 场景级状态累积为 mastered（≥2 次达标且均分≥75）。"""
    db = get_session_factory()()
    try:
        u = User(username=f"m{uuid4().hex[:8]}", nickname="m", password_hash="x")
        db.add(u)
        db.flush()
        uid = int(u.id)
        scen = Scenario(
            title="acc",
            scene_type="cafe",
            difficulty=2,
            system_prompt="p",
            opening_line="o",
            target_corpus="Hi|你好",
        )
        db.add(scen)
        db.flush()
        s1 = DbSession(
            user_id=uid,
            kind=SessionKinds.DIALOG,
            scenario_id=scen.id,
            status=SessionStatus.COMPLETED,
            started_at=datetime.now(UTC),
        )
        db.add(s1)
        db.flush()
        db.add(
            Attempt(
                user_id=uid,
                session_id=s1.id,
                kind=AttemptKinds.DIALOG_SPEECH,
                pron_score=Decimal("80"),
                flu_score=Decimal("75"),  # S=78 达标
            )
        )
        s2 = DbSession(
            user_id=uid,
            kind=SessionKinds.DIALOG,
            scenario_id=scen.id,
            status=SessionStatus.COMPLETED,
            started_at=datetime.now(UTC),
        )
        db.add(s2)
        db.flush()
        db.add(
            Attempt(
                user_id=uid,
                session_id=s2.id,
                kind=AttemptKinds.DIALOG_SPEECH,
                pron_score=Decimal("88"),
                flu_score=Decimal("90"),  # S=88.8 达标
            )
        )
        db.commit()
        update_session_mastery(db, int(s1.id))
        update_session_mastery(db, int(s2.id))
        db.commit()
        row = db.execute(
            select(UserMastery).where(
                UserMastery.user_id == uid,
                UserMastery.content_type == "scene",
                UserMastery.content_id == scen.id,
            )
        ).scalar_one()
        assert row.attempt_count == 2
        assert row.pass_count == 2
        assert row.status == MasteryStatus.MASTERED
    finally:
        db.close()
