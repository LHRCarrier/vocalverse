"""update_user_level 核心逻辑单测（local/31 §6.1 A1~A5 + local/32 修订回归）。

覆盖：定级回退 / 冷启动 / 满窗混合（甲 L2→L3 旅程）/ confidence 单调 / 滞回 / 难度归一化符号。
SQLite `:memory:` 走 create_all（docs/10 §7：测试 create_all，生产 Alembic）。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from app.db import get_session_factory
from app.models import (
    Attempt,
    MaterialDifficulty,
    Placement,
    Scenario,
    User,
    UserSkillState,
)
from app.models import (
    Session as DbSession,
)
from app.models.base import AttemptKinds, SessionKinds, SessionStatus
from app.skill.service import update_user_level
from sqlalchemy import select


def _mk_user() -> int:
    db = get_session_factory()()
    try:
        u = User(username=f"u{uuid4().hex[:8]}", nickname="t", password_hash="x")
        db.add(u)
        db.flush()
        db.commit()
        return int(u.id)
    finally:
        db.close()


def _mk_scenario() -> int:
    db = get_session_factory()()
    try:
        s = Scenario(
            title="s",
            scene_type="cafe",
            difficulty=1,
            system_prompt="p",
            opening_line="o",
            target_corpus="hi|你好",
        )
        db.add(s)
        db.flush()
        db.commit()
        return int(s.id)
    finally:
        db.close()


def _mk_placement(user_id: int, score: float, level: str, days_ago: int) -> None:
    db = get_session_factory()()
    try:
        db.add(
            Placement(
                user_id=user_id,
                status="completed",
                completed_at=datetime.now(UTC) - timedelta(days=days_ago),
                overall_score=Decimal(str(score)),
                level=level,
                details={"schema_version": "2d"},
            )
        )
        db.commit()
    finally:
        db.close()


def _mk_attempts(user_id: int, scenario_id: int, scores: list[float], turn0: int) -> None:
    """每个 score = (pron, flu) 对，均分成若干会话（每 5 条一会话）。"""
    db = get_session_factory()()
    try:
        start = datetime.now(UTC) - timedelta(days=7) + timedelta(seconds=turn0)
        # 每 5 条一个会话，会话创建时间依序递增
        for i in range(0, len(scores), 5):
            chunk = scores[i : i + 5]
            sess = DbSession(
                user_id=user_id,
                kind=SessionKinds.DIALOG,
                scenario_id=scenario_id,
                status=SessionStatus.COMPLETED,
                started_at=start,
                completed_at=start + timedelta(minutes=3),
            )
            db.add(sess)
            db.flush()
            for j, (p, f) in enumerate(chunk):
                db.add(
                    Attempt(
                        user_id=user_id,
                        session_id=sess.id,
                        kind=AttemptKinds.DIALOG_SPEECH,
                        pron_score=Decimal(str(p)),
                        flu_score=Decimal(str(f)),
                        created_at=start + timedelta(seconds=j),
                    )
                )
            start += timedelta(days=1)
        db.commit()
    finally:
        db.close()


def _mk_diff(content_id: int, diff: float) -> None:
    db = get_session_factory()()
    try:
        db.add(
            MaterialDifficulty(
                content_type="scene",
                content_id=content_id,
                diff_score=Decimal(str(diff)),
                diff_level="L2",
                version="expert-v1",
            )
        )
        db.commit()
    finally:
        db.close()


def _get_state(user_id: int) -> UserSkillState:
    db = get_session_factory()()
    try:
        return db.execute(
            select(UserSkillState).where(UserSkillState.user_id == user_id)
        ).scalar_one()
    finally:
        db.close()


# ---------------------------------------------------------------------------
def test_cold_start_no_placement_no_samples() -> None:
    """A1：双缺（无 placement 无样本）→ (50, L1, conf=0)。"""
    uid = _mk_user()
    r = update_user_level(uid)
    assert r["est_score"] == 50.0
    assert r["est_level"] == "L1"
    assert r["confidence"] == 0.0
    assert r["sample_count"] == 0


def test_placement_only_no_samples() -> None:
    """A2：有定档无样本 → est=定档分（2d），conf=0。"""
    uid = _mk_user()
    _mk_placement(uid, 62.0, "L2", days_ago=3)
    r = update_user_level(uid)
    assert r["est_score"] == 62.0
    assert r["est_level"] == "L2"
    assert r["confidence"] == 0.0


def test_confidence_monotonic() -> None:
    """A4（local/30 修订回归）：confidence 随 n 单调（n=4→0.4, n=5→0.5, n=10→1.0）。"""
    uid = _mk_user()
    _mk_placement(uid, 62.0, "L2", days_ago=30)  # 30 天前定档，f 极小
    sid = _mk_scenario()
    _mk_diff(sid, 70.0)  # 中性难度（归一化不影响）
    _mk_attempts(uid, sid, [(60, 60)] * 4, turn0=0)
    r4 = update_user_level(uid)
    assert r4["confidence"] == pytest.approx(0.4)
    _mk_attempts(uid, sid, [(60, 60)], turn0=100)
    r5 = update_user_level(uid)
    assert r5["confidence"] == pytest.approx(0.5)


def test_ji_journey_L2_to_L3() -> None:
    """D2 端到端：甲 P=62，三次练习窗口均值→74，est≈72.3 → L3（local/30 §3 复算）。"""
    uid = _mk_user()
    _mk_placement(uid, 62.0, "L2", days_ago=5)  # d≈5 → f≈0.142
    sid = _mk_scenario()
    _mk_diff(sid, 70.0)  # 中性
    # 会话1 均值 67.2、会话2 均值 72、会话3 均值 76；窗口=10 → 取会话2+3 → mean 74
    s1 = [(66, 68), (68, 70), (65, 68), (70, 73), (67, 69)]  # pron,flu -> 0.6p+0.4f = 67.2 附近
    s2 = [(72, 74), (70, 72), (71, 73), (73, 75), (74, 76)]  # ~72
    s3 = [(75, 77), (77, 79), (76, 78), (75, 77), (77, 79)]  # ~76
    _mk_attempts(uid, sid, s1 + s2 + s3, turn0=0)
    r = update_user_level(uid)
    # est = 0.142*62 + 0.858*74 ≈ 72.3 → L3（断言档位见 L3，分数落 70~77）
    assert r["est_level"] == "L3"
    assert 70.0 <= r["est_score"] <= 77.0


def test_hysteresis_keeps_L3_at_upper_edge() -> None:
    """A5（local/30 修订回归）：est 69.9（旧档 L3）→ 保持 L3（滞回带 [67,70)）。"""
    uid = _mk_user()
    _mk_placement(uid, 62.0, "L2", days_ago=5)
    sid = _mk_scenario()
    _mk_diff(sid, 70.0)
    _mk_attempts(uid, sid, [(72, 72)] * 10, turn0=0)  # 先推到 L3（est≈70.6）
    first = update_user_level(uid)
    assert first["est_level"] == "L3"
    # 窗口降到 raw70 → est≈68.9（raw=L2），但 ≥67 → 滞回带内保持 L3
    _mk_attempts(uid, sid, [(70, 70)] * 10, turn0=500)
    second = update_user_level(uid)
    assert second["est_level"] == "L3"  # 滞回带内保持


def test_difficulty_normalization_sign() -> None:
    """A7：难度归一化符号（local/27 §4.1 修正为 +）。难素材(diff=85)→能力分被拉高。"""
    uid = _mk_user()
    _mk_placement(uid, 62.0, "L2", days_ago=5)
    sid = _mk_scenario()
    _mk_diff(sid, 85.0)  # 难素材
    # raw = 60，归一化后 = 60 + (85-70) = 75
    _mk_attempts(uid, sid, [(60, 60)] * 5, turn0=0)
    r = update_user_level(uid)
    # 归一化把样本拉到 75，且定档残余 f≈0.14 -> est 在 72~75 区间，应为 L3
    assert r["est_score"] >= 72.0
    assert r["est_level"] == "L3"
