"""唱歌评分任务编排（2026-09-09 唱歌 P0 D4~D7 · app/sing/service.py）。

职责：
- **提交**：归属/歌曲校验（published + pitch_ref_status=ready → 否则 40905）→ 音频校验
  （40002/41301/41302）→ 扣桶（sing 5/h + ise 30/h——发音抽样合 1 次）→ 落草稿行
  （分数 NULL，不可变行语义：done 时一次性填分）→ 建任务（Redis 态 + 内存兜底 D6）；
- **工作器**：进程内 asyncio 任务，评分信号量 2（与前链路独立，docs/06 §8①⑤）；
  ffmpeg → pyin 用户 F0 → SingScorer（DTW/映射/降权）→ ISE 抽样句（D3，前 N 句）→
  结果一次性写 sing_attempts（scoring_version/ref_version 快照）；
- **轮询**：GET status（任务态→DB 兜底：行存在且有分=done）；GET result（done 后取）。
- **线程模型**：uvicorn ``--workers 1`` 不变；所有 CPU 密集（pyin/DTW/soundfile）走
  ``asyncio.to_thread``；ffmpeg 走 run_ffmpeg（15s 护栏）；进度经任务态透出（禁同步等待）。
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
import time
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

from app.audio.ffmpeg_utils import probe_duration_seconds
from app.audio.pitch import to_16k_mono_wav
from app.audio.sing import (
    SCORING_VERSION,
    LineScore,
    SingScoreResult,
    get_sing_scorer,
    window_scale,
)
from app.audio.upload import validate_audio_bytes
from app.core.config import get_settings
from app.core.ratelimit import consume_all
from app.core.response import BizError
from app.db import get_session_factory
from app.models import Lrc, Session, SingAttempt, Song, SongPitchRef
from app.models.base import ContentStatus, PitchRefStatus, SessionKinds
from app.practice.orchestrator import save_audio_bytes

logger = logging.getLogger("vocalverse")

# 任务态 TTL（docs/06 §8⑤：Redis 任务状态轮询；TTL 30min 对齐音频保留语义）
TASK_TTL_S = 1800
_TASK_PREFIX = "sing:attempt:"

# 评分并发信号量（独立于 whisper/ISE/提取；docs/06 §8③）
_sing_sem: asyncio.Semaphore | None = None

# 内存 dict 兜底（Redis 不可用 → degraded，docs/06 §10.2 降级语义）
_MEM_TASKS: dict[int, tuple[float, dict]] = {}


def _sem() -> asyncio.Semaphore:
    global _sing_sem
    if _sing_sem is None:
        _sing_sem = asyncio.Semaphore(get_settings().sing_concurrency)
    return _sing_sem


# ---------------------------------------------------------------------------
# 任务态存储（Redis + 内存兜底；D6 拍板）
# ---------------------------------------------------------------------------
async def _task_set(attempt_id: int, payload: dict) -> None:
    _MEM_TASKS[attempt_id] = (time.time() + TASK_TTL_S, dict(payload))
    try:
        from app.core.redis_client import get_redis

        client = get_redis()
        if client is None:
            return
        import json

        await client.set(f"{_TASK_PREFIX}{attempt_id}", json.dumps(payload), ex=TASK_TTL_S)
    except Exception:  # Redis 写失败 → 内存已经兜底（degraded）
        logger.warning("sing task store redis set failed attempt=%s (memory fallback)", attempt_id)


async def _task_get(attempt_id: int) -> dict | None:
    try:
        from app.core.redis_client import get_redis

        client = get_redis()
        if client is not None:
            import json

            raw = await client.get(f"{_TASK_PREFIX}{attempt_id}")
            if raw is not None:
                return json.loads(raw)
    except Exception:
        logger.warning("sing task store redis get failed attempt=%s (memory fallback)", attempt_id)
    entry = _MEM_TASKS.get(attempt_id)
    if entry is None:
        return None
    expires, payload = entry
    if expires < time.time():
        _MEM_TASKS.pop(attempt_id, None)
        return None
    return payload


# ---------------------------------------------------------------------------
# 提交（POST /sessions/{id}/audio）
# ---------------------------------------------------------------------------
async def submit_song_audio(user_id: int, session_id: int, audio: bytes) -> dict:
    """校验 + 扣桶 + 落草稿行 + 启动异步评分；返回 {attempt_id, status}。"""
    settings = get_settings()
    db = get_session_factory()()
    try:
        session = db.execute(
            select(Session).where(Session.id == session_id, Session.user_id == user_id)
        ).scalar_one_or_none()
        if session is None or session.kind != SessionKinds.SING:
            raise BizError(http_status=404, code=40401, message="session not found or expired")
        song = db.get(Song, int(session.song_id)) if session.song_id else None
        if song is None or song.status != ContentStatus.PUBLISHED:
            raise BizError(http_status=404, code=40401, message="song not found")
        if song.pitch_ref_status != PitchRefStatus.READY:
            # 参考旋律未就绪/缺失（40905；先登记后使用 docs/api/error-codes.md）
            raise BizError(
                http_status=409,
                code=40905,
                message=f"reference pitch not ready (status={song.pitch_ref_status})",
            )
        # 幂等 / 重试（2026-09-10 · P1-3 修复）：
        # 同一 `(user, session)` **只允许一行**
        # （唯一键 `uq_sing_attempts_user_session`，迁移 0012），
        # 故"再来一次"必须区分三种情形：
        #   ① 已完成（有逐句结果或有分）→ 幂等返回既有结果（不重复扣桶/建任务）；
        #   ② 任务仍在跑（queued/processing）→ 幂等返回状态（防双击重复扣桶）；
        #   ③ 失败/中断的草稿（lines 空、无分、任务态已丢）→ **就地重置**该行并重跑——
        #      修复前 `.first()` 无条件复用（含 failed 行）→ 同会话永远只返回那次失败，
        #      用户无法重试（拷问报告 P1-3 / B-F7 / C-#3）；而"新建一行"又会撞唯一键。
        # 依据：docs/10 §4.3（sing_attempts 唯一键 + 草稿行语义：分数 NULL = 未定稿）、
        # docs/21 §3.6（幂等语义）、docs/11 Q-B08（不伪造分数）。
        existing = (
            db.execute(
                select(SingAttempt)
                .where(SingAttempt.user_id == user_id, SingAttempt.session_id == session_id)
                .order_by(SingAttempt.id.desc())
            )
            .scalars()
            .first()
        )
        reuse_attempt_id: int | None = None
        if existing is not None:
            if _attempt_finished(existing):
                return await _status_payload(int(existing.id))
            task = await _task_get(int(existing.id))
            if task is not None and task.get("status") in ("queued", "processing"):
                return await _status_payload(int(existing.id))
            reuse_attempt_id = int(existing.id)  # ③ 失败草稿：就地重置后继续走上传
    finally:
        db.close()

    # 校验前置于扣额（审计 R-06 同口径）
    data = validate_audio_bytes(
        audio,
        min_bytes=settings.min_upload_bytes,
        max_bytes=settings.max_upload_bytes,
    )
    # 时长校验（41302：> max_sing_seconds；先落临时文件探测）
    dur = await _probe_duration(data)
    if dur is not None and dur > settings.max_sing_seconds:
        raise BizError(
            http_status=413,
            code=41302,
            message=f"audio too long ({dur:.0f}s > {settings.max_sing_seconds}s)",
        )

    # 分桶限流（D3：sing 整首计 1 + ise 抽样句计 1；等待中不重复扣——幂等分支在上）
    # P1-13：两桶**一起扣**（`consume_all`：任一超限 → 全量回滚 + 429）。旧写法逐桶顺序扣，
    # ISE 桶超限时 sing 桶已扣且不回滚 → 用户重试再扣一次（同一会话的重传被计两次），
    # 且 ISE 额度耗尽期间每次重试都白扣一个 sing（用户始终拿不到结果却在烧额度）。
    await consume_all(
        [("sing", settings.sing_rate_per_hour), ("ise", settings.ise_rate_per_hour)], user_id
    )

    audio_url = save_audio_bytes(data)

    db = get_session_factory()()
    try:
        if reuse_attempt_id is not None:
            # ③ 失败草稿**就地重置**（P1-3）：重写素材/时长并清空结果，行 id 不变
            # （唯一键保证同会话只有一行；不可变语义仍成立——只有"未定稿"的草稿会被重写）
            attempt = db.get(SingAttempt, reuse_attempt_id)
            if attempt is not None:
                attempt.audio_url = audio_url
                attempt.duration_s = max(1, int(dur or 0))
                attempt.is_complete = False
                attempt.lines = []
                attempt.alignment = {}
                attempt.scoring_version = SCORING_VERSION
                attempt.ref_version = None
                db.commit()
                attempt_id = reuse_attempt_id
                logger.info("sing attempt=%s draft reset for retry (user=%s)", attempt_id, user_id)
            else:  # 行被并发删掉（理论竞态）→ 回落新建
                reuse_attempt_id = None
        if reuse_attempt_id is None:
            attempt = SingAttempt(
                user_id=user_id,
                session_id=session_id,
                song_id=int(session.song_id),
                duration_s=max(1, int(dur or 0)),
                audio_url=audio_url,
                is_complete=False,
                lines=[],
                alignment={},
            )
            db.add(attempt)
            db.commit()
            attempt_id = int(attempt.id)
    finally:
        db.close()

    await _task_set(attempt_id, {"status": "queued", "progress": {"done_lines": 0, "total": 0}})
    asyncio.create_task(_run_attempt(attempt_id))
    logger.info("sing attempt submitted: %s (user=%s)", attempt_id, user_id)
    return {"attempt_id": attempt_id, "status": "queued"}


async def _probe_duration(audio: bytes) -> float | None:
    """字节音频时长探测（写入临时文件 → ffprobe；失败 None——时长校验降级为通过）。"""
    with tempfile.NamedTemporaryFile(suffix=".in", delete=False) as tmp:
        tmp.write(audio)
        path = tmp.name
    try:
        return await probe_duration_seconds(path)
    finally:
        Path(path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# 工作器
# ---------------------------------------------------------------------------
async def _run_attempt(attempt_id: int) -> None:
    """异步评分流水线（信号量 2；失败 → 任务态 failed，草稿行分数保持 NULL——不伪造）。"""
    async with _sem():
        try:
            await _run_attempt_inner(attempt_id)
        except Exception as exc:
            # 2026-09-10 P0-5：失败对外**码化**——已登记 50003（参考旋律提取/唱歌评分算法失败）
            # + 可读中文文案；异常细节只进服务端日志（G-#12：不再回传容器绝对路径/内部异常串）。
            # `code` 让前端可按码映射（`api/sing.ts:singFailureMessage`），不再靠 message 匹配。
            # 依据：docs/api/error-codes.md:31（50003）、docs/21 §3.6、docs/api/envelope.md。
            logger.exception("sing attempt=%s failed: %s", attempt_id, exc)
            await _task_set(
                attempt_id,
                {
                    "status": "failed",
                    "progress": {"done_lines": 0, "total": 0},
                    "code": 50003,
                    "error": "评分失败，请重试",
                },
            )


async def _run_attempt_inner(attempt_id: int) -> None:
    settings = get_settings()
    # 1) 素材：attempt.audio_url（唯一真源）→ 共享卷文件 → 16k mono wav
    db = get_session_factory()()
    try:
        attempt = db.get(SingAttempt, attempt_id)
        if attempt is None or not attempt.audio_url:
            raise RuntimeError(f"attempt {attempt_id} missing audio")
        audio_url = attempt.audio_url
    finally:
        db.close()
    data_dir = Path(settings.audio_dir)
    src = (data_dir / Path(audio_url).name).as_posix()
    if not Path(src).exists():
        raise FileNotFoundError(f"audio file missing: {src}")
    with tempfile.TemporaryDirectory(prefix="sing-") as tmp:
        wav = str(Path(tmp) / "user.wav")
        await to_16k_mono_wav(src, wav)
        # 2) 评分核心（pyin/DTW/映射——to_thread 承载 CPU 重活）
        result, ref_meta = await asyncio.to_thread(_score_core_sync, wav, int(attempt_id))
        # 3) 发音抽样句（D3）：前 N 句（N=APP_SING_PRON_SAMPLES；weak 句优先为 P2 增强）
        sampled = await _pron_sample_lines(wav, result, settings.sing_pron_samples)
        # 发音为后补维度：抽样后重算 pron/overall（评分器聚合时 pron 尚未知）
        _reaggregate_pron(result)
        await _finish_attempt(int(attempt_id), result, sampled, ref_meta)


def _score_core_sync(wav: str, attempt_id: int) -> tuple[SingScoreResult, dict]:
    """同步评分核心：读参考 + 评分（pyin/DTW/映射 pure CPU）。"""
    db = get_session_factory()()
    try:
        attempt = db.get(SingAttempt, attempt_id)
        if attempt is None:
            raise RuntimeError(f"attempt {attempt_id} not found")
        song_id = int(attempt.song_id)
        lines = list(
            db.execute(select(Lrc).where(Lrc.song_id == song_id).order_by(Lrc.seq)).scalars()
        )
        if not lines:
            raise RuntimeError("lrc lines empty")
        refs = (
            db.execute(
                select(SongPitchRef).where(
                    SongPitchRef.lrc_id.in_([int(line.id) for line in lines])
                )
            )
            .scalars()
            .all()
        )
        ref_by_lrc = {int(r.lrc_id): r for r in refs}
        ref_lines = []
        for line in lines:
            ref = ref_by_lrc.get(int(line.id))
            ref_lines.append(
                {
                    "lrc_id": int(line.id),
                    "seq": int(line.seq),
                    "start_ms": int(line.offset_ms),
                    "end_ms": int(ref.end_ms if ref else 0) or int(line.end_offset_ms or 0),
                    "pitch_ref": ref.pitch_ref if ref else {"f0s": []},
                    "text": line.line_text,
                }
            )
        ref_version = next((r.version for r in refs if r.version), None)
        return get_sing_scorer().score_sync(wav, ref_lines), {
            "ref_version": ref_version,
            "song_id": song_id,
        }
    finally:
        db.close()


async def _pron_sample_lines(wav: str, result: SingScoreResult, n: int) -> dict[int, float]:
    """抽样句发音（D3）：前 n 句各切窗口 → 口语评分引擎（ISE/Fake）；返回 {seq: pron_score}。

    n<=0 → 发音维度关闭（{ }，整体发音分 None）；抽样失败单句降级（pron None，不伪造）。
    """
    if n <= 0:
        return {}
    scorer = None
    sampled: dict[int, float] = {}
    offset = float(result.alignment.get("offset_ms") or 0.0)
    # 句窗缩放与评分侧同源（BUG-4：用户慢 → 句更长，见 sing.py:window_scale 的 clamp 说明）
    scale = window_scale(result.alignment.get("bpm_ratio"))
    # v6（2026-09-10 F1）：评分侧把每句的**用户时间轴窗口**写进 alignment.windows_ms（时间弯折），
    # 抽样直接复用同一份映射，杜绝"评分用弯折窗、发音用仿射窗"的口径分叉；旧行（v5 及以前）无该键
    # → 回退到 v5 公式（+offset 与 window_scale）。
    windows = {
        int(w[0]): (float(w[1]), float(w[2]))
        for w in (result.alignment.get("windows_ms") or [])
        if isinstance(w, (list, tuple)) and len(w) >= 3
    }
    scored = [line for line in result.lines[:n] if not line.skipped]
    try:
        from app.audio.base import get_scorer_client

        scorer = get_scorer_client()
    except Exception:
        scorer = None
    for line in scored:
        # 句窗口映射到**用户时间轴**：与评分侧完全同口径。
        # - v6（2026-09-10 F1）：优先用评分侧下发的 `alignment.windows_ms`
        #   （时间弯折：路径局部中位），
        #   起点与长度同源，避免"评分用弯折窗、发音用仿射窗"的分叉；
        # - v5 及更早的行没有该键 → 回退 `line.start_ms + offset`（+ window_scale 缩句长）。
        # 2026-09-10 修复（P0）：旧实现写的是 `line.start_ms - offset`（**方向反**）——
        # offset>0（用户整体晚起唱，真机实测 2272ms）时切片落在静音/别的句子上，占综合
        # 0.3 权重的发音分与真实演唱无关，且不可复现（Fake 打分器 offset=0 使单测看不见）。
        # 依据：docs/06 §9.4（时间轴不变式 + 句窗弯折）、docs/21 §3.6、docs/10 §4.3。
        mapped = windows.get(int(line.seq))
        if mapped is not None:
            win_start, win_end = mapped
        else:
            win_start = float(line.start_ms) + offset
            win_end = win_start + max(1.0, (float(line.end_ms) - float(line.start_ms)) * scale)
        seg = await _slice_wav(wav, win_start, win_end)
        if seg is None:
            continue
        try:
            if scorer is None:
                raise RuntimeError("scorer unavailable")
            score = await scorer.score(seg, _reference_text(line))
            # 同步回填到对应句 pron_score（不可变行语义在落库时才固化）
            for cand in result.lines:
                if cand.seq == line.seq:
                    cand.pron_score = round(float(score.pronunciation), 2)
                    break
            sampled[line.seq] = round(float(score.pronunciation), 2)
        except Exception as exc:
            logger.warning("sing pron sample line=%s skipped: %s", line.seq, exc)
    return sampled


def _reference_text(line: LineScore) -> str:
    """ISE 参考文本占位：句子文本缺省 'you'（仅打分结构用，fake 引擎不校验内容）。"""
    return "you"


async def _slice_wav(wav: str, start_ms: float, end_ms: float) -> bytes | None:
    """16k mono wav 句窗口切片 → PCM wav bytes（ISE 需要 audio/L16;16k）。"""
    import io

    import soundfile as sf

    try:
        data, _sr = await asyncio.to_thread(
            _read_range,
            wav,
            start_ms * 16,
            end_ms * 16,  # 16k → 样本序号
        )
    except Exception:
        return None
    if data is None or len(data) == 0:
        return None
    buf = io.BytesIO()
    sf.write(buf, data.astype("float32"), 16000, format="WAV")
    return buf.getvalue()


def _read_range(wav: str, start_sample: float, end_sample: float):
    import soundfile as sf

    # 注意：sf.read 无 format 参数（format 仅 sf.write 用）；格式按文件头自动识别
    data, _sr = sf.read(wav, dtype="float32", always_2d=False)
    i0, i1 = int(max(0, start_sample)), int(min(len(data), max(start_sample, end_sample)))
    if i1 - i0 < 800:  # <50ms 切片丢弃（无有效内容）
        return None, 16000
    return data[i0:i1], 16000


def _reaggregate_pron(result: SingScoreResult) -> None:
    """发音抽样后重算 pron + overall（评分器聚合时 pron 未知；缺失降权语义不变）。

    音准权重用 ``result.pitch_weight``（口径 v3 · item8 动态权重：参考缺失多时
    aggregate 已按三段政策降/清零）；综合分再乘 ``result.coverage_conf``
    （口径 v4 · R3：用户有效句覆盖率置信度，<40% → 0 → overall None 不给分）——
    与 ``aggregate_result`` 同口径复算，否则两处口径不一致。
    """
    from app.audio.sing import _mean, _weighted_overall

    prons = [line.pron_score for line in result.lines if line.pron_score is not None]
    result.pron = _mean(prons)
    wp = result.pitch_weight if result.pitch_weight is not None else 0.5
    weighted = _weighted_overall(result.pitch, result.rhythm, result.pron, wp, 0.2, 0.3)
    conf = result.coverage_conf if result.coverage_conf is not None else 1.0
    result.overall = None if (weighted is None or conf <= 0) else round(weighted * conf, 2)


async def _finish_attempt(
    attempt_id: int, result: SingScoreResult, pron: dict, ref_meta: dict
) -> None:
    """一次性写 sing_attempts（不可变行：done 时落全部字段，无中间态）。"""
    total = result.expected_lines or max(1, len(result.lines))
    await _task_set(
        attempt_id,
        {"status": "processing", "progress": {"done_lines": total, "total": total}},
    )
    db = get_session_factory()()
    try:
        attempt = db.get(SingAttempt, attempt_id)
        if attempt is None:
            raise RuntimeError(f"attempt {attempt_id} not found")
        attempt.overall_score = _dec(result.overall)
        attempt.pitch_score = _dec(result.pitch)
        attempt.rhythm_score = _dec(result.rhythm)
        attempt.pron_score = _dec(result.pron)
        attempt.is_complete = result.is_complete
        attempt.expected_lines = result.expected_lines
        attempt.lines = [_line_dict(line) for line in result.lines]
        attempt.alignment = result.alignment
        attempt.scoring_version = SCORING_VERSION  # v2（口径升级留痕；docs/10 §4.3）
        attempt.ref_version = ref_meta.get("ref_version")
        db.commit()
    finally:
        db.close()
    await _task_set(
        attempt_id,
        {
            "status": "done",
            "progress": {"done_lines": total, "total": total},
            "error": None,
        },
    )


def _line_dict(line: LineScore) -> dict:
    """lines[i] 落库契约（docs/10 §4.3：分项 + user_f0 + missing 降权标注 + 起唱偏差）。"""
    return {
        "seq": line.seq,
        "start_ms": line.start_ms,
        "end_ms": line.end_ms,
        "pitch_score": line.pitch_score,
        "rhythm_score": line.rhythm_score,
        "pron_score": line.pron_score,
        "synced": line.synced,
        "skipped": line.skipped,
        "reason": line.reason,
        "ref_seq": line.ref_seq,
        "no_ref": line.no_ref,
        # v2：该句起唱偏差 ms（相对「LRC 时间戳 + 整首对齐偏移」；None = 未检出
        # 或句前已在持续发声——口径 v4 · R1 起唱判据）
        "onset_dev_ms": line.onset_dev_ms,
        # v4 · R2：音符命中率（是否唱在参考旋律上；<0.5 → 该句 off_melody 降权）
        "note_hit_rate": line.note_hit_rate,
        "user_f0": line.user_f0,
        "cent_dev": line.cent_dev,
    }


def _dec(v: float | None) -> Decimal | None:
    return Decimal(str(round(v, 2))) if v is not None else None


# ---------------------------------------------------------------------------
# 轮询与结果
# ---------------------------------------------------------------------------
async def get_attempt_status(attempt_id: int, user_id: int) -> dict:
    """状态轮询（归属校验 → 任务态 → DB 兜底：行有分=done（服务重启恢复））。"""
    db = get_session_factory()()
    try:
        attempt = db.execute(
            select(SingAttempt).where(SingAttempt.id == attempt_id, SingAttempt.user_id == user_id)
        ).scalar_one_or_none()
        if attempt is None:
            raise BizError(http_status=404, code=40401, message="attempt not found")
    finally:
        db.close()
    return await _status_payload(attempt_id)


def _attempt_finished(attempt: SingAttempt) -> bool:
    """评分是否**已终结**（任务态丢失后的 DB 兜底判据，与结果端点同口径）。

    2026-09-10 P1 修复：v4/v5 口径**允许 `overall_score` 为 NULL**（覆盖率 <40% 不给综合分，
    `sing.py:overall = None if conf <= 0`），而旧判据「`overall_score is not None` 才算 done」
    会把这批**已经算完**的 attempt 判成 `failed` +「评分任务中断」——用户看到"失败"、报告入口
    消失，重录还要再扣一次额度（拷问报告 P1-1，B/C/G 三路交叉；`docs/21:175` 曾把错判据写成契约）。
    现判据 = 「有逐句结果（`lines` 非空，逐句唯一真源）**或**有综合分」，与 `get_attempt_result`
    的可读判据一致；真正未算完的（两者皆无）仍返回 50002 中断。
    依据：docs/06 §9.4（v4 R3 / v5）、docs/10 §4.3（lines 为逐句唯一真源）、docs/21 §3.6。
    """
    return bool(attempt.lines) or attempt.overall_score is not None


async def _status_payload(attempt_id: int) -> dict:
    task = await _task_get(attempt_id)
    if task is not None:
        return {"attempt_id": attempt_id, **task}
    # 任务态丢失（重启/Redis 过期）→ DB 兜底判定
    db = get_session_factory()()
    try:
        attempt = db.get(SingAttempt, attempt_id)
        if attempt is not None and _attempt_finished(attempt):
            return {
                "attempt_id": attempt_id,
                "status": "done",
                "progress": {
                    "done_lines": attempt.expected_lines or 0,
                    "total": attempt.expected_lines or 0,
                },
                "error": None,
            }
    finally:
        db.close()
    return {
        "attempt_id": attempt_id,
        "status": "failed",
        "progress": {"done_lines": 0, "total": 0},
        # 2026-09-10 P0-5：码化 + 中文（原文 task lost 英文串直接透给用户）。
        # 判据见 :func:`_attempt_finished`（P1 起与结果端点同口径）。
        "code": 50002,
        "error": "评分任务中断（服务重启或结果超时），请重试",
    }


async def get_attempt_result(attempt_id: int, user_id: int) -> dict:
    """评分结果（done 后取；未完成 40902，不存在 40401——归属即校验存在）。"""
    db = get_session_factory()()
    try:
        attempt = db.execute(
            select(SingAttempt).where(SingAttempt.id == attempt_id, SingAttempt.user_id == user_id)
        ).scalar_one_or_none()
        if attempt is None:
            raise BizError(http_status=404, code=40401, message="attempt not found")
        if attempt.overall_score is None and not attempt.lines:
            raise BizError(http_status=409, code=40902, message="attempt not ready")
        return _result_dict(attempt)
    finally:
        db.close()


def _result_dict(a: SingAttempt) -> dict:
    def f(v):
        return float(v) if v is not None else None

    return {
        "id": int(a.id),
        "song_id": int(a.song_id),
        "audio_url": a.audio_url,
        "duration_s": a.duration_s,
        "overall": f(a.overall_score),
        "pitch": f(a.pitch_score),
        "rhythm": f(a.rhythm_score),
        "pron": f(a.pron_score),
        "is_complete": a.is_complete,
        "expected_lines": a.expected_lines,
        "scoring_version": a.scoring_version,
        "ref_version": a.ref_version,
        "lines": a.lines or [],
        "alignment": a.alignment or {},
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }
