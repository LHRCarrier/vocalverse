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
from fastapi import HTTPException
from sqlalchemy import select


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
                    pitch_ref={
                        "f0s": [440.0] * 20,
                        "notes": ["A4"] * 20,
                        "midi": [69] * 20,
                        # pyin-v2：参考音符级 onset（item7 参考侧数据源；
                        # 缺失则 bpm_source=duration）
                        "onsets_ms": [0.0, 400.0, 800.0, 1200.0, 1600.0],
                    },
                    version="pyin-v2",
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
# 发音抽样句窗（2026-09-10 P0 修复回归）
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_pron_sample_window_follows_user_timeline(tmp_path, monkeypatch):
    """发音抽样切窗必须落在**用户时间轴**（参考 + offset，句长再乘 window_scale）。

    2026-09-10 BUG 回归（**修复前必失败**）：旧实现为 `line.start_ms - offset`（方向反）→
    offset>0（用户整体晚起唱）时切片落在静音/别的句子上，占综合 0.3 权重的发音分与真实
    演唱无关。用「只在用户时间轴窗口内有声」的合成 wav 即可判别：修复前 rms=0、修复后 ≈0.35。
    依据：docs/06 §9.4（时间轴不变式 + BUG-4 句窗缩放）、docs/21 §3.6、docs/10 §4.3。
    """
    import io
    from types import SimpleNamespace

    import numpy as np
    import soundfile as sf
    from app.audio.sing import LineScore, SingScoreResult

    sr = 16000
    y = np.zeros(int(sr * 6.0), dtype="float32")
    # 参考句 [2000,3000)ms；用户整体晚 1500ms → 用户时间轴上该句在 [3500,4500)
    tone = 0.5 * np.sin(2 * np.pi * 440 * np.arange(int(sr * 1.0)) / sr)
    y[int(sr * 3.5) : int(sr * 4.5)] = tone
    wav = tmp_path / "user_timeline.wav"
    sf.write(wav, y, sr, format="WAV")

    result = SingScoreResult(
        lines=[
            LineScore(
                seq=1,
                start_ms=2000,
                end_ms=3000,
                pitch_score=90.0,
                rhythm_score=90.0,
                pron_score=None,
            )
        ],
        alignment={"offset_ms": 1500, "bpm_ratio": 1.0},
    )
    seen: list[float] = []

    class _RecordingScorer:
        async def score(self, audio_bytes: bytes, reference: str, language: str = "en"):
            data, _ = sf.read(io.BytesIO(audio_bytes), dtype="float32")
            seen.append(float(np.sqrt(np.mean(data**2))) if len(data) else 0.0)
            return SimpleNamespace(pronunciation=88.0)

    monkeypatch.setattr("app.audio.base.get_scorer_client", lambda: _RecordingScorer())
    from app.sing.service import _pron_sample_lines

    scores = await _pron_sample_lines(str(wav), result, 1)
    assert scores == {1: 88.0}
    assert seen and seen[0] > 0.2, f"切窗落在静音段（修复前行为）：rms={seen}"


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


# ---------------------------------------------------------------------------
# 多桶限流（2026-09-10 P1-13 修复回归）
# ---------------------------------------------------------------------------
def _bucket_count(bucket: str, user_id: int) -> int:
    """当前窗口内该桶计数（测试环境 Redis 关闭 → 内存 TRACE 为唯一计数源）。"""
    import time

    import app.core.ratelimit as rl

    key = (bucket, str(user_id), rl._window(time.time()))
    return int(rl.TRACE.get(key, (0, 0))[0])


@pytest.mark.asyncio
async def test_submit_does_not_charge_sing_when_ise_bucket_is_full(monkeypatch, tmp_path):
    """**P1-13**：ISE 桶超限时不得白扣 sing 桶（两桶一起扣，任一超限全量回滚）。

    修复前必失败：旧写法 `await consume("sing", …)` → `await consume("ise", …)`，ise 抛 429 时
    sing 已扣且不回滚 → 断言实测 `_bucket_count("sing") == 1`。后果：用户重试同一会话上传
    （失败草稿本就允许重跑，见 P1-3）会再扣一次 sing；ISE 额度耗尽期间每次重试都白烧一个 sing。
    """
    import app.core.ratelimit as rl
    from app.core.config import get_settings
    from app.sing.service import submit_song_audio

    monkeypatch.setattr("app.sing.service.probe_duration_seconds", _fake_probe_2s)
    _install_pipeline_stubs(monkeypatch, tmp_path)  # 静音后台 worker + 管线桩
    rl.TRACE.clear()  # 真实限流（不 patch consume_all）→ 内存后端计数可断言

    settings = get_settings()
    monkeypatch.setattr(settings, "ise_rate_per_hour", 0)  # ISE 桶额度耗尽

    db = _new_db()
    song_id = _seed_ready_song(db)
    user_id, session_id = _seed_user_session(db, song_id=song_id)
    db.close()

    with pytest.raises(HTTPException) as exc:
        await submit_song_audio(user_id, session_id, _wav_bytes())
    assert exc.value.status_code == 429
    assert _bucket_count("sing", user_id) == 0, "ISE 超限时 sing 必须回滚（修复前为 1）"
    assert _bucket_count("ise", user_id) == 0

    settings.ise_rate_per_hour = 60  # 额度恢复后重试：sing 只应被计 **一次**（不是两次）
    r = await submit_song_audio(user_id, session_id, _wav_bytes())
    assert r["status"] == "queued"
    assert _bucket_count("sing", user_id) == 1


async def _submit_ok(monkeypatch, *, with_lrc: int = 3):
    """标准提交打桩：时长 2s、不扣桶、ffmpeg/评分桩。返回 (user_id, session_id, r)。"""
    from app.sing.service import submit_song_audio

    async def fake_probe(_path: str) -> float:
        return 2.0

    async def fake_consume(*args, **kwargs):
        return None

    monkeypatch.setattr("app.sing.service.probe_duration_seconds", fake_probe)
    monkeypatch.setattr("app.sing.service.consume_all", fake_consume)
    monkeypatch.setattr("app.core.ratelimit.consume_all", fake_consume)
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
    monkeypatch.setattr("app.sing.service.consume_all", _fake_consume)
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


@pytest.mark.asyncio
async def test_submit_retry_after_failure_resets_draft_in_place(monkeypatch, tmp_path):
    """① 评分失败后"再来一次"必须能重跑（P1-3）：同 id 就地重置 → queued → 再跑可 done。

    修复前必失败：旧幂等分支对 `(user, session)` 的既有行**无条件** `return _status_payload(...)`，
    于是这次失败会永久粘住——重传只会回 `status=failed`（用户看到"失败"且无法重试，
    拷问报告 P1-3 / B-F7 / C-#3）；而改成"新建一行"会撞迁移 0012 的唯一键。
    现在的语义（docs/10 §4.3 草稿行 = 分数 NULL 未定稿，可重写）：
    未定稿行就地重置（id 不变、素材换新、旧结果清空），已定稿行才幂等返回。
    """
    from app.sing.service import _run_attempt, _task_get, get_attempt_status, submit_song_audio

    monkeypatch.setattr("app.sing.service.probe_duration_seconds", _fake_probe_2s)
    monkeypatch.setattr("app.sing.service.consume_all", _fake_consume)
    monkeypatch.setattr("app.core.ratelimit.consume_all", _fake_consume)
    _install_pipeline_stubs(monkeypatch, tmp_path)

    db = _new_db()
    song_id = _seed_ready_song(db)
    user_id, session_id = _seed_user_session(db, song_id=song_id)
    db.close()

    r1 = await submit_song_audio(user_id, session_id, _wav_bytes())

    # 第一轮：worker 崩溃 → failed（不伪造分数）
    async def _boom(*args, **kwargs):
        raise RuntimeError("pipeline crash")

    monkeypatch.setattr("app.sing.service.to_16k_mono_wav", _boom)
    await _run_attempt(r1["attempt_id"])
    assert (await get_attempt_status(r1["attempt_id"], user_id))["status"] == "failed"

    # 第二轮：管线恢复 → 同会话重传必须**重跑**，而不是把 failed 原样回给用户
    _install_pipeline_stubs(monkeypatch, tmp_path)
    r2 = await submit_song_audio(user_id, session_id, _wav_bytes())
    assert r2["attempt_id"] == r1["attempt_id"], "唯一键约束下必须就地复用同一行（不新建第二行）"
    assert r2["status"] == "queued", "修复前此处返回 failed（.first() 无条件复用失败行）"
    assert (await _task_get(r1["attempt_id"]))["status"] == "queued"

    db = _new_db()
    try:
        rows = (
            db.execute(select(SingAttempt).where(SingAttempt.session_id == session_id))
            .scalars()
            .all()
        )
        assert len(rows) == 1, (
            f"同会话只允许一行（uq_sing_attempts_user_session），实得 {len(rows)}"
        )
        assert rows[0].lines == []  # 旧结果已清空（未定稿行可重写）
        assert rows[0].overall_score is None
        assert rows[0].ref_version is None  # 世代快照随重跑重算
    finally:
        db.close()

    # 第三轮：重跑真的能算完并落分（证明重置不是"只改状态"）
    await _run_attempt(r1["attempt_id"])
    status = await get_attempt_status(r1["attempt_id"], user_id)
    assert status["status"] == "done"
    db = _new_db()
    try:
        row = db.get(SingAttempt, r1["attempt_id"])
        assert row.lines, "重跑后应写入逐句结果"
        assert row.is_complete is True
    finally:
        db.close()


