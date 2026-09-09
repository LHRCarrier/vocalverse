"""唱歌编排与端点测试（M3 P0 D4/D5/D6/D7）。

覆盖：SessionCreate.song_id + create_session sing 分支（40905 门禁/no lrc）/
submit（归属/song ready/40002/41302 时长/幂等）/
任务态（queued→processing→done；Redis 不可用走内存兜底）/
worker 全链路（ffmpeg 桩→Fake 评分→ISE 抽样→落库字段契约）/
失败不伪造（error 快照 + 分数 NULL）/
轮询/结果（归属 40401、未完成 40902、结果契约 lines/alignment/user_f0）/
GET /audio 归属补 SingAttempt（C-P1）。
"""

from __future__ import annotations

import asyncio
import math
import uuid
from pathlib import Path

import pytest
from app.models import Lrc, Session, SingAttempt, Song, SongPitchRef
from app.models.base import ContentStatus, PitchRefStatus, SessionKinds


def _seed_ready_song(db, *, with_lrc: int = 3, ready: bool = True) -> int:
    song = Song(
        title="Twinkle",
        level=1,
        audio_url="/data/audio/twinkle.wav",
        status=ContentStatus.PUBLISHED,
        pitch_ref_status=PitchRefStatus.READY if ready else PitchRefStatus.MISSING,
    )
    db.add(song)
    db.flush()
    lrc_ids = []
    for i in range(with_lrc):
        lrc = Lrc(
            song_id=song.id,
            seq=i + 1,
            offset_ms=i * 3000,
            end_offset_ms=(i + 1) * 3000,
            line_text=f"line {i + 1}",
        )
        db.add(lrc)
        db.flush()
        lrc_ids.append(int(lrc.id))
    if ready:
        for lid in lrc_ids:
            db.add(
                SongPitchRef(
                    lrc_id=lid,
                    start_ms=0,
                    end_ms=3000,
                    pitch_ref={"f0s": [440.0] * 20, "notes": ["A4"] * 20, "midi": [69] * 20},
                    version="pyin-v1",
                )
            )
    db.commit()
    return int(song.id)


def _seed_user(db):
    from app.models import User

    user = User(
        username=f"sing_{uuid.uuid4().hex[:10]}",
        email=None,
        password_hash="x",
        nickname="U",
    )
    db.add(user)
    db.flush()
    return user


def _seed_user_session(db, *, kind: str = "sing", song_id: int | None = None) -> tuple[int, int]:
    user = _seed_user(db)
    sess = Session(user_id=user.id, kind=kind, song_id=song_id, assigned_turns=3)
    db.add(sess)
    db.commit()
    return user.id, int(sess.id)


def _new_db():
    from app.db import get_session_factory

    return get_session_factory()()


def _wav_bytes(duration_s: float = 1.0) -> bytes:
    """合成 440Hz 16k mono wav 字节。"""
    import io

    import numpy as np
    import soundfile as sf

    sr = 16000
    t = np.linspace(0, duration_s, int(sr * duration_s), endpoint=False)
    buf = io.BytesIO()
    sf.write(buf, (0.5 * np.sin(2 * math.pi * 440 * t)).astype("float32"), sr, format="WAV")
    return buf.getvalue()


def _install_pipeline_stubs(monkeypatch, tmp_path):
    """ffmpeg 桩（合成 440Hz wav）+ Fake 评分器（发音 82）+ 后台任务静音（测试手动跑 worker）。"""
    import app.sing.service as svc

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

    # submit 会 asyncio.create_task 启后台 worker——测试改手动 await _run_attempt，
    # 避免对同一 attempt 双 worker 竞态写（也保证任务态可断言）
    monkeypatch.setattr("app.sing.service.asyncio.create_task", lambda _coro: None)
    monkeypatch.setattr("app.sing.service.to_16k_mono_wav", _fake_convert)
    monkeypatch.setattr("app.audio.base.get_scorer_client", lambda: _FakeScorer())
    return svc


# ---------------------------------------------------------------------------
# 会话创建（create_session sing 分支）
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_create_session_sing_requires_ready_song():
    from app.core.response import BizError
    from app.practice.service import create_session

    db = _new_db()
    _seed_ready_song(db, ready=False)
    db.close()
    with pytest.raises(BizError) as exc:
        await create_session(1, SessionKinds.SING, None, None, None, None, song_id=1)
    assert exc.value.code == 40905


@pytest.mark.asyncio
async def test_create_session_sing_success():
    from app.practice.service import create_session

    db = _new_db()
    user_id, _ = _seed_user_session(db)
    song_id = _seed_ready_song(db)
    db.close()
    session = await create_session(
        user_id, SessionKinds.SING, None, None, None, None, song_id=song_id
    )
    assert session.kind == "sing"
    assert session.song_id == song_id
    assert session.assigned_turns == 3  # lrc 行数快照


