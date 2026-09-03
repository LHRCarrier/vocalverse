"""冒烟：创建两个不同水平/兴趣的测试用户，调用推荐接口，观察返回场景列表是否符合预期。

预期：L2(coffee/travel) 用户窗口 [L2,L3][+L1 扩档]，无 L4；L4(negotiation) 用户窗口 {L4}[+L3 扩档]，
无 L1/L2；两人兴趣命中不同 → 结果互异。
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from app.db import get_session_factory
from app.models import MaterialDifficulty, Scenario, User, UserProfile, UserSkillState
from app.rec.service import recommend_scenes


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


def _mk_scene(title: str, diff_level: str, tags: list[str], scene_type: str) -> int:
    db = get_session_factory()()
    try:
        s = Scenario(
            title=title,
            scene_type=scene_type,
            difficulty=2,
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


def test_two_user_different_level_and_interest() -> None:
    # 两个不同水平/兴趣的测试用户
    user_a = _mk_user("L2", ["coffee", "travel", "ordering"])  # 中低水平，生活兴趣
    user_b = _mk_user("L4", ["career", "negotiation", "advanced"])  # 高端水平，职场兴趣
    # 场景：覆盖 L1..L4，标签与两人分别对齐（scene_type 互异避免同类型上限干扰）
    _mk_scene("L2 咖啡馆", "L2", ["coffee", "travel"], "cafe")
    _mk_scene("L3 机场", "L3", ["coffee"], "airport")
    _mk_scene("L4 商务谈判", "L4", ["career", "negotiation", "advanced"], "interview")
    _mk_scene("L3 面试", "L3", ["career", "negotiation"], "library")
    _mk_scene("L1 日常", "L1", ["daily-life"], "other")

    db = get_session_factory()()
    try:
        items_a = recommend_scenes(user_a, limit=6, db=db)
        items_b = recommend_scenes(user_b, limit=6, db=db)
        titles_a = [it["title"] for it in items_a]
        titles_b = [it["title"] for it in items_b]
        print("\n[smoke] user_A(L2, coffee/travel) →", titles_a)
        print("[smoke] user_B(L4, negotiation)  →", titles_b)

        assert items_a and items_b  # 恒非空
        assert all(it["content_type"] == "scene" for it in items_a + items_b)

        # A 水平窗 [L2,L3](+L1 扩档)：不含 L4
        assert all(it["diff_level"] != "L4" for it in items_a), f"A 不应出现 L4: {titles_a}"
        # A 命中生活兴趣 → 首推 tag_hit ≥1
        assert items_a[0]["tag_hit"] >= 1, f"A 首推应命中兴趣: {titles_a}"

        # B 水平窗 {L4}(+L3 扩档)：不含 L1/L2
        assert all(it["diff_level"] in {"L3", "L4"} for it in items_b), (
            f"B 应只在 L3/L4: {titles_b}"
        )
        assert items_b[0]["tag_hit"] >= 1, f"B 首推应命中职场兴趣: {titles_b}"

        # 两人兴趣不同 → 列表互异
        assert set(titles_a) != set(titles_b), "不同水平/兴趣用户推荐应互异"
    finally:
        db.close()
