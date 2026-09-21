"""埋点链路 P1（docs/53 §1）：target_type 扩值 / 维度快照 / 游客 page_view / 约束兜底。

修复前必失败用例见 ``test_defense_target_type_persists``（原 CHECK 只允许 scene/song/home，
defense 事件被 IntegrityError 当成重复上报静默吞掉 → 答辩链路 0 落库）。
"""

from __future__ import annotations

import time

from app.db import get_session_factory
from app.models import Event
from app.models.user import User, UserProfile
from sqlalchemy import select


def _rows(**filters) -> list[Event]:
    db = get_session_factory()()
    try:
        stmt = select(Event)
        for key, value in filters.items():
            stmt = stmt.where(getattr(Event, key) == value)
        return list(db.execute(stmt).scalars())
    finally:
        db.close()


def _new_profile_user(*, age_group: str = "adult", level: str = "L3") -> int:
    db = get_session_factory()()
    try:
        user = User(username="event_u", nickname="e", password_hash="x")
        db.add(user)
        db.flush()
        db.add(UserProfile(user_id=user.id, age_group=age_group, cefr_level=level))
        db.commit()
        return int(user.id)
    finally:
        db.close()


def test_defense_target_type_persists(client, auth_headers):
    """答辩 target_type='defense' 必须真实落库（修复前：CHECK 拦截 → 静默 dedup）。"""
    r = client.post(
        "/api/v1/events",
        json={
            "event_type": "scene_start",
            "client_event_id": "def-001",
            "target_type": "defense",
            "target_id": 7,
            "occurred_at": int(time.time()),
        },
        headers=auth_headers,
    )
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["dedup"] is False and body["id"], f"答辩事件被丢弃：{body}"
    rows = _rows(client_event_id="def-001")
    assert len(rows) == 1 and rows[0].target_type == "defense" and rows[0].target_id == 7


def test_dimensions_snapshot_filled(client):
    """维度快照：level/age_group 取档案、channel 客户端传、server_offset_ms 服务端算。"""
    user_id = _new_profile_user(age_group="teen", level="L2")
    occurred = int(time.time()) - 2
    r = client.post(
        "/api/v1/events",
        json={
            "event_type": "page_view",
            "client_event_id": "dim-001",
            "occurred_at": occurred,
            "channel": "android",
            "browse_session_id": "browse-abc-123",
            "page": "/m/home",
        },
        headers={"X-Test-User-Id": str(user_id)},
    )
    assert r.status_code == 200
    row = _rows(client_event_id="dim-001")[0]
    assert row.level == "L2" and row.age_group == "teen"
    assert row.channel == "android"
    assert row.browse_session_id == "browse-abc-123"
    assert row.server_offset_ms is not None and 1500 <= row.server_offset_ms <= 60000


def test_guest_page_view_allowed_others_rejected(client):
    """游客 page_view 可上报（user_id NULL）；其余事件仍 401。"""
    r = client.post(
        "/api/v1/events",
        json={
            "event_type": "page_view",
            "client_event_id": "guest-001",
            "occurred_at": int(time.time()),
        },
    )
    assert r.status_code == 200 and r.json()["data"]["dedup"] is False
    rows = _rows(client_event_id="guest-001")
    assert len(rows) == 1 and rows[0].user_id is None and rows[0].level is None

    r2 = client.post(
        "/api/v1/events",
        json={"event_type": "free_chat_open", "client_event_id": "guest-002"},
    )
    assert r2.status_code == 401


def test_invalid_target_type_dropped_not_swallowed(client, auth_headers):
    """非法 target_type：显式 dropped（不再靠 DB 冲突静默当重复）。"""
    r = client.post(
        "/api/v1/events",
        json={
            "event_type": "page_view",
            "client_event_id": "bad-target-001",
            "target_type": "hack",
        },
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["data"]["dropped"] == "target_type"
    assert _rows(client_event_id="bad-target-001") == []


def test_fk_dimension_dropped_event_kept(client):
    """FK 维度（song_id）指向不存在行 → 去掉维度重试，事件本身保留。

    SQLite 默认不校验 FK（PRAGMA foreign_keys=OFF）→ 本用例先开启（StaticPool 单连接共享）；
    用户行也需真实存在（否则 user_id FK 先炸）。
    """
    from sqlalchemy import text

    user_id = _new_profile_user()
    db = get_session_factory()()
    try:
        db.execute(text("PRAGMA foreign_keys=ON"))
        db.commit()
    finally:
        db.close()

    r = client.post(
        "/api/v1/events",
        json={
            "event_type": "score_event",
            "client_event_id": "fk-001",
            "song_id": 999999,
            "target_type": "song",
        },
        headers={"X-Test-User-Id": str(user_id)},
    )
    assert r.status_code == 200 and r.json()["data"]["dedup"] is False
    row = _rows(client_event_id="fk-001")[0]
    assert row.song_id is None and row.target_type == "song"


def test_payload_whitelist_scalar_only(client, auth_headers):
    """payload 只收标量：嵌套结构丢弃 payload、事件保留；超长同样丢弃。"""
    r = client.post(
        "/api/v1/events",
        json={
            "event_type": "word_lookup",
            "client_event_id": "pl-001",
            "payload": {"word": "coffee", "nested": {"a": 1}},
        },
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert _rows(client_event_id="pl-001")[0].payload == {}

    r2 = client.post(
        "/api/v1/events",
        json={
            "event_type": "word_lookup",
            "client_event_id": "pl-002",
            "payload": {"word": "coffee"},
        },
        headers=auth_headers,
    )
    assert r2.status_code == 200
    assert _rows(client_event_id="pl-002")[0].payload == {"word": "coffee"}


def test_retired_types_still_insertable(client, auth_headers):
    """退役事件（fun_action/corpus_hit）保留枚举以兼容历史/旧客户端。"""
    for i, name in enumerate(("fun_action", "corpus_hit")):
        r = client.post(
            "/api/v1/events",
            json={"event_type": name, "client_event_id": f"retired-{i}"},
            headers=auth_headers,
        )
        assert r.status_code == 200 and r.json()["data"]["dedup"] is False
