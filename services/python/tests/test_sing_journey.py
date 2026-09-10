"""唱歌模块 HTTP 全链路旅程测试（2026-09-10 复测轮）。

目的：把「选歌 → 建会话 → 上传 → 轮询 → 结果 → 回放 → 收藏 → 边界」串成**一条真路由的旅程**，
补上分散单测之间的缝（响应模型校验、envelope、跨端点状态流转、失败后重试）。

与 `test_sing_service.py` 的分工：那里直调 service 层（快、聚焦内部语义）；这里一律走 HTTP
（含 `response_model` 校验与全局 handler），用 Fake ffmpeg/评分器打桩，不依赖容器与外网。

覆盖：
- 选歌/详情（`favorited` + 逐句参考 f0s）/ 收藏 PUT·DELETE + 跨用户隔离；
- 建会话 → 上传 → status → result 的完整流转与响应键契约；
- 录音回放归属（本人 200 / 他人 40401 / 无 token 401）；
- 幂等（重复上传同 attempt）与 **P1-3 失败后重试**（同 attempt 就地重跑 → done）；
- 边界：40101 / 40401 / 40902 / 40905 / 40002 / 41302 / 41301 / 42901（含 `Retry-After`）。
"""

from __future__ import annotations

import io
import math

import pytest
from app.models import Lrc, Session, Song, SongPitchRef
from app.models.base import ContentStatus, PitchRefStatus
from fastapi.testclient import TestClient

SONG_ID_HOLDER: dict[str, int] = {}


def _new_db():
    from app.db import get_session_factory

    return get_session_factory()()


def _auth(uid: int) -> dict[str, str]:
    return {"X-Test-User-Id": str(uid)}


def _seed_song(*, ready: bool = True, with_lrc: int = 3) -> int:
    """song + LRC + 参考旋律（ready 时逐句 f0s/onsets_ms，pyin-v2 世代）。"""
    db = _new_db()
    try:
        song = Song(
            title="Twinkle",
            artist="Demo",
            level=1,
            duration_s=60,
            bpm=100,
            musical_key="C",
            audio_url="/data/audio/song_twinkle.wav",
            status=ContentStatus.PUBLISHED,
            pitch_ref_status=PitchRefStatus.READY if ready else PitchRefStatus.MISSING,
        )
        db.add(song)
        db.flush()
        for i in range(with_lrc):
            line = Lrc(
                song_id=song.id,
                seq=i + 1,
                offset_ms=i * 3000,
                end_offset_ms=(i + 1) * 3000,
                line_text=f"line {i + 1}",
            )
            db.add(line)
            db.flush()
            if ready:
                db.add(
                    SongPitchRef(
                        lrc_id=line.id,
                        start_ms=0,
                        end_ms=3000,
                        pitch_ref={
                            "f0s": [440.0] * 20,
                            "notes": ["A4"] * 20,
                            "midi": [69] * 20,
                            "onsets_ms": [0.0, 400.0, 800.0],
                        },
                        version="pyin-v2",
                    )
                )
        db.commit()
        return int(song.id)
    finally:
        db.close()


def _wav_bytes(duration_s: float = 2.0) -> bytes:
    """合成 440Hz 16k 单声道 wav（真实字节，过 `validate_audio_bytes` 的魔数校验）。"""
    import numpy as np
    import soundfile as sf

    sr = 16000
    t = np.linspace(0, duration_s, int(sr * duration_s), endpoint=False)
    buf = io.BytesIO()
    sf.write(buf, (0.5 * np.sin(2 * math.pi * 440 * t)).astype("float32"), sr, format="WAV")
    return buf.getvalue()


def _install_stubs(monkeypatch, tmp_path):
    """ffmpeg 桩 + Fake 评分器 + **手动驱动 worker**（不 patch asyncio，避免影响 TestClient）。"""

    async def _fake_convert(src: str, dst: str, timeout_s: float = 15.0):
        import numpy as np
        import soundfile as sf

        sr = 16000
        t = np.linspace(0, 2.0, sr * 2, endpoint=False)
        sf.write(dst, (0.5 * np.sin(2 * np.pi * 440 * t)).astype("float32"), sr)

    class _FakeScorer:
        async def score(self, audio_bytes: bytes, reference: str, language: str = "en"):
            from app.audio.base import ScoreResult

            return ScoreResult(overall=80.0, pronunciation=82.0, fluency=78.0)

    async def _noop_task(_coro):
        return None

    monkeypatch.setattr("app.sing.service.probe_duration_seconds", _probe_2s)
    monkeypatch.setattr("app.sing.service.to_16k_mono_wav", _fake_convert)
    monkeypatch.setattr("app.audio.base.get_scorer_client", lambda: _FakeScorer())
    monkeypatch.setattr("app.sing.service._run_attempt", _noop_run)
    return _fake_convert