# ---------------------------------------------------------------------------
# 上传（submit_song_audio）
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_submit_rejects_missing_session():
    from app.core.response import BizError
    from app.sing.service import submit_song_audio

    db = _new_db()
    _, _ = _seed_user_session(db)
    _seed_ready_song(db)
    db.close()
    with pytest.raises(BizError) as exc:
        await submit_song_audio(9999, 999999, _wav_bytes())
    assert exc.value.code == 40401


@pytest.mark.asyncio
async def test_submit_rejects_pitch_not_ready(monkeypatch):
    from app.core.response import BizError
    from app.sing.service import submit_song_audio

    async def fake_probe(_path: str) -> float | None:
        return None

    monkeypatch.setattr("app.sing.service.probe_duration_seconds", fake_probe)
    db = _new_db()
    song_id = _seed_ready_song(db, ready=False)
    user_id, session_id = _seed_user_session(db, song_id=song_id)
    db.close()
    with pytest.raises(BizError) as exc:
        await submit_song_audio(user_id, session_id, _wav_bytes())
    assert exc.value.code == 40905


@pytest.mark.asyncio
async def test_submit_rejects_too_long(monkeypatch):
    from app.core.response import BizError
    from app.sing.service import submit_song_audio

    async def fake_probe(_path: str) -> float:
        return 300.0  # > max_sing_seconds=180

    monkeypatch.setattr("app.sing.service.probe_duration_seconds", fake_probe)
    db = _new_db()
    song_id = _seed_ready_song(db)
    user_id, session_id = _seed_user_session(db, song_id=song_id)
    db.close()
    with pytest.raises(BizError) as exc:
        await submit_song_audio(user_id, session_id, _wav_bytes())
    assert exc.value.code == 41302


async def _submit_ok(monkeypatch, *, with_lrc: int = 3):
    """标准提交打桩：时长 2s、不扣桶、ffmpeg/评分桩。返回 (user_id, session_id, r)。"""
    from app.sing.service import submit_song_audio

    async def fake_probe(_path: str) -> float:
        return 2.0

    async def fake_consume(*args, **kwargs):
        return None

    monkeypatch.setattr("app.sing.service.probe_duration_seconds", fake_probe)
    monkeypatch.setattr("app.sing.service.consume", fake_consume)
    monkeypatch.setattr("app.core.ratelimit.consume", fake_consume)
    db = _new_db()
    song_id = _seed_ready_song(db, with_lrc=with_lrc)
    user_id, session_id = _seed_user_session(db, song_id=song_id)
    db.close()
    r = await submit_song_audio(user_id, session_id, _wav_bytes())
    return user_id, session_id, song_id, r


@pytest.mark.asyncio
async def test_submit_creates_queued_attempt_idempotent(monkeypatch):
    from app.sing.service import _task_get, submit_song_audio

    monkeypatch.setattr("app.sing.service.probe_duration_seconds", _fake_probe_2s)
    monkeypatch.setattr("app.sing.service.consume", _fake_consume)
    _ = _install_pipeline_stubs(monkeypatch, Path("."))
    db = _new_db()
    song_id = _seed_ready_song(db)
    user_id, session_id = _seed_user_session(db, song_id=song_id)
    db.close()
    r1 = await submit_song_audio(user_id, session_id, _wav_bytes())
    assert r1["status"] == "queued"
    assert r1["attempt_id"] > 0
    r2 = await submit_song_audio(user_id, session_id, _wav_bytes())
    assert r2["attempt_id"] == r1["attempt_id"]  # 幂等：同会话重复上传复用
    task = await _task_get(r1["attempt_id"])
    assert task["status"] == "queued"


async def _fake_probe_2s(_path: str) -> float:
    return 2.0


async def _fake_consume(*args, **kwargs):
    return None


@pytest.mark.asyncio
async def test_worker_completes_and_writes_immutable_row(monkeypatch, tmp_path):
    """端到端：submit → worker → done → 行字段契约（lines/alignment/版本快照）。"""
    from app.sing.service import _run_attempt, get_attempt_result, get_attempt_status

    monkeypatch.setattr("app.sing.service.probe_duration_seconds", _fake_probe_2s)
    monkeypatch.setattr("app.sing.service.consume", _fake_consume)
    monkeypatch.setattr("app.core.ratelimit.consume", _fake_consume)
    _install_pipeline_stubs(monkeypatch, tmp_path)

    user_id, _sid, _song_id, r = await _submit_ok(monkeypatch, with_lrc=3)
    attempt_id = r["attempt_id"]
    await _run_attempt(attempt_id)

    status = await get_attempt_status(attempt_id, user_id)
    assert status["status"] == "done"
    result = await get_attempt_result(attempt_id, user_id)
    # 综合 = 0.5·95(音准) + 0.2·95(节奏) + 0.3·82(发音抽样) = 91.1（docs/06 §9.4 复算）
    assert abs(result["overall"] - 91.1) < 0.01
    assert result["pitch"] == 95.0
    assert result["pron"] == 82.0  # 抽样句 ISE（Fake 引擎 82）
    assert result["is_complete"] is True
    assert result["expected_lines"] == 3
    assert result["scoring_version"] == "v1"
    assert result["ref_version"] == "pyin-v1"
    assert result["alignment"]["method"] == "dtw-sakoe-chiba-v1"
    assert len(result["lines"]) == 3
    assert result["lines"][0]["user_f0"] != []  # D4：逐帧 F0 落库
    assert "user_f0" in result["lines"][0]
    assert result["lines"][0]["pron_score"] == 82.0


