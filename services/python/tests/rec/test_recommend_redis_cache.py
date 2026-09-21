"""推荐 Redis 缓存回归（grill py-01：生产态缓存协程未 await → 500/零实现）。

用 fakeredis 模拟生产 redis.asyncio 客户端，验证：
- 缓存命中后不再重算（_recommend_impl 只跑一次）且返回值是真实 JSON 反序列化结果
  （若是被 await 的协程经 json.loads 必然 TypeError —— 本组测试即回归锁）；
- 主动失效（invalidate_recommendation_cache）后下次请求重算。

2026-09-21（酒馆迁移）：scene 推荐移除，推荐物改为影子素材，缓存键 `rec:{uid}:shadow`。
"""

from __future__ import annotations

import json
from decimal import Decimal
from uuid import uuid4

import fakeredis.aioredis
from app.db import get_session_factory
from app.models import (
    MaterialDifficulty,
    ShadowMaterial,
    User,
    UserProfile,
    UserSkillState,
)
from app.rec import service as rec_service
from app.rec.service import invalidate_recommendation_cache, recommend_shadow


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


def _mk_shadow(title: str, diff_level: str = "L2") -> None:
    db = get_session_factory()()
    try:
        m = ShadowMaterial(
            title=title,
            level=2,
            text_content="Hi there.",
            audio_url=f"/demo/audio/shadow/{title}.mp3",
            wpm=120,
            duration_s=10,
            interest_tags=["coffee"],
            source="demo_only",
            status="published",
        )
        db.add(m)
        db.flush()
        db.add(
            MaterialDifficulty(
                content_type="shadow",
                content_id=m.id,
                diff_score=Decimal("70"),
                diff_level=diff_level,
                version="expert-v1",
            )
        )
        db.commit()
    finally:
        db.close()


def _seed_full_window() -> None:
    """limit=3 满额（避开复习席分支——该分支当前有 app 缺陷，见 rec/test_recommend.py）。"""
    for title in ("shadow-a", "shadow-b", "shadow-c"):
        _mk_shadow(title)


async def test_recommend_cache_hit_skips_recompute(monkeypatch) -> None:
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(rec_service, "get_redis", lambda: fake)
    uid = _mk_user()
    _seed_full_window()

    calls = {"n": 0}
    orig = rec_service._recommend_impl

    def counting_impl(user_id, ctype, limit, db):
        calls["n"] += 1
        return orig(user_id, ctype, limit, db)

    monkeypatch.setattr(rec_service, "_recommend_impl", counting_impl)

    first = await recommend_shadow(uid, limit=3)
    assert calls["n"] == 1
    assert first and first[0]["title"] == "shadow-a"
    await recommend_shadow(uid, limit=3)
    assert calls["n"] == 1  # 命中缓存，不再重算（也证明缓存值是真实反序列化结果）

    # 缓存里确实存了 JSON 串（而非协程对象）
    saved = await fake.get(f"rec:{uid}:shadow")
    assert isinstance(saved, str)
    assert json.loads(saved) == first


async def test_invalidate_forces_recompute(monkeypatch) -> None:
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(rec_service, "get_redis", lambda: fake)
    uid = _mk_user()
    _seed_full_window()

    await recommend_shadow(uid, limit=3)
    await invalidate_recommendation_cache(uid)
    assert await fake.get(f"rec:{uid}:shadow") is None

    calls = {"n": 0}
    orig = rec_service._recommend_impl

    def counting_impl(user_id, ctype, limit, db):
        calls["n"] += 1
        return orig(user_id, ctype, limit, db)

    monkeypatch.setattr(rec_service, "_recommend_impl", counting_impl)
    await recommend_shadow(uid, limit=3)
    assert calls["n"] == 1  # 失效后重新计算


async def test_redis_unavailable_degrades_to_recompute(monkeypatch) -> None:
    """get_redis() → None（测试态/连接失败）：不走缓存，直接重算（不 500）。"""
    monkeypatch.setattr(rec_service, "get_redis", lambda: None)
    uid = _mk_user()
    _seed_full_window()
    items = await recommend_shadow(uid, limit=3)
    assert items and items[0]["title"] == "shadow-a"