async def _probe_2s(_path: str) -> float:
    return 2.0


async def _noop_run(_attempt_id: int) -> None:
    """占位：提交时不让后台 worker 真跑（测试手动 await `_run_attempt`）。"""


def _upload(client: TestClient, session_id: int, uid: int, audio: bytes | None = None):
    return client.post(
        f"/api/v1/sessions/{session_id}/audio",
        headers=_auth(uid),
        files={"audio": ("sing.wav", audio if audio is not None else _wav_bytes(), "audio/wav")},
    )


def _create_sing_session(client: TestClient, uid: int, song_id: int):
    return client.post(
        "/api/v1/sessions", headers=_auth(uid), json={"kind": "sing", "song_id": song_id}
    )


@pytest.mark.asyncio
async def test_sing_journey_happy_path(client: TestClient, monkeypatch, tmp_path):
    """主旅程：选歌 → 详情 → 收藏 → 建会话 → 上传 → 轮询 → 结果 → 回放。"""
    from app.sing.service import _run_attempt

    _install_stubs(monkeypatch, tmp_path)
    uid, other = 9001, 9002
    song_id = _seed_song()

    # 1) 选歌列表：envelope + 收藏态 false
    songs = client.get("/api/v1/songs", headers=_auth(uid))
    assert songs.status_code == 200, songs.text
    assert songs.json()["code"] == 0
    item = next(s for s in songs.json()["data"] if s["id"] == song_id)
    assert item["favorited"] is False
    assert item["pitch_ref_status"] == "ready"
    assert item["expected_lines"] == 3
    assert item["audio_url"], "参考旋律音频路径必须下发（前端「听参考旋律」）"

    # 2) 详情：逐句参考 f0s（双序列图数据源）
    detail = client.get(f"/api/v1/songs/{song_id}", headers=_auth(uid)).json()["data"]
    assert len(detail["lines"]) == 3
    assert detail["lines"][0]["pitch_ref"]["f0s"], "逐句参考旋律缺失"

    # 3) 收藏：PUT → true；列表可见；他人不受影响；DELETE → false（幂等）
    assert client.put(f"/api/v1/songs/{song_id}/favorite", headers=_auth(uid)).json()["data"] == {
        "song_id": song_id,
        "favorited": True,
    }
    mine = client.get("/api/v1/songs", headers=_auth(uid)).json()["data"]
    assert next(s for s in mine if s["id"] == song_id)["favorited"] is True
    theirs = client.get("/api/v1/songs", headers=_auth(other)).json()["data"]
    assert next(s for s in theirs if s["id"] == song_id)["favorited"] is False, "收藏必须按用户隔离"
    assert (
        client.delete(f"/api/v1/songs/{song_id}/favorite", headers=_auth(uid)).json()["data"][
            "favorited"
        ]
        is False
    )

    # 4) 建会话 → 上传：受理回执**只有 attempt_id/status**（P1-14 契约）
    created = _create_sing_session(client, uid, song_id)
    assert created.status_code == 200, created.text
    session_id = created.json()["data"]["id"]
    up = _upload(client, session_id, uid)
    assert up.status_code == 200, up.text
    ack = up.json()["data"]
    assert set(ack) == {"attempt_id", "status"}, ack
    assert ack["status"] == "queued"
    attempt_id = ack["attempt_id"]

    # 5) 轮询：queued → （结果未就绪 40902）→ 驱动 worker → done
    st = client.get(f"/api/v1/sing/attempts/{attempt_id}/status", headers=_auth(uid)).json()["data"]
    assert st["status"] == "queued" and st["progress"] == {"done_lines": 0, "total": 0}
    early = client.get(f"/api/v1/sing/attempts/{attempt_id}", headers=_auth(uid))
    assert early.status_code == 409 and early.json()["code"] == 40902

    await _run_attempt(attempt_id)
    st = client.get(f"/api/v1/sing/attempts/{attempt_id}/status", headers=_auth(uid)).json()["data"]
    assert st["status"] == "done", st
    assert st["progress"]["total"] == 3

    # 6) 结果：键契约 + 分数 + 逐句 + 对齐留痕
    res = client.get(f"/api/v1/sing/attempts/{attempt_id}", headers=_auth(uid))
    assert res.status_code == 200, res.text
    r = res.json()["data"]
    assert set(r) == {
        "id",
        "song_id",
        "audio_url",
        "duration_s",
        "overall",
        "pitch",
        "rhythm",
        "pron",
        "is_complete",
        "expected_lines",
        "scoring_version",
        "ref_version",
        "lines",
        "alignment",
        "created_at",
    }, set(r)
    assert r["scoring_version"] == "v6"
    assert r["ref_version"] == "pyin-v2"
    assert abs(r["overall"] - 91.1) < 0.01, r["overall"]  # 0.5·95+0.2·95+0.3·82
    assert r["is_complete"] is True and r["expected_lines"] == 3
    assert r["alignment"]["method"] == "dtw-local-sakoe-chiba-v3"
    assert r["alignment"]["bpm_source"] in (
        "onset-f0",
        "onset-flux",
        "onset-arbitrated",
        "duration",
    ), r["alignment"]["bpm_source"]
    assert len(r["lines"]) == 3
    assert r["lines"][0]["user_f0"] and "cent_dev" in r["lines"][0]

    # 7) 录音回放归属：本人 200 / 他人 403（音频越权口径 = 40301）/ 无 token 401
    name = r["audio_url"].rsplit("/", 1)[-1]
    assert client.get(f"/api/v1/audio/{name}", headers=_auth(uid)).status_code == 200
    foreign_play = client.get(f"/api/v1/audio/{name}", headers=_auth(other))
    assert foreign_play.status_code == 403 and foreign_play.json()["code"] == 40301, (
        foreign_play.text
    )
    assert client.get(f"/api/v1/audio/{name}").status_code == 401

    # 8) 幂等：已定稿后重复上传 → 同一 attempt 且仍是 done（不重复扣桶/建任务）
    again = _upload(client, session_id, uid)
    assert again.status_code == 200, again.text
    assert again.json()["data"]["attempt_id"] == attempt_id
    assert again.json()["data"]["status"] == "done"


