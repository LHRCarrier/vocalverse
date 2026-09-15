"""推荐 Redis 缓存回归（grill py-01：生产态缓存协程未 await → 500/零实现）。

用 fakeredis 模拟生产 redis.asyncio 客户端，验证：
- 缓存命中后不再重算（_recommend_impl 只跑一次）且返回值是真实 JSON 反序列化结果
  （若是被 await 的协程经 json.loads 必然 TypeError —— 本组测试即回归锁）；
- 主动失效（invalidate_recommendation_cache）后下次请求重算。
"""

from __future__ import annotations

import json
from decimal import Decimal
from uuid import uuid4

import fakeredis.aioredis
from app.db import get_session_factory
from app.models import (
    MaterialDifficulty,
    Scenario,
    User,
    UserProfile,
    UserSkillState,
)
from app.rec import service as rec_service
from app.rec.service import invalidate_recommendation_cache, recommend_scenes


def _mk_user(level: str = "L2") -> int:
    db = get_session_factory()()
    try:
        u = User(username=f"r{uuid4().hex[:8]}", nickname="t", password_hash="x")
        db.add(u)
        db.flush()
        db.add(UserProfile(user_id=u.id, interest_tags=["coffee"], cefr_level=level))
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


def _mk_scene(title: str, diff_level: str = "L2") -> None:
    db = get_session_factory()()
    try:
        s = Scenario(
            title=title,
            scene_type="cafe",
            difficulty=2,
            system_prompt="p",
            opening_line="o",
            target_corpus="Hi|你好",
            interest_tags=["coffee"],
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
    finally:
        db.close()


async def test_recommend_cache_hit_skips_recompute(monkeypatch) -> None:
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(rec_service, "get_redis", lambda: fake)
    uid = _mk_user()
    _mk_scene("cafe-a")

    calls = {"n": 0}
    orig = rec_service._recommend_impl

    def counting_impl(user_id, ctype, limit, db):
        calls["n"] += 1
        return orig(user_id, ctype, limit, db)

    monkeypatch.setattr(rec_service, "_recommend_impl", counting_impl)

    first = await recommend_scenes(uid, limit=3)
    assert calls["n"] == 1
    assert first and first[0]["title"] == "cafe-a"
    await recommend_scenes(uid, limit=3)
    assert calls["n"] == 1  # 命中缓存，不再重算（也证明缓存值是真实反序列化结果）

    # 缓存里确实存了 JSON 串（而非协程对象）
    saved = await fake.get(f"rec:{uid}:scene")
    assert isinstance(saved, str)
    assert json.loads(saved) == first


async def test_invalidate_forces_recompute(monkeypatch) -> None:
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(rec_service, "get_redis", lambda: fake)
    uid = _mk_user()
    _mk_scene("cafe-b")

    await recommend_scenes(uid, limit=3)
    await invalidate_recommendation_cache(uid)
    assert await fake.get(f"rec:{uid}:scene") is None

    calls = {"n": 0}
    orig = rec_service._recommend_impl

    def counting_impl(user_id, ctype, limit, db):
        calls["n"] += 1
        return orig(user_id, ctype, limit, db)

    monkeypatch.setattr(rec_service, "_recommend_impl", counting_impl)
    await recommend_scenes(uid, limit=3)
    assert calls["n"] == 1  # 失效后重新计算


async def test_redis_unavailable_degrades_to_recompute(monkeypatch) -> None:
    """get_redis() → None（测试态/连接失败）：不走缓存，直接重算（不 500）。"""
    monkeypatch.setattr(rec_service, "get_redis", lambda: None)
    uid = _mk_user()
    _mk_scene("cafe-c")
    items = await recommend_scenes(uid, limit=3)
    assert items and items[0]["title"] == "cafe-c"