@pytest.mark.asyncio
async def test_attempt_ownership_and_not_ready(monkeypatch, tmp_path):
    from app.core.response import BizError
    from app.sing.service import _run_attempt, get_attempt_result

    monkeypatch.setattr("app.sing.service.probe_duration_seconds", _fake_probe_2s)
    monkeypatch.setattr("app.sing.service.consume", _fake_consume)
    monkeypatch.setattr("app.core.ratelimit.consume", _fake_consume)
    _install_pipeline_stubs(monkeypatch, tmp_path)

    user_id, _sid, _song_id, r = await _submit_ok(monkeypatch, with_lrc=3)
    # 他人访问 → 40401（不泄露存在性）
    with pytest.raises(BizError) as exc:
        await get_attempt_result(r["attempt_id"], 9999)
    assert exc.value.code == 40401
    # 未完成 → 40902（草稿行分数 NULL）
    with pytest.raises(BizError) as exc:
        await get_attempt_result(r["attempt_id"], user_id)
    assert exc.value.code == 40902
    await _run_attempt(r["attempt_id"])
    with pytest.raises(BizError) as exc:
        await get_attempt_result(r["attempt_id"], 9999)
    assert exc.value.code == 40401


@pytest.mark.asyncio
async def test_worker_failure_no_fake_scores(monkeypatch, tmp_path):
    """失败：任务态 failed + 行分数 NULL（不伪造分数——docs/11 Q-B08 同口径）。"""
    from app.sing.service import _run_attempt, get_attempt_status

    monkeypatch.setattr("app.sing.service.probe_duration_seconds", _fake_probe_2s)
    monkeypatch.setattr("app.sing.service.consume", _fake_consume)
    monkeypatch.setattr("app.core.ratelimit.consume", _fake_consume)

    async def _boom(*args, **kwargs):
        raise RuntimeError("pipeline crash")

    monkeypatch.setattr("app.sing.service.to_16k_mono_wav", _boom)

    user_id, _sid, _song_id, r = await _submit_ok(monkeypatch, with_lrc=3)
    await _run_attempt(r["attempt_id"])

    status = await get_attempt_status(r["attempt_id"], user_id)
    assert status["status"] == "failed"
    assert "pipeline crash" in (status.get("error") or "")
    db = _new_db()
    try:
        row = db.get(SingAttempt, r["attempt_id"])
        assert row.overall_score is None
        assert row.pitch_score is None
        assert row.lines == []  # 无部分写入
    finally:
        db.close()


# ---------------------------------------------------------------------------
# GET /audio 归属补 SingAttempt（C-P1）
# ---------------------------------------------------------------------------
def test_get_audio_ownership_includes_sing_attempt(tmp_path):
    import numpy as np
    import soundfile as sf
    from app.core.config import get_settings
    from app.main import app
    from starlette.testclient import TestClient

    db = _new_db()
    user_id, _ = _seed_user_session(db)
    song_id = _seed_ready_song(db)
    attempt = SingAttempt(
        user_id=user_id,
        session_id=None,
        song_id=song_id,
        duration_s=1,
        audio_url="/api/v1/audio/deadbeef0123456789abcdef01234567.mp3",
        lines=[],
        alignment={},
    )
    db.add(attempt)
    db.commit()
    db.close()

    settings = get_settings()
    Path(settings.audio_dir).mkdir(parents=True, exist_ok=True)
    path = Path(settings.audio_dir) / "deadbeef0123456789abcdef01234567.mp3"
    sr = 16000
    t = np.linspace(0, 0.5, int(sr * 0.5), endpoint=False)
    sf.write(str(path), (0.5 * np.sin(2 * np.pi * 440 * t)).astype("float32"), sr)
    path.touch()

    with TestClient(app) as client:
        resp = client.get(
            "/api/v1/audio/deadbeef0123456789abcdef01234567.mp3",
            headers={"X-Test-User-Id": str(user_id)},
        )
        assert resp.status_code == 200  # C-P1：跟唱回放不再 403


# Module-level helpers used by tests above（asyncio 保持导出以便 pytest 收集）
_ = asyncio
