"""自由对话（MVP，docs/14 §12）：无状态 LLM 流式（Fake 全链路）+ 契约/校验。

约定同 docs/14 §3.3：SSE 事件为单行 `data: {json}`；本端点只发
user_transcript / text_delta / turn_end / error 子集。
"""

from __future__ import annotations

import json

FAKE_AUDIO = b"fake-audio-bytes" * 128


def _events(resp_text: str) -> list[dict]:
    out: list[dict] = []
    for line in resp_text.splitlines():
        if line.startswith("data: "):
            out.append(json.loads(line[6:]))
    return out


def test_free_chat_in_openapi(client):
    """产品端点：进契约快照（与 test_only 端点（404 断言）相反）。"""
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/free-chat/turn" in paths


def test_text_turn_streams_reply(client, auth_headers):
    resp = client.post(
        "/api/v1/free-chat/turn",
        data={"text": "Hi there!", "history": "[]"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    evs = _events(resp.text)
    types = [e["type"] for e in evs]
    assert "text_delta" in types and "turn_end" in types
    assert types[0] == "text_delta"  # 打字轮无 user_transcript
    reply = "".join(e["text"] for e in evs if e["type"] == "text_delta")
    assert "Of course" in reply  # Fake LLM 首段（docs/06 第 6 章打桩）
    end = [e for e in evs if e["type"] == "turn_end"][0]
    assert end["turn_index"] == 1
    assert end["score_status"] == "unavailable"  # 自由对话 MVP 无评分


def test_audio_turn_emits_user_transcript(client, auth_headers):
    resp = client.post(
        "/api/v1/free-chat/turn",
        files={"audio": ("a.webm", FAKE_AUDIO, "audio/webm")},
        data={"history": "[]"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    evs = _events(resp.text)
    assert evs[0]["type"] == "user_transcript"
    assert "[stub]" in evs[0]["text"]  # FakeASR（无真 Key）
    assert "text_delta" in [e["type"] for e in evs]


def test_history_carried_and_turn_index(client, auth_headers):
    history = json.dumps(
        [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello! How are you?"},
        ]
    )
    resp = client.post(
        "/api/v1/free-chat/turn",
        data={"text": "I'm good", "history": history},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    evs = _events(resp.text)
    end = [e for e in evs if e["type"] == "turn_end"][0]
    assert end["turn_index"] == 2  # 1 条历史 user + 当前轮


def test_missing_input_422(client, auth_headers):
    resp = client.post(
        "/api/v1/free-chat/turn",
        data={"history": "[]"},
        headers=auth_headers,
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == 42204


def test_bad_history_422(client, auth_headers):
    resp = client.post(
        "/api/v1/free-chat/turn",
        data={"text": "hi", "history": "not-json"},
        headers=auth_headers,
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == 42203