@pytest.mark.asyncio
async def test_submit_retry_after_restart_recovers_draft(monkeypatch, tmp_path):
    """② 任务态丢失（服务重启 / Redis 过期）+ 未定稿草稿行：重传应就地重跑而非报"中断"。

    覆盖 C-#3 的"重启后永远 50002"：修复前 `_status_payload` 对无任务态且无分的行返回
    `failed/50002`，而幂等分支又无条件返回它 → 该会话彻底废掉（既不能读结果也不能重录）。
    """
    from app.sing.service import _task_get, get_attempt_status, submit_song_audio
    from app.sing.service import _task_get as _real_task_get

    monkeypatch.setattr("app.sing.service.probe_duration_seconds", _fake_probe_2s)
    monkeypatch.setattr("app.sing.service.consume_all", _fake_consume)
    _install_pipeline_stubs(monkeypatch, tmp_path)

    db = _new_db()
    song_id = _seed_ready_song(db)
    user_id, session_id = _seed_user_session(db, song_id=song_id)
    # 模拟"上一轮已落草稿行、任务态已丢"：直接插一行 NULL 分草稿，不设任务态
    draft = SingAttempt(
        user_id=user_id, session_id=session_id, song_id=song_id, duration_s=5, lines=[]
    )
    db.add(draft)
    db.commit()
    draft_id = int(draft.id)
    db.close()

    async def _no_task(_attempt_id: int) -> None:
        return None  # 模拟 Redis 任务态过期 / 服务重启后内存 dict 清空

    monkeypatch.setattr("app.sing.service._task_get", _no_task)
    assert (await get_attempt_status(draft_id, user_id))["status"] == "failed"  # 无任务态兜底

    r = await submit_song_audio(user_id, session_id, _wav_bytes())
    assert r["attempt_id"] == draft_id, "重启后重传应复用同一草稿行（唯一键下不可新建）"
    assert r["status"] == "queued"

    monkeypatch.setattr("app.sing.service._task_get", _real_task_get)  # 用真实实现查刚落的任务态
    assert (await _task_get(draft_id))["status"] == "queued"


async def _fake_consume(*args, **kwargs):
    return None


@pytest.mark.asyncio
async def test_worker_completes_and_writes_immutable_row(monkeypatch, tmp_path):
    """端到端：submit → worker → done → 行字段契约（lines/alignment/版本快照）。"""
    from app.sing.service import _run_attempt, get_attempt_result, get_attempt_status

    monkeypatch.setattr("app.sing.service.probe_duration_seconds", _fake_probe_2s)
    monkeypatch.setattr("app.sing.service.consume_all", _fake_consume)
    monkeypatch.setattr("app.core.ratelimit.consume_all", _fake_consume)
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
    assert result["scoring_version"] == "v6"  # 口径 v6（v5 + 句窗时间弯折；docs/10 §4.3 留痕）
    assert result["ref_version"] == "pyin-v2"  # pyin-v2：参考含音符级 onset（BUG-1 修复）
    assert result["alignment"]["method"] == "dtw-local-sakoe-chiba-v3"
    assert result["alignment"]["ref_coverage"] == 1.0  # item8：参考完整（种子 3 句全有）
    assert result["alignment"]["pitch_weight"] == 0.5  # item8：全额权重
    assert "transpose_semitones" in result["alignment"]  # item5：移调留痕
    assert "bpm_source" in result["alignment"]  # item7：真实 BPM 来源标注
    # item7 参考侧数据源：种子 ref 带 onsets_ms → Fake 评分器不消费（STRUCTURAL 断言在单测里），
    # 此处只验证契约键存在（真实链路见 local/sing_e2e_test.py 容器实测）
    assert len(result["lines"]) == 3
    assert result["lines"][0]["user_f0"] != []  # D4：逐帧 F0 落库
    assert "user_f0" in result["lines"][0]
    assert "onset_dev_ms" in result["lines"][0]  # v2：起唱偏差落库（报告/排障用）
    assert result["lines"][0]["pron_score"] == 82.0