@pytest.mark.asyncio
async def test_sing_journey_retry_after_failure(client: TestClient, monkeypatch, tmp_path):
    """P1-3 端到端：评分失败 → 同会话重试**就地重跑**（同 attempt_id）→ done。

    修复前必失败：幂等分支无条件复用 failed 行 → 重试永远回 `failed`（用户无法重录）。
    """
    from app.sing.service import _run_attempt

    fake_convert = _install_stubs(monkeypatch, tmp_path)
    uid = 9003
    song_id = _seed_song()
    session_id = _create_sing_session(client, uid, song_id).json()["data"]["id"]

    # 第一轮：管线崩 → failed（50003）+ 分数 NULL
    async def _boom(*_args, **_kwargs):
        raise RuntimeError("pipeline crash")

    monkeypatch.setattr("app.sing.service.to_16k_mono_wav", _boom)
    first = _upload(client, session_id, uid).json()["data"]
    await _run_attempt(first["attempt_id"])
    st = client.get(
        f"/api/v1/sing/attempts/{first['attempt_id']}/status", headers=_auth(uid)
    ).json()["data"]
    assert st["status"] == "failed" and st["code"] == 50003, st
    assert "pipeline crash" not in (st.get("error") or ""), "异常细节不得回传客户端"

    # 第二轮：管线恢复 → 必须能重跑（修复前回 failed）
    monkeypatch.setattr("app.sing.service.to_16k_mono_wav", fake_convert)
    second = _upload(client, session_id, uid)
    assert second.status_code == 200, second.text
    assert second.json()["data"]["attempt_id"] == first["attempt_id"], "唯一键下必须复用同一行"
    assert second.json()["data"]["status"] == "queued", "修复前此处为 failed"
    await _run_attempt(first["attempt_id"])
    assert (
        client.get(
            f"/api/v1/sing/attempts/{first['attempt_id']}/status", headers=_auth(uid)
        ).json()["data"]["status"]
        == "done"
    )
    db = _new_db()
    try:
        rows = db.query(Session).filter(Session.id == session_id).all()
        assert rows, "会话仍在"
    finally:
        db.close()


