"""演示播种 + 推荐链路冒烟（local/31 §6.4 D 组 · local/32 A-5.1/A-5.2）。"""

from __future__ import annotations

from app.db import get_session_factory
from app.db.seed import seed_scenarios
from app.db.seed_recommend import (
    seed_demo_reco_accounts,
    seed_demo_scenes,
    seed_material_difficulty,
)
from app.models import User
from app.rec.service import recommend_scenes
from sqlalchemy import select


def _seed_all() -> None:
    db = get_session_factory()()
    try:
        seed_scenarios(db)  # 8 场景（Java 内容 seed，单写豁免先例）
        seed_demo_scenes(db)
        seed_material_difficulty(db)
        seed_demo_reco_accounts(db)
        db.commit()
    finally:
        db.close()


def test_demo_accounts_get_distinct_reco() -> None:
    """A-5.2：L2 看基础/进阶、L3 看面试(L3)、L4 看商务谈判(L4)，三者互异。"""
    _seed_all()
    db = get_session_factory()()
    try:
        uid = {
            u.username: u.id
            for u in db.execute(
                select(User).where(
                    User.username.in_(["demo_reco_L2", "demo_reco_L3", "demo_reco_L4"])
                )
            ).scalars()
        }
        l2 = {it["title"] for it in recommend_scenes(uid["demo_reco_L2"], limit=6, db=db)}
        l3 = {it["title"] for it in recommend_scenes(uid["demo_reco_L3"], limit=6, db=db)}
        l4 = {it["title"] for it in recommend_scenes(uid["demo_reco_L4"], limit=6, db=db)}
        # 三者都应非空、且互异（推荐素材不同，A-5.2）
        assert l2 and l3 and l4
        assert l2 != l3 and l3 != l4 and l2 != l4
        # L4 应命中商务谈判（L4 素材，A-5.2）
        assert any("商务谈判" in t for t in l4)
    finally:
        db.close()
