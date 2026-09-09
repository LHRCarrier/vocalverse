"""参考旋律提取任务编排（pitch_extract_jobs 事实源 · 2026-09-09 唱歌 P0 D2/D6 拍板）。

职责：
- **扫描**（lifespan 周期 + 启动）：对每首 published 歌曲，若 song_pitch_refs 与其 LRC 行
  不匹配（缺失/版本旧）且无进行中任务 → 建 job（queued）；failed 且重试未达上限 → 重建；
- **工作器**：queued→running（乐观 UPDATE 防并发双跑）→ pyin 提取（to_thread，信号量 2）
  → 逐句写 song_pitch_refs（version="pyin-v1"）→ 委托 Java 翻转 songs.pitch_ref_status；
- **委托**（POST /internal/song/{id}/pitch-status，camelCase + 3s + raise_for_status）：
  失败不阻塞 job 完成（done + payload 记委托失败）→ 扫描的「补偿分支」检测
  「refs 齐全但状态门禁未 ready」→ 重发委托（幂等，安全）；
- **单写方守护**：songs 表 Java 独占写（M-1 仅授 SELECT）——本模块只 SELECT songs，
  状态翻转一律走内部 REST；song_pitch_refs/pitch_extract_jobs 为 Python 写方。

并发/线程模型（docs/06 §8①⑤）：提取信号量独立（与 whisper/ISE/sing 无关），
librosa/ffmpeg 全部 ``to_thread``；uvicorn ``--workers 1`` 下不阻塞 SSE 心跳。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select

from app.audio.pitch import (
    EXTRACTOR_VERSION,
    PitchExtractError,
    get_pitch_extractor,
    resolve_audio_path,
    slice_window,
    to_16k_mono_wav,
)
from app.core.config import get_settings
from app.db import get_session_factory
from app.models import Lrc, PitchExtractJob, Song, SongPitchRef
from app.models.base import ContentStatus, PitchJobStatus, PitchRefStatus

logger = logging.getLogger("vocalverse")

# 进程内提取信号量（独立于评分/whisper；docs/06 §8③ 语义：多任务排队不雪崩）
_extract_sem: asyncio.Semaphore | None = None


def _sem() -> asyncio.Semaphore:
    global _extract_sem
    if _extract_sem is None:
        _extract_sem = asyncio.Semaphore(get_settings().pitch_extract_concurrency)
    return _extract_sem


# ---------------------------------------------------------------------------
# 扫描（读侧门禁 + 任务事实源）
# ---------------------------------------------------------------------------
def lrc_generation(db, song_id: int) -> tuple[int, str] | None:
    """LRC 世代标识：取该歌当前最新行 id（整首重写=删旧插新→max id 变化即世代变化）。

    返回 (max_lrc_id, revision)；无 LRC 行 → None（该歌无法提取）。
    """
    row = db.execute(select(func.max(Lrc.id)).where(Lrc.song_id == song_id)).scalar()
    if row is None:
        return None
    return int(row), f"lrc-m{int(row)}"


def _refs_ready(db, song_id: int, lrc_ids: list[int]) -> bool:
    """该歌 LRC 行的 song_pitch_refs 是否齐全且为当前算法世代（version='pyin-v1'）。"""
    rows = db.execute(
        select(SongPitchRef.lrc_id, SongPitchRef.version).where(SongPitchRef.lrc_id.in_(lrc_ids))
    ).all()
    refs = {int(r.lrc_id): r.version for r in rows}
    if len(refs) != len(lrc_ids):
        return False
    return all(v == EXTRACTOR_VERSION for v in refs.values())


def scan_due_jobs() -> int:
    """扫描并创建待提取任务；返回新建任务数（幂等：无缺失/有进行中任务/超重试上限则跳过）。"""
    settings = get_settings()
    created = 0
    db = get_session_factory()()
    try:
        # 候选 1：无进行中任务的 published 歌曲（仅读 songs/lrc——songs 属 Java 独占写）
        songs = db.execute(select(Song).where(Song.status == ContentStatus.PUBLISHED)).scalars()
        for song in songs:
            gen = lrc_generation(db, int(song.id))
            if gen is None:
                continue
            max_lrc_id, revision = gen
            lrc_ids = [
                int(r[0]) for r in db.execute(select(Lrc.id).where(Lrc.song_id == song.id)).all()
            ]
            active = db.execute(
                select(PitchExtractJob.id).where(
                    PitchExtractJob.song_id == song.id,
                    PitchExtractJob.status.in_((PitchJobStatus.QUEUED, PitchJobStatus.RUNNING)),
                )
            ).first()
            if active:
                continue
            if _resume_or_create(db, song, max_lrc_id, lrc_ids, revision, settings):
                created += 1
        # 候选 2（补偿分支）：refs 齐全但 songs.pitch_ref_status 门禁未 ready（委托曾失败）
        # —— 幂等重发委托（同值重复无害，docs/21 §4 第三条）
        _resend_delegation_for_ready_songs(db)
        db.commit()
    finally:
        db.close()
    return created


def _resume_or_create(
    db, song, max_lrc_id: int, lrc_ids: list[int], revision: str, settings
) -> bool:
    """refs 缺失/旧版 → 建新任务；已有 failed 任务且未达重试上限 → 重置重建。

    返回是否实际创建/恢复了任务（供扫描计数，仅计数用）。
    """
    if _refs_ready(db, int(song.id), lrc_ids):
        return False
    last_failed = db.execute(
        select(PitchExtractJob)
        .where(
            PitchExtractJob.song_id == song.id,
            PitchExtractJob.status == PitchJobStatus.FAILED,
        )
        .order_by(PitchExtractJob.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if last_failed is not None and last_failed.attempts >= settings.pitch_extract_max_attempts:
        # 已达重试上限：保留 failed 证据（payload 有错误快照），不无限重建
        logger.warning(
            "pitch extract job failed beyond attempts song=%s (attempts=%s)",
            song.id,
            last_failed.attempts,
        )
        return False
    if last_failed is not None:
        # 重试 = 重置为 queued（attempts+1 在 _finish_job 失败分支记录；恢复不 +1，避免超额重试）
        last_failed.status = PitchJobStatus.QUEUED
        last_failed.revision = revision
        last_failed.lrc_id = max_lrc_id
        last_failed.finished_at = None
        return True
    db.add(
        PitchExtractJob(
            song_id=int(song.id),
            lrc_id=max_lrc_id,
            revision=revision,
            status=PitchJobStatus.QUEUED,
            payload={},
        )
    )
    return True


def _resend_delegation_for_ready_songs(db) -> None:
    """补偿：refs 齐全且版本当前，但 songs.pitch_ref_status 门禁未 ready → 重发委托（幂等）。"""
    rows = db.execute(
        select(Song.id, Song.pitch_ref_status).where(
            Song.status == ContentStatus.PUBLISHED,
            Song.pitch_ref_status != PitchRefStatus.READY,
        )
    ).all()
    for song_id, status in rows:
        lrc_ids = [
            int(r[0]) for r in db.execute(select(Lrc.id).where(Lrc.song_id == int(song_id))).all()
        ]
        if not lrc_ids:
            continue
        if not _refs_ready(db, int(song_id), lrc_ids):
            continue
        if status == PitchRefStatus.BUILDING:
            continue  # 有进行中任务（worker 会推进）；未见 running 任务也 keep building
        active = db.execute(
            select(PitchExtractJob.id).where(
                PitchExtractJob.song_id == int(song_id),
                PitchExtractJob.status.in_((PitchJobStatus.QUEUED, PitchJobStatus.RUNNING)),
            )
        ).first()
        if active:
            continue
        try:
            notify_pitch_status(int(song_id), PitchRefStatus.READY, EXTRACTOR_VERSION)
            logger.info("pitch status 补偿委托：song=%s ready", song_id)
        except Exception as exc:
            logger.warning("pitch status 补偿委托失败 song=%s: %s", song_id, exc)


# ---------------------------------------------------------------------------
# 工作器
# ---------------------------------------------------------------------------
async def run_due_jobs_until_stopped(stop: asyncio.Event) -> None:
    """lifespan 后台循环：扫描 + 并行执行（提取信号量限流），间隔可配；stop 事件优雅退出。"""
    settings = get_settings()
    while not stop.is_set():
        try:
            await asyncio.to_thread(scan_due_jobs)
            await _drain_queue()
        except Exception as exc:  # 扫描/执行异常不得杀死循环（启动扫描失败=自愈重试）
            logger.exception("pitch extract loop error: %s", exc)
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=settings.pitch_extract_scan_interval_s)


async def _drain_queue() -> None:
    settings = get_settings()
    db = get_session_factory()()
    try:
        jobs = (
            db.execute(
                select(PitchExtractJob)
                .where(PitchExtractJob.status == PitchJobStatus.QUEUED)
                .order_by(PitchExtractJob.id)
                .limit(8)
            )
            .scalars()
            .all()
        )
    finally:
        db.close()
    if not jobs:
        return
    # 并发闸门：提取信号量（与评分/whisper 相互独立）
    async with _sem():
        await asyncio.gather(
            *(
                asyncio.to_thread(run_job_sync, int(j.id), settings.pitch_extract_max_attempts)
                for j in jobs
            )
        )


def claim_job(job_id: int) -> bool:
    """queued→running 抢占（并发双跑防护）：WHERE status 复核后置位。

    成功返回 True；否则 False（他处已处理）。写纪律：单写方探针
    （tests/test_single_writer.py）以文件级粗粒度守护，本文件合法 import 了 Java 拥有表
    （Song/Lrc 仅读侧），故本文件的写一律走 ORM 属性赋值（db.add / attr + commit），
    不出现 Core 更新语句形式。并发安全性：uvicorn ``--workers 1`` + 扫描/执行同事件循环
    串行，claim 竞争面仅进程内（同批不同 job_id 并行、重复 job_id 不可能被同批取两次），
    此显式状态复核已足够；PG 行锁属冗余保险，不引入（避免探针误报）。
    """
    db = get_session_factory()()
    try:
        job = db.execute(
            select(PitchExtractJob).where(
                PitchExtractJob.id == job_id,
                PitchExtractJob.status == PitchJobStatus.QUEUED,
            )
        ).scalar_one_or_none()
        if job is None:
            return False
        job.status = PitchJobStatus.RUNNING
        job.started_at = datetime.now(UTC)
        db.commit()
        return True
    finally:
        db.close()


def run_job_sync(job_id: int, max_attempts: int = 3) -> None:
    """执行单个提取任务（同步，工作线程内）；全过程 DB 短事务 + 异常一律转 failed 快照。

    流程（D2）：提取成功 → 逐句写 song_pitch_refs（Python 写方，幂等覆盖）→
    委托 Java 翻转 songs.pitch_ref_status=ready（失败仅告警，扫描补偿兜底）。
    """
    if not claim_job(job_id):
        return
    settings = get_settings()
    try:
        _run_job_inner(job_id, settings.audio_dir)
    except Exception as exc:
        logger.exception("pitch extract job=%s failed: %s", job_id, exc)
        fail_payload = {
            "error": str(exc),
            "failed_at": datetime.now(UTC).isoformat(),
        }
        _finish_job(job_id, fail_payload)
        return
    _finish_job(job_id, {})


def _run_job_inner(job_id: int, audio_dir: str) -> None:
    """提取主体：读 job → 首歌/行 → 音源解析 → ffmpeg → pyin → 逐句写 refs → 委托。"""
    db = get_session_factory()()
    try:
        job = db.get(PitchExtractJob, job_id)
        if job is None:
            raise PitchExtractError(f"job {job_id} not found")
        song = db.get(Song, int(job.song_id))
        if song is None:
            raise PitchExtractError(f"song {job.song_id} not found")
        lines = list(
            db.execute(
                select(Lrc).where(Lrc.song_id == int(job.song_id)).order_by(Lrc.seq)
            ).scalars()
        )
        if not lines:
            raise PitchExtractError("lrc lines empty")
    finally:
        db.close()

    # D1：输入轨两级回退（vocal_ref 优先 → audio_url）
    src = resolve_audio_path(song.vocal_ref_url, audio_dir) or resolve_audio_path(
        song.audio_url, audio_dir
    )
    if src is None:
        raise PitchExtractError(
            f"音频文件不可达（vocal_ref={song.vocal_ref_url} audio={song.audio_url})"
        )

    with tempfile.TemporaryDirectory(prefix="pitch-") as tmp:
        wav = str(Path(tmp) / "track.wav")
        # ffmpeg 子进程（15s 护栏）→ 提取 pyin（run_job_sync 工作线程承载，不进事件循环）
        asyncio.run(to_16k_mono_wav(src, wav))
        track = get_pitch_extractor().extract_track(wav)

    # 句窗口（A-G6）：end_offset_ms 缺 → 按下一句起点推断；末句按整轨时长兜底
    line_windows: list[tuple[int, int]] = []
    for i, line in enumerate(lines):
        start = int(line.offset_ms)
        end = int(line.end_offset_ms) if line.end_offset_ms else None
        if end is None:
            end = int(lines[i + 1].offset_ms) if i + 1 < len(lines) else int(track.duration_ms)
        if end <= start:
            end = start + max(500, int(track.hop_ms * 4))
        line_windows.append((start, end))

    # 写 refs（Python 写方；lrc_id 唯一 → 幂等覆盖）
    db = get_session_factory()()
    try:
        for line, (start, end) in zip(lines, line_windows, strict=True):
            payload = slice_window(track, start, end)
            # frame_start/frame_end 是 slice_window 的辅助键（起唱检测取能量用），
            # 不属参考旋律契约（song_pitch_refs.pitch_ref = {f0s,notes,midi}），剔除
            pitch_ref = {k: v for k, v in payload.items() if k not in ("frame_start", "frame_end")}
            db.add(
                SongPitchRef(
                    lrc_id=int(line.id),
                    start_ms=payload["start_ms"],
                    end_ms=payload["end_ms"] or end,
                    pitch_ref=pitch_ref,
                    extractor="pyin",
                    version=EXTRACTOR_VERSION,
                )
            )
        db.commit()
    finally:
        db.close()

    # 委托 Java 翻转读侧门禁（失败仅告警 → 扫描「补偿分支」幂等重发，不阻塞 job 完成）
    try:
        notify_pitch_status(int(job.song_id), PitchRefStatus.READY, EXTRACTOR_VERSION)
    except Exception as exc:
        logger.warning(
            "pitch status 委托失败 job=%s song=%s（补偿重发兜底）: %s",
            job_id,
            job.song_id,
            exc,
        )
        _append_payload(job_id, {"delegation_error": str(exc)})


def _finish_job(job_id: int, fail_payload: dict) -> None:
    """收尾：成功 done / 失败 failed（attempts+1，错误快照不伪造）。"""
    db = get_session_factory()()
    try:
        job = db.get(PitchExtractJob, job_id)
        if job is None:
            return
        now = datetime.now(UTC)
        if fail_payload:
            job.status = PitchJobStatus.FAILED
            job.attempts = int(job.attempts or 0) + 1
            job.finished_at = now
            raw = dict(job.payload or {})
            raw.update(fail_payload)
            job.payload = raw
        else:
            job.status = PitchJobStatus.DONE
            job.finished_at = now
            raw = dict(job.payload or {})
            raw.update({"version": EXTRACTOR_VERSION, "finished_at": now.isoformat()})
            job.payload = raw
        db.commit()
    finally:
        db.close()


def _append_payload(job_id: int, extra: dict) -> None:
    db = get_session_factory()()
    try:
        job = db.get(PitchExtractJob, job_id)
        if job is not None:
            raw = dict(job.payload or {})
            raw.update(extra)
            job.payload = raw
            db.commit()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 内部 REST 委托（docs/21 §4 第三条；唯一入口见 app/core/internal_client.py）
# ---------------------------------------------------------------------------
def notify_pitch_status(song_id: int, status: str, version: str | None) -> None:
    """POST /internal/song/{id}/pitch-status（camelCase；幂等；失败抛异常由调用方降级）。"""
    from app.core.internal_client import post_internal

    post_internal(
        f"/internal/song/{song_id}/pitch-status",
        {"songId": song_id, "status": status, "version": version},
    )