def test_sing_journey_authorization_and_boundaries(client: TestClient, monkeypatch, tmp_path):
    """边界：40101 / 40401 / 40905 / 40002 / 41302 / 41301 / 42901（含 Retry-After）。"""
    import app.core.ratelimit as rl
    from app.core.config import get_settings

    _install_stubs(monkeypatch, tmp_path)
    uid, other = 9004, 9005
    song_id = _seed_song()
    other_song_id = _seed_song(ready=False)  # 参考旋律未就绪
    session_id = _create_sing_session(client, uid, song_id).json()["data"]["id"]
    attempt_id = _upload(client, session_id, uid).json()["data"]["attempt_id"]

    # 无 token → 40101 envelope
    unauth = client.get(f"/api/v1/sing/attempts/{attempt_id}/status")
    assert unauth.status_code == 401 and unauth.json()["code"] == 40101, unauth.text

    # 他人 attempt → 40401（不泄露存在性）
    foreign = client.get(f"/api/v1/sing/attempts/{attempt_id}/status", headers=_auth(other))
    assert foreign.status_code == 404 and foreign.json()["code"] == 40401, foreign.text

    # 参考旋律未就绪的歌曲 → 建会话 40905
    not_ready = _create_sing_session(client, uid, other_song_id)
    assert not_ready.status_code == 409 and not_ready.json()["code"] == 40905, not_ready.text

    # 非 sing 会话上传 → 40401
    db = _new_db()
    try:
        dialog = Session(user_id=uid, kind="dialog", assigned_turns=3)
        db.add(dialog)
        db.commit()
        dialog_id = int(dialog.id)
    finally:
        db.close()
    wrong_kind = _upload(client, dialog_id, uid)
    assert wrong_kind.status_code == 404 and wrong_kind.json()["code"] == 40401, wrong_kind.text

    # 音频过短 → 40002（**新会话**：同会话会先命中幂等分支）
    sid2 = _create_sing_session(client, uid, song_id).json()["data"]["id"]
    tiny = _upload(client, sid2, uid, audio=b"RIFF0000WAVE")
    assert tiny.status_code >= 400, tiny.text
    assert tiny.json()["code"] in (40002, 41301), tiny.text

    # 超 180s → 41302（时长探测打桩）
    async def _probe_300(_path: str) -> float:
        return 300.0

    monkeypatch.setattr("app.sing.service.probe_duration_seconds", _probe_300)
    sid3 = _create_sing_session(client, uid, song_id).json()["data"]["id"]
    too_long = _upload(client, sid3, uid)
    assert too_long.status_code == 413 and too_long.json()["code"] == 41302, too_long.text

    # 体量超限 → 41301（BodySizeLimitMiddleware 在路由前拦截）
    settings = get_settings()
    sid4 = _create_sing_session(client, uid, song_id).json()["data"]["id"]
    huge = _upload(client, sid4, uid, audio=b"RIFF" + b"\x00" * (settings.max_upload_bytes + 1024))
    assert huge.status_code == 413 and huge.json()["code"] == 41301, huge.text[:200]

    # 限流 → 42901 envelope + Retry-After（ISE 桶置 0：真实多桶判定路径）
    monkeypatch.setattr(
        "app.sing.service.probe_duration_seconds", _probe_2s
    )  # 复原：时长校验先于限流
    monkeypatch.setattr(settings, "ise_rate_per_hour", 0)
    rl.TRACE.clear()
    sid5 = _create_sing_session(client, uid, song_id).json()["data"]["id"]
    limited = _upload(client, sid5, uid)
    assert limited.status_code == 429, limited.text
    assert limited.json()["code"] == 42901, limited.text
    assert int(limited.headers.get("Retry-After", "0")) >= 1, (
        "429 必须带 Retry-After（docs/api/error-codes.md）"
    )
    # P1-13：被拒请求不消耗任何桶（sing 桶计数必须为 0）
    import time as _time

    key = ("sing", str(uid), rl._window(_time.time()))
    assert rl.TRACE.get(key, (0, 0))[0] == 0, "ise 超限时 sing 桶不得被扣（P1-13）"


def test_sing_journey_unknown_song_and_attempt(client: TestClient, monkeypatch, tmp_path):
    """不存在/未发布资源：歌曲 40401；attempt 不存在 40401（不区分他人/不存在）。"""
    _install_stubs(monkeypatch, tmp_path)
    uid = 9006
    ghost_song = client.get("/api/v1/songs/999999", headers=_auth(uid))
    assert ghost_song.status_code == 404 and ghost_song.json()["code"] == 40401, ghost_song.text
    ghost_attempt = client.get("/api/v1/sing/attempts/999999/status", headers=_auth(uid))
    assert ghost_attempt.status_code == 404 and ghost_attempt.json()["code"] == 40401
    ghost_result = client.get("/api/v1/sing/attempts/999999", headers=_auth(uid))
    assert ghost_result.status_code == 404 and ghost_result.json()["code"] == 40401
    # 收藏不存在的歌 → 40401（幂等语义不掩盖存在性校验）
    fav = client.put("/api/v1/songs/999999/favorite", headers=_auth(uid))
    assert fav.status_code == 404 and fav.json()["code"] == 40401, fav.text
    del fav
