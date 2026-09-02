"""规则推荐引擎单测（local/31 §6.3 C 组 + local/32 补强 C7/C8/C9）。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from app.db import get_session_factory
from app.models import (
    Event,
    MaterialDifficulty,
    Scenario,
    User,
    UserMastery,
    UserProfile,
    UserSkillState,
)
from app.models.base import EventTypes
from app.rec.service import recommend_scenes
from sqlalchemy import select

_L2, _L3, _L4 = "L2", "L3", "L4"


def _mk_user(level: str, tags: list[str]) -> int:
    db = get_session_factory()()
    try:
        u = User(username=f"r{uuid4().hex[:8]}", nickname="t", password_hash="x")
        db.add(u)
        db.flush()
        db.add(UserProfile(user_id=u.id, interest_tags=tags, cefr_level=level))
        db.add(
            UserSkillState(
                user_id=u.id,
                pron_est=0,
                flu_est=0,
                est_score=0,
                est_level=level,
                confidence=Decimal("1.0"),
            )
        )
        db.commit()
        return int(u.id)
    finally:
        db.close()


def _mk_scene(title: str, difficulty: int, diff_level: str, tags: list[str]):
    db = get_session_factory()()
    try:
        s = Scenario(
            title=title,
            scene_type="cafe",
            difficulty=difficulty,
            system_prompt="p",
            opening_line="o",
            target_corpus="Hi|你好",
            interest_tags=tags,
            status="published",
        )
        db.add(s)
        db.flush()
        db.add(
            MaterialDifficulty(
                content_type="scene",
                content_id=s.id,
                diff_score=Decimal("70"),
                diff_level=diff_level,
                version="expert-v1",
            )
        )
        db.commit()
        return int(s.id)
    finally:
        db.close()


def _mk_mastery(user_id: int, scene_id: int, status: str, days_ago: int | None) -> None:
    db = get_session_factory()()
    try:
        lp = datetime.now(UTC) - timedelta(days=days_ago) if days_ago is not None else None
        db.add(
            UserMastery(
                user_id=user_id,
                content_type="scene",
                content_id=scene_id,
                status=status,
                last_practiced_at=lp,
            )
        )
        db.commit()
    finally:
        db.close()


def test_l2_user_no_l4() -> None:
    """C1/C8：L2 用户推荐只含 [L2,L3]，无 L4 无 L1。"""
    uid = _mk_user(_L2, ["coffee"])
    _mk_scene("a", 2, _L2, ["coffee"])
    _mk_scene("b", 2, _L2, ["coffee"])
    _mk_scene("c", 3, _L3, ["coffee"])
    _mk_scene("d", 4, _L4, ["coffee"])
    db = get_session_factory()()
    try:
        items = recommend_scenes(uid, limit=6, db=db)
        assert items, "应有推荐"
        assert all(it["diff_level"] in {_L2, _L3} for it in items)
        assert all(it["content_type"] == "scene" for it in items)
    finally:
        db.close()


def test_mastered_item_last() -> None:
    """C9：已掌握场景排在同档未掌握之后。"""
    uid = _mk_user(_L2, ["coffee"])
    a = _mk_scene("mastered", 2, _L2, ["coffee"])
    _mk_scene("fresh", 2, _L2, ["coffee"])
    _mk_mastery(uid, a, "mastered", days_ago=30)
    db = get_session_factory()()
    try:
        items = recommend_scenes(uid, limit=2, db=db)
        order = [it["title"] for it in items]
        assert order.index("fresh") < order.index("mastered")  # 未掌握在前
        assert items[-1]["mstatus"] == "mastered"
    finally:
        db.close()


def test_cold_user_zero_profile() -> None:
    """C7：零 skill/profile 用户回退权威档 → 返回默认列表（不抛、非空或空态）。"""
    db = get_session_factory()()
    try:
        u = User(username=f"r{uuid4().hex[:8]}", nickname="t", password_hash="x")
        db.add(u)
        db.flush()
        uid = int(u.id)
        _mk_scene("any", 1, "L1", [])
    finally:
        db.close()
    # 无 user_skill_state/user_profiles（未定档）→ resolve_level=L1 → 返回 L1 场景
    db = get_session_factory()()
    try:
        items = recommend_scenes(uid, limit=3, db=db)
        assert len(items) == 1 and items[0]["title"] == "any"
    finally:
        db.close()


def test_l4_review_slot() -> None:
    """C3：L4 用户主窗无 L4，复习席补 L3 已练且 ≥7 天未练的素材。"""
    uid = _mk_user(_L4, ["coffee"])
    _mk_scene("l3stale", 3, _L3, ["coffee"])  # 已练很久 → 复习席
    _mk_mastery(uid, _mk_scene("l3stale2", 3, _L3, ["coffee"]), "in_progress", days_ago=10)
    _mk_scene("l4new", 4, _L4, ["coffee"])  # 主窗 L4 素材（占位）
    db = get_session_factory()()
    try:
        items = recommend_scenes(uid, limit=6, db=db)
        # 主窗 {L4}（L4 用户），复习席补 L3（已练 >7 天）
        titles = [it["title"] for it in items]
        assert "L4" in {it["diff_level"] for it in items}
        assert "l3stale2" in titles
    finally:
        db.close()


def test_impression_logged_when_own_session() -> None:
    """C5：自有会话路径（db=None）写曝光埋点 events.recommend_impression。"""
    uid = _mk_user(_L2, ["coffee"])
    _mk_scene("x", 2, _L2, ["coffee"])
    recommend_scenes(uid, limit=3)  # db=None → 自有 session，写 Event + Redis（testing→None 跳过）
    db = get_session_factory()()
    try:
        e = (
            db.execute(
                select(Event).where(
                    Event.user_id == uid, Event.event_type == EventTypes.RECOMMEND_IMPRESSION
                )
            )
            .scalars()
            .first()
        )
        assert e is not None
        assert e.payload["user_level"] == _L2
        assert e.payload["items"]
    finally:
        db.close()
