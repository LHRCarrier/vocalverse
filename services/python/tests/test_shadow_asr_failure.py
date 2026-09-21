"""影子跟读 ASR 失败降级回归（BUG 归档：worklog/BUG实测/影子跟读ASR失败NameError.md）。

背景：`_shadow_turn` 的 ASR 异常路径引用未绑定的 `res`（`getattr(res, "no_speech", False)`），
ASR 抛错时抛 `NameError` → 路由兜成 `error(internal)`，用户只看到「管线提示：internal」
而不是「听不清请再试」的友好降级。修复：try 前 `res = None`。

本用例在修复前会失败（SSE 出现 error/internal、无 turn_end），修复后通过。
"""

from __future__ import annotations

import json

from app.audio.base import ASRResult


class _RaisingASR:
    """ASR 桩：transcribe 抛错（模拟引擎崩溃/上游 503）。"""

    async def transcribe(self, audio_bytes: bytes, language: str = "en") -> ASRResult:
        raise RuntimeError("asr engine exploded")


def _sse_events(text: str) -> list[dict]:
    out = []
    for line in text.splitlines():
        if line.startswith("data: "):
            out.append(json.loads(line[6:]))
    return out


def test_shadow_asr_failure_degrades_gracefully(client, auth_headers, monkeypatch):
    from app.api.routes import practice as practice_route

    # 复用 test_m2_core 的会话构造（影子素材 + 会话）
    from tests.test_m2_core import FAKE_AUDIO, _make_shadow_session

    session_id = _make_shadow_session(client, auth_headers)

    class _Orchestrator:
        async def run(self, *args, **kwargs):
            from app.practice.orchestrator import get_orchestrator

            orchestrator = get_orchestrator()
            orchestrator._asr = _RaisingASR()  # type: ignore[attr-defined]
            async for event in orchestrator.run(*args, **kwargs):
                yield event

    monkeypatch.setattr(practice_route, "get_orchestrator", lambda: _Orchestrator())

    resp = client.post(
        f"/api/v1/sessions/{session_id}/turns",
        data={"action": "normal"},
        files={"audio": ("a.webm", FAKE_AUDIO, "audio/webm")},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    events = _sse_events(resp.text)
    types = [e["type"] for e in events]
    # 修复前：error(internal) 且无 turn_end；修复后：正常收尾（评分缺省降级）
    assert "error" not in types, events
    assert "turn_end" in types


def test_shadow_asr_none_speech_still_notes(client, auth_headers):
    """对照：正常 Fake ASR 路径不回归（turn_start → turn_end）。"""
    from tests.test_m2_core import FAKE_AUDIO, _make_shadow_session

    session_id = _make_shadow_session(client, auth_headers)
    resp = client.post(
        f"/api/v1/sessions/{session_id}/turns",
        data={"action": "normal"},
        files={"audio": ("a.webm", FAKE_AUDIO, "audio/webm")},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    types = [e["type"] for e in _sse_events(resp.text)]
    assert "turn_start" in types and "turn_end" in types and "error" not in types
