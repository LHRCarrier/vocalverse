"""第四步：shadow（影子跟读）推荐 + 难度兜底。

规则引擎 shadow 分支（rec/service.py _candidates）：先 join material_difficulty
(content_type='shadow')；无 md 行时用 ShadowMaterial.level 经 _FALLBACK 兜底映射
[1..4]→[L1..L4]；有 md 行则优先 diff_level。shadow 无 scene_type 多样性约束
（_diversify 对非 scene 直接截断）。
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from app.db import get_session_factory
from app.models import MaterialDifficulty, ShadowMaterial, User, UserProfile, UserSkillState
from app.rec.service import recommend_shadow


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


def _mk_shadow(title: str, level: int, tags: list[str], diff_level: str | None = None) -> int:
    db = get_session_factory()()
    try:
        s = ShadowMaterial(
            title=title,
            level=level,
            text_content="Hi, could you repeat that?",
            audio_url="/demo/audio/shadow/x.mp3",
            wpm=120,
            duration_s=10,
            interest_tags=tags,
            source="demo_only",
            status="published",
        )
        db.add(s)
        db.flush()
        if diff_level is not None:
            db.add(
                MaterialDifficulty(
                    content_type="shadow",
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


class TestShadowRecommend:
    def test_shadow_uses_level_fallback_when_no_md(self) -> None:
        """无 material_difficulty 行 → 用 ShadowMaterial.level 兜底映射。"""
        uid = _mk_user("L2", ["coffee"])
        _mk_shadow("shadow_l2", level=2, tags=["coffee"])  # level 2 → 兜底 L2
        db = get_session_factory()()
        try:
            items = recommend_shadow(uid, limit=5, db=db)
            assert items
            assert all(it["content_type"] == "shadow" for it in items)
            assert items[0]["diff_level"] == "L2"
        finally:
            db.close()

    def test_shadow_md_overrides_fallback(self) -> None:
        """有 material_difficulty 行 → 用 diff_level（md 优先于 level 兜底）。"""
        uid = _mk_user("L2", ["coffee"])
        # level=2 但 md 强制 L3；L2 用户窗口 {L2,L3} → 该 shadow 应出现且档位为 L3
        _mk_shadow("shadow_md_l3", level=2, tags=["coffee"], diff_level="L3")
        db = get_session_factory()()
        try:
            items = recommend_shadow(uid, limit=5, db=db)
            assert items
            assert items[0]["diff_level"] == "L3"
        finally:
            db.close()

    def test_shadow_respects_level_window(self) -> None:
        """shadow 也受水平窗 [L,L+1] 约束：L2 用户看不到 L4 影子。"""
        uid = _mk_user("L2", ["coffee"])
        _mk_shadow("shadow_l2", level=2, tags=["coffee"])
        _mk_shadow("shadow_l4", level=4, tags=["coffee"])  # L4，L2 用户不应见
        db = get_session_factory()()
        try:
            items = recommend_shadow(uid, limit=5, db=db)
            assert items
            assert all(it["diff_level"] != "L4" for it in items)
        finally:
            db.close()

    def test_shadow_empty_when_no_material(self) -> None:
        """无任何 published 影子素材 → 返回空列表（不抛）。"""
        uid = _mk_user("L2", ["coffee"])
        db = get_session_factory()()
        try:
            assert recommend_shadow(uid, limit=5, db=db) == []
        finally:
            db.close()
