"""第三步：曝光埋点 + Redis 缓存命中/失效（own 会话路径，db=None）。

要点：get_redis() 在 testing 下返回 None（redis_client.py:26-27）→ _cache_get/_cache_set/
invalidate 都静默 no-op。因此测缓存必须 monkeypatch app.rec.service.get_redis 为内存 stub；
曝光埋点（Event 写库）不依赖 Redis，own 路径总会写。
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from app.db import get_session_factory
from app.models import Event, MaterialDifficulty, Scenario, User, UserProfile, UserSkillState
from app.models.base import EventTypes
from app.rec.service import invalidate_recommendation_cache, recommend_scenes
from sqlalchemy import func, select


class _FakeRedis:
    """最小内存 stub：模拟 get/set(ex=)/delete，供缓存命中/失效断言。"""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def get(self, key: str):
        return self.store.get(key)

    def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.store[key] = value

    def delete(self, *keys: str) -> int:
        n = 0
        for k in keys:
            if k in self.store:
                del self.store[k]
                n += 1
        return n


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


def _mk_scene(title: str, diff_level: str, tags: list[str], scene_type: str = "cafe") -> int:
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


def _event_row(uid: int):
    db = get_session_factory()()
    try:
        return (
            db.execute(
                select(Event).where(
                    Event.user_id == uid, Event.event_type == EventTypes.RECOMMEND_IMPRESSION
                )
            )
            .scalars()
            .first()
        )
    finally:
        db.close()


def _event_count(uid: int) -> int:
    db = get_session_factory()()
    try:
        return int(
            db.execute(
                select(func.count())
                .select_from(Event)
                .where(
                    Event.user_id == uid,
                    Event.event_type == EventTypes.RECOMMEND_IMPRESSION,
                )
            ).scalar_one()
        )
    finally:
        db.close()


class TestImpressionPayload:
    def test_payload_structure_and_items_match_return(self) -> None:
        """own 路径写曝光：payload = {content_type, items, user_level, rule_version}。"""
        uid = _mk_user("L2", ["coffee"])
        _mk_scene("s", "L2", ["coffee"], "cafe")
        items = recommend_scenes(uid, limit=3, db=None)  # own：写 Event（Redis testing→None 跳过）
        assert items
        e = _event_row(uid)
        assert e is not None
        p = e.payload
        assert p["content_type"] == "scene"
        assert p["user_level"] == "L2"
        assert p["rule_version"] == "rules-v1"
        assert isinstance(p["items"], list) and p["items"]
        for it in p["items"]:
            assert {"id", "level"} <= set(it)
        # 曝光 items 与返回 id 集合一致
        assert {x["id"] for x in p["items"]} == {it["id"] for it in items}


class TestRedisCache:
    def test_cache_written_on_first_call_then_hit(self, monkeypatch) -> None:
        fake = _FakeRedis()
        monkeypatch.setattr("app.rec.service.get_redis", lambda: fake)
        uid = _mk_user("L2", ["coffee"])
        _mk_scene("s", "L2", ["coffee"], "cafe")
        first = recommend_scenes(uid, limit=3, db=None)
        key = f"rec:{uid}:scene"
        assert key in fake.store, "首次 own 调用应写入缓存 rec:{uid}:scene"
        # 第二次命中缓存：结果一致，且不再写曝光
        second = recommend_scenes(uid, limit=3, db=None)
        assert {it["id"] for it in second} == {it["id"] for it in first}
        assert _event_count(uid) == 1, "缓存命中不应再写曝光"

    def test_invalidate_deletes_both_keys(self, monkeypatch) -> None:
        fake = _FakeRedis()
        monkeypatch.setattr("app.rec.service.get_redis", lambda: fake)
        uid = 42
        fake.store[f"rec:{uid}:scene"] = "[]"
        fake.store[f"rec:{uid}:shadow"] = "[]"
        invalidate_recommendation_cache(uid)
        assert f"rec:{uid}:scene" not in fake.store
        assert f"rec:{uid}:shadow" not in fake.store

    def test_invalidate_survives_no_redis(self, monkeypatch) -> None:
        """get_redis() 为 None（testing 默认）时 invalidate 不抛、幂等。"""
        monkeypatch.setattr("app.rec.service.get_redis", lambda: None)
        invalidate_recommendation_cache(7)  # 不应抛异常

    def test_cache_get_json_roundtrip_via_fake(self, monkeypatch) -> None:
        """_cache_set 写入 JSON 字符串、_cache_get 可解析回列表（经 fake redis）。"""
        fake = _FakeRedis()
        monkeypatch.setattr("app.rec.service.get_redis", lambda: fake)
        uid = _mk_user("L2", ["coffee"])
        _mk_scene("s", "L2", ["coffee"], "cafe")
        # 第一次 miss → 计算并写缓存；直接读 fake 确认是 JSON 字符串且可解析
        recommend_scenes(uid, limit=3, db=None)
        key = f"rec:{uid}:scene"
        assert key in fake.store
        import json

        cached = json.loads(fake.store[key])
        assert isinstance(cached, list) and cached
        assert cached[0]["content_type"] == "scene"
