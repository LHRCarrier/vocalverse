"""第五步：resolve_level 回退链（skill confidence → cefr_level → L1）。

resolve_level（rec/service.py:73-84）：UserSkillState.confidence ≥ skill_confidence_min(0.35)
→ 用 est_level；否则回退 UserProfile.cefr_level；再否则回退 "L1"。
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from app.db import get_session_factory
from app.models import User, UserProfile, UserSkillState
from app.rec.service import resolve_level


def _mk_user(
    level: str,
    tags: list[str],
    *,
    has_profile: bool = True,
    has_skill: bool = True,
    est_level: str | None = None,
    confidence: Decimal | None = None,
    cefr_level: str | None = None,
) -> int:
    db = get_session_factory()()
    try:
        u = User(username=f"r{uuid4().hex[:8]}", nickname="t", password_hash="x")
        db.add(u)
        db.flush()
        uid = int(u.id)
        if has_profile:
            db.add(UserProfile(user_id=uid, interest_tags=tags, cefr_level=cefr_level or level))
        if has_skill:
            db.add(
                UserSkillState(
                    user_id=uid,
                    pron_est=0,
                    flu_est=0,
                    est_score=0,
                    est_level=est_level or level,
                    confidence=confidence if confidence is not None else Decimal("1.0"),
                )
            )
        db.commit()
        return uid
    finally:
        db.close()


class TestResolveLevel:
    def test_prefers_skill_when_conf_sufficient(self) -> None:
        """confidence ≥ 阈值 → 返回 UserSkillState.est_level。"""
        uid = _mk_user("L3", [], est_level="L3", confidence=Decimal("0.8"))
        db = get_session_factory()()
        try:
            assert resolve_level(db, uid) == "L3"
        finally:
            db.close()

    def test_falls_back_to_cefr_when_conf_low(self) -> None:
        """confidence < 阈值 → 回退 UserProfile.cefr_level（权威档）。"""
        uid = _mk_user("L4", [], est_level="L4", confidence=Decimal("0.1"), cefr_level="L2")
        db = get_session_factory()()
        try:
            assert resolve_level(db, uid) == "L2"
        finally:
            db.close()

    def test_falls_back_to_cefr_when_skill_missing(self) -> None:
        """无 user_skill_state 行 → 直接用 UserProfile.cefr_level。"""
        uid = _mk_user("L4", [], has_skill=False, cefr_level="L4")
        db = get_session_factory()()
        try:
            assert resolve_level(db, uid) == "L4"
        finally:
            db.close()

    def test_falls_back_to_L1_when_no_data(self) -> None:
        """无 skill_state 且无 profile → 回退 L1。"""
        db = get_session_factory()()
        try:
            u = User(username=f"r{uuid4().hex[:8]}", nickname="t", password_hash="x")
            db.add(u)
            db.commit()
            uid = int(u.id)
            assert resolve_level(db, uid) == "L1"
        finally:
            db.close()
