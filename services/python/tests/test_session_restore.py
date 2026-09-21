"""R-13 会话恢复端点（GET /api/v1/sessions/{id}）回归矩阵。

2026-09-21（酒馆迁移）：dialog（英语场景对话）移除后本矩阵改用 shadow 会话
（新建会话不落开场消息；回合消息/词时间戳由测试直接落库模拟）。

- live StateStore 存在 → 运行态为权威（state/current_turn/next_seq）；
- StateStore 无记录（TTL 过期/进程重启）→ 以 scenario_messages 权威历史重建
  （state.py 注释口径「权威历史永远在 scenario_messages（不可变只 INSERT）」）；
- 归属校验（P0-3）：不拥有 → 40401（不泄露存在性）；
- 已完成会话回带 report_id（前端直接跳报告，P0-8 短路语义复用）。

修复前失败：端点不存在（404）——实现前所有用例均红。
"""

from __future__ import annotations

import asyncio

from app.db import get_session_factory
from app.models import ScenarioMessage, ShadowMaterial
from app.practice.service import complete_session
from app.practice.state import get_state_store


def _create_shadow_session(client, auth_headers) -> int:
    db = get_session_factory()()
    try:
        material = ShadowMaterial(
            title="r13-shadow",
            level=2,
            text_content="Hi! Welcome.\nNice to meet you.",
            audio_url="/demo/audio/shadow/r13.mp3",
            wpm=120,
            duration_s=10,
            interest_tags=[],
            source="demo_only",
            status="published",
        )
        db.add(material)
        db.commit()
        mid = material.id
    finally:
        db.close()
    resp = client.post(
        "/api/v1/sessions", json={"kind": "shadow", "shadow_material_id": mid}, headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    return int(resp.json()["data"]["id"])


def _insert_turn_messages(session_id: int) -> None:
    """直接落库一轮对话产物（user seq1 + assistant seq2），模拟已完成回合。"""
    db = get_session_factory()()
    db.add(
        ScenarioMessage(
            session_id=session_id,
            seq=1,
            role="user",
            origin="respond",
            content="Hi! Welcome.",
            meta={},
        )
    )
    db.add(
        ScenarioMessage(
            session_id=session_id,
            seq=2,
            role="assistant",
            content="Nice to meet you.",
            meta={},
        )
    )
    db.commit()
    db.close()


def test_restore_live_state_after_create(client, auth_headers) -> None:
    """新会话：state=awaiting_user / current_turn=0 / next_seq=1（尚无回合消息）。"""
    sid = _create_shadow_session(client, auth_headers)
    resp = client.get(f"/api/v1/sessions/{sid}", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["id"] == sid
    assert data["kind"] == "shadow"
    assert data["status"] == "active"
    assert data["state"] == "awaiting_user"
    assert data["current_turn"] == 0
    assert data["next_seq"] == 1
    assert data["next_expected_turn"] == 0
    assert data["report_id"] is None
    assert data["messages"] == []


def test_restore_prefers_live_state_over_messages(client, auth_headers) -> None:
    """StateStore 有记录时运行态为权威：即使 DB 已有消息，current_turn 仍取 state。"""
    sid = _create_shadow_session(client, auth_headers)
    _insert_turn_messages(sid)
    resp = client.get(f"/api/v1/sessions/{sid}", headers=auth_headers)
    data = resp.json()["data"]
    assert data["current_turn"] == 0
    assert data["next_seq"] == 1
    assert len(data["messages"]) == 2  # 消息快照照常回带（UI 重建）


def test_restore_rebuilds_from_messages_when_state_missing(client, auth_headers) -> None:
    """状态缺失（模拟 TTL 过期/重启）：current_turn=user 消息数、next_seq=max(seq)+1。"""
    sid = _create_shadow_session(client, auth_headers)
    _insert_turn_messages(sid)
    asyncio.run(get_state_store().delete(sid))
    resp = client.get(f"/api/v1/sessions/{sid}", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["state"] == "awaiting_user"
    assert data["current_turn"] == 1
    assert data["next_seq"] == 3
    assert data["next_expected_turn"] == 1
    assert [m["seq"] for m in data["messages"]] == [1, 2]


def test_restore_completed_returns_report_id(client, auth_headers) -> None:
    """已收尾会话：status=completed + report_id 回带（前端直接跳报告页）。"""
    sid = _create_shadow_session(client, auth_headers)
    _insert_turn_messages(sid)
    report_id = complete_session(sid, None, "done")
    asyncio.run(get_state_store().delete(sid))
    resp = client.get(f"/api/v1/sessions/{sid}", headers=auth_headers)
    data = resp.json()["data"]
    assert data["status"] == "completed"
    assert data["state"] == "completed"
    assert data["report_id"] == report_id
    assert data["current_turn"] == 1


def test_restore_ownership_404(client, auth_headers) -> None:
    """非本人会话 → 404/40401（不泄露存在性，docs/api/error-codes.md 40301 行口径）。"""
    sid = _create_shadow_session(client, auth_headers)
    resp = client.get(f"/api/v1/sessions/{sid}", headers={"X-Test-User-Id": "2"})
    assert resp.status_code == 404
    assert resp.json()["code"] == 40401


def test_restore_returns_persisted_words(client, auth_headers) -> None:
    """B4：用户消息 meta 持久化的词时间戳随恢复端点回带（断线后仍可按词对轴）。"""
    sid = _create_shadow_session(client, auth_headers)
    db = get_session_factory()()
    db.add(
        ScenarioMessage(
            session_id=sid,
            seq=1,
            role="user",
            origin="respond",
            content="Hi! Welcome.",
            audio_url="/api/v1/audio/abc.mp3",
            meta={
                "words": [
                    {"word": "Hi!", "start": 0.12, "end": 0.36, "probability": 0.99},
                    {"word": "Welcome.", "start": 0.75, "end": 1.12, "probability": 0.98},
                ]
            },
        )
    )
    db.commit()
    db.close()
    asyncio.run(get_state_store().delete(sid))
    resp = client.get(f"/api/v1/sessions/{sid}", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    user_msg = next(m for m in data["messages"] if m["role"] == "user")
    assert user_msg["words"][0] == {
        "word": "Hi!",
        "start": 0.12,
        "end": 0.36,
        "probability": 0.99,
    }
    assert user_msg["audio_url"] == "/api/v1/audio/abc.mp3"