@pytest.mark.asyncio
async def test_attempt_ownership_and_not_ready(monkeypatch, tmp_path):
    from app.core.response import BizError
    from app.sing.service import _run_attempt, get_attempt_result

    monkeypatch.setattr("app.sing.service.probe_duration_seconds", _fake_probe_2s)
    monkeypatch.setattr("app.sing.service.consume_all", _fake_consume)
    monkeypatch.setattr("app.core.ratelimit.consume_all", _fake_consume)
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
    """失败：任务态 failed + 行分数 NULL（不伪造分数——docs/11 Q-B08 同口径）。

    2026-09-10 P0-5：失败态**码化**（`code=50003`＝已登记「唱歌评分算法失败」，
    docs/api/error-codes.md:31）+ 对外只给可读文案；异常细节（含容器路径）不再回传客户端，
    只进服务端日志。
    """
    from app.sing.service import _run_attempt, get_attempt_status

    monkeypatch.setattr("app.sing.service.probe_duration_seconds", _fake_probe_2s)
    monkeypatch.setattr("app.sing.service.consume_all", _fake_consume)
    monkeypatch.setattr("app.core.ratelimit.consume_all", _fake_consume)

    async def _boom(*args, **kwargs):
        raise RuntimeError("pipeline crash")

    monkeypatch.setattr("app.sing.service.to_16k_mono_wav", _boom)

    user_id, _sid, _song_id, r = await _submit_ok(monkeypatch, with_lrc=3)
    await _run_attempt(r["attempt_id"])

    status = await get_attempt_status(r["attempt_id"], user_id)
    assert status["status"] == "failed"
    assert status["code"] == 50003, (
        "失败态必须回带已登记码（P0-5；修复前无 code 键、error 为异常原文）"
    )
    assert status["error"] == "评分失败，请重试"
    assert "pipeline crash" not in (status.get("error") or ""), "异常细节不得回传客户端（G-#12）"
    db = _new_db()
    try:
        row = db.get(SingAttempt, r["attempt_id"])
        assert row.overall_score is None
        assert row.pitch_score is None
        assert row.lines == []  # 无部分写入
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 任务态丢失后的 DB 兜底判据（2026-09-10 · P1-1）
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_task_lost_overall_none_still_done(monkeypatch):
    """P1-1：任务态丢失后，**合法完成但 overall=None**（覆盖率 <40%，v4/v5 允许）仍判 done。

    修复前判据「`overall_score is not None` 才算 done」→ 这批已算完的 attempt 被判
    `failed` +「评分任务中断」，而 `GET /sing/attempts/{id}` 同时返回 200（自相矛盾）。
    依据：docs/06 §9.4（v4 R3 / v5）、docs/10 §4.3（lines 为逐句唯一真源）、docs/21 §3.6。
    """
    import uuid

    from app.models import Session, SingAttempt, User
    from app.sing import service as svc

    db = _new_db()
    try:
        user = User(
            username=f"p11_{uuid.uuid4().hex[:8]}", email=None, password_hash="x", nickname="U"
        )
        db.add(user)
        db.flush()
        sess = Session(user_id=user.id, kind="sing", song_id=1, assigned_turns=3)
        db.add(sess)
        db.flush()
        row = SingAttempt(
            user_id=user.id,
            session_id=sess.id,
            song_id=1,
            duration_s=30,
            lines=[{"seq": 1, "skipped": False, "pitch_score": 80.0, "rhythm_score": None}],
            alignment={},
            is_complete=False,
            expected_lines=1,
            overall_score=None,  # ← 合法：覆盖率 <40% 不给综合分
        )
        db.add(row)
        db.commit()
        attempt_id, uid = int(row.id), int(user.id)
    finally:
        db.close()

    async def _no_task(_attempt_id: int) -> None:
        return None  # 模拟 Redis 任务态过期/重启

    monkeypatch.setattr(svc, "_task_get", _no_task)
    status = await svc.get_attempt_status(attempt_id, uid)
    assert status["status"] == "done", "合法完成（overall=None）不得被判 failed（修复前行为）"
    assert status["error"] is None
    assert status["progress"]["total"] == 1


@pytest.mark.asyncio
async def test_task_lost_unfinished_still_reports_interrupted(monkeypatch):
    """反向护栏：真正未算完（无 lines、无分）→ 仍报 50002 中断（不得误判 done）。"""
    import uuid

    from app.models import Session, SingAttempt, User
    from app.sing import service as svc

    db = _new_db()
    try:
        user = User(
            username=f"p11b_{uuid.uuid4().hex[:8]}", email=None, password_hash="x", nickname="U"
        )
        db.add(user)
        db.flush()
        sess = Session(user_id=user.id, kind="sing", song_id=1, assigned_turns=3)
        db.add(sess)
        db.flush()
        row = SingAttempt(
            user_id=user.id,
            session_id=sess.id,
            song_id=1,
            duration_s=30,
            lines=[],
            alignment={},
            overall_score=None,
        )
        db.add(row)
        db.commit()
        attempt_id, uid = int(row.id), int(user.id)
    finally:
        db.close()

    async def _no_task(_attempt_id: int) -> None:
        return None

    monkeypatch.setattr(svc, "_task_get", _no_task)
    status = await svc.get_attempt_status(attempt_id, uid)
    assert status["status"] == "failed"
    assert status["code"] == 50002


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
