"""R-13 会话恢复端点（GET /api/v1/sessions/{id}）回归矩阵。

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
from app.models import Scenario, ScenarioMessage
from app.practice.service import complete_session
from app.practice.state import get_state_store

ACCENT = "Hi! Welcome."


def _create_dialog_session(client, auth_headers) -> int:
    db = get_session_factory()()
    scenario = Scenario(
        title="r13-cafe",
        scene_type="cafe",
        difficulty=1,
        system_prompt="You are Bella, a friendly barista.",
        opening_line=ACCENT,
        target_corpus="I'd like a coffee, please.|请给我来杯咖啡",
        interest_tags=[],
        status="published",
    )
    db.add(scenario)
    db.commit()
    sid = scenario.id
    db.close()
    resp = client.post(
        "/api/v1/sessions", json={"kind": "dialog", "scenario_id": sid}, headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    return int(resp.json()["data"]["id"])


def _insert_turn_messages(session_id: int) -> None:
    """直接落库一轮对话产物（user seq2 + assistant seq3），模拟已完成回合。"""
    db = get_session_factory()()
    db.add(
        ScenarioMessage(
            session_id=session_id,
            seq=2,
            role="user",
            origin="respond",
            content="I'd like a coffee, please.",
            meta={},
        )
    )
    db.add(
        ScenarioMessage(
            session_id=session_id,
            seq=3,
            role="assistant",
            content="Here you go!",
            meta={},
        )
    )
    db.commit()
    db.close()


def test_restore_live_state_after_create(client, auth_headers) -> None:
    """新会话：state=awaiting_user / current_turn=0 / next_seq=2（开场占 seq1）。"""
    sid = _create_dialog_session(client, auth_headers)
    resp = client.get(f"/api/v1/sessions/{sid}", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["id"] == sid
    assert data["kind"] == "dialog"
    assert data["status"] == "active"
    assert data["state"] == "awaiting_user"
    assert data["current_turn"] == 0
    assert data["next_seq"] == 2
    assert data["next_expected_turn"] == 0
    assert data["report_id"] is None
    assert [m["role"] for m in data["messages"]] == ["assistant"]
    assert data["messages"][0]["content"] == ACCENT


def test_restore_prefers_live_state_over_messages(client, auth_headers) -> None:
    """StateStore 有记录时运行态为权威：即使 DB 已有消息，current_turn 仍取 state。"""
    sid = _create_dialog_session(client, auth_headers)
    _insert_turn_messages(sid)
    resp = client.get(f"/api/v1/sessions/{sid}", headers=auth_headers)
    data = resp.json()["data"]
    assert data["current_turn"] == 0
    assert data["next_seq"] == 2
    assert len(data["messages"]) == 3  # 消息快照照常回带（UI 重建）


def test_restore_rebuilds_from_messages_when_state_missing(client, auth_headers) -> None:
    """状态缺失（模拟 TTL 过期/重启）：current_turn=user 消息数、next_seq=max(seq)+1。"""
    sid = _create_dialog_session(client, auth_headers)
    _insert_turn_messages(sid)
    asyncio.run(get_state_store().delete(sid))
    resp = client.get(f"/api/v1/sessions/{sid}", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["state"] == "awaiting_user"
    assert data["current_turn"] == 1
    assert data["next_seq"] == 4
    assert data["next_expected_turn"] == 1
    assert [m["seq"] for m in data["messages"]] == [1, 2, 3]


def test_restore_completed_returns_report_id(client, auth_headers) -> None:
    """已收尾会话：status=completed + report_id 回带（前端直接跳报告页）。"""
    sid = _create_dialog_session(client, auth_headers)
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
    sid = _create_dialog_session(client, auth_headers)
    resp = client.get(f"/api/v1/sessions/{sid}", headers={"X-Test-User-Id": "2"})
    assert resp.status_code == 404
    assert resp.json()["code"] == 40401


def test_restore_returns_persisted_words(client, auth_headers) -> None:
    """B4：用户消息 meta 持久化的词时间戳随恢复端点回带（断线后仍可按词对轴）。"""
    sid = _create_dialog_session(client, auth_headers)
    db = get_session_factory()()
    db.add(
        ScenarioMessage(
            session_id=sid,
            seq=2,
            role="user",
            origin="respond",
            content="I'd like a coffee, please.",
            audio_url="/api/v1/audio/abc.mp3",
            meta={
                "words": [
                    {"word": "I'd", "start": 0.12, "end": 0.36, "probability": 0.99},
                    {"word": "coffee", "start": 0.75, "end": 1.12, "probability": 0.98},
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
        "word": "I'd",
        "start": 0.12,
        "end": 0.36,
        "probability": 0.99,
    }
    assert user_msg["audio_url"] == "/api/v1/audio/abc.mp3"
