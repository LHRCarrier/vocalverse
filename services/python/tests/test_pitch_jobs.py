"""参考旋律提取任务编排测试（唱歌 P0 D2/D6 · pitch_extract_jobs 事实源）。

覆盖：扫描建任务（published 门禁/已有 refs 跳过/进行中任务去重/LRC 重写重建/
**提取器世代升级自动重建（pyin-v1 refs → 建任务）**）/ 工作器状态机
（queued→running→done|failed）/ 委托 camelCase 键名（P0-6 类回归）/
委托失败补偿（refs 齐全但门禁未 ready → 幂等重发）/ 失败重试达上限不再自动重建。
CI 零模型：Fake 提取器注入 + ffmpeg 转换打桩（测试音频由 soundfile 合成）。
"""

from __future__ import annotations

import math
from pathlib import Path

from app.audio.pitch import EXTRACTOR_VERSION
from app.models import Lrc, PitchExtractJob, Song, SongPitchRef
from app.models.base import PitchJobStatus
from sqlalchemy import delete, select, update


def _install_fake_post(monkeypatch, resp_status: int = 200, fail_first: int = 0):
    """HTTP post 打桩：捕获请求、可模拟前 N 次失败（≥400 抛错）。"""
    captured = {"calls": []}

    class FakeResp:
        status_code = resp_status

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(f"upstream {self.status_code}")

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["calls"].append(
            {"url": url, "json": json or {}, "headers": headers or {}, "timeout": timeout}
        )
        if len(captured["calls"]) <= fail_first:
            raise RuntimeError("upstream unavailable")
        return FakeResp()

    monkeypatch.setattr("app.core.internal_client.httpx.post", fake_post)
    return captured


def _seed_song(db, *, status: str = "published", with_lrc: int = 2, title="Twinkle") -> int:
    song = Song(
        title=title,
        level=1,
        audio_url="/data/audio/twinkle.wav",
        status=status,
        pitch_ref_status="missing",
    )
    db.add(song)
    db.flush()
    for i in range(with_lrc):
        db.add(
            Lrc(
                song_id=song.id,
                seq=i + 1,
                offset_ms=i * 3000,
                end_offset_ms=(i + 1) * 3000,
                line_text=f"line {i + 1}",
            )
        )
    db.flush()
    return int(song.id)


def _wav_audio(tmp_path: Path) -> str:
    """合成 1.2s 440Hz 正弦 wav（供 ffmpeg 桩拷贝为 16k 单声道输入）。"""
    import numpy as np
    import soundfile as sf

    sr = 16000
    t = np.linspace(0, 1.2, int(sr * 1.2), endpoint=False)
    path = tmp_path / "tone.wav"
    sf.write(str(path), (0.5 * np.sin(2 * math.pi * 440 * t)).astype("float32"), sr)
    return str(path)


class FakeExtractor:
    """FakePitchExtractor 的结构等价体（避免依赖 soundfile 读取真实 wav）。"""

    def extract_track(self, wav_path: str):
        from app.audio.pitch import TrackF0

        sr = 16000
        hop = 512
        n = 60
        return TrackF0(
            sr=sr,
            hop_ms=1000.0 * hop / sr,
            times_ms=[i * 1000.0 * hop / sr for i in range(n)],
            f0=[440.0] * n,
            midi=[69] * n,
            names=["A4"] * n,
            duration_ms=n * 1000.0 * hop / sr,
        )


def _install_jobs_stubs(monkeypatch, tmp_path, audio_path: str | None):
    """打桩 ffmpeg 转换 + Fake 提取器，返回 jobs 模块。"""
    import app.sing.jobs as jobs

    if audio_path is not None:

        async def _fake_convert(src: str, dst: str, timeout_s: float = 15.0):
            import shutil

            shutil.copyfile(audio_path, dst)

        monkeypatch.setattr("app.sing.jobs.to_16k_mono_wav", _fake_convert)
    monkeypatch.setattr("app.audio.pitch.get_pitch_extractor", lambda: FakeExtractor())
    return jobs


def _new_db():
    from app.db import get_session_factory

    return get_session_factory()()


# ---------------------------------------------------------------------------
# 扫描
# ---------------------------------------------------------------------------
def test_scan_creates_jobs_for_published_song_without_refs():
    from app.sing.jobs import lrc_generation, scan_due_jobs

    db = _new_db()
    try:
        song_id = _seed_song(db)
        gen = lrc_generation(db, song_id)
        assert gen is not None and gen[1] == f"lrc-m{gen[0]}"
        db.commit()
    finally:
        db.close()

    assert scan_due_jobs() == 1

    db = _new_db()
    try:
        jobs = db.execute(select(PitchExtractJob)).scalars().all()
        assert len(jobs) == 1
        assert jobs[0].song_id == song_id
        assert jobs[0].status == PitchJobStatus.QUEUED
        assert jobs[0].payload == {}
    finally:
        db.close()


def test_scan_skips_draft_and_skips_when_refs_ready():
    from app.sing.jobs import scan_due_jobs

    db = _new_db()
    try:
        _seed_song(db, status="draft", title="DraftSong")
        ready_id = _seed_song(db, title="ReadySong")
        lrc_ids = db.execute(select(Lrc.id).where(Lrc.song_id == ready_id)).scalars().all()
        for lid in lrc_ids:
            db.add(
                SongPitchRef(
                    lrc_id=int(lid),
                    start_ms=0,
                    end_ms=3000,
                    pitch_ref={"f0s": [440.0], "notes": ["A4"]},
                    version=EXTRACTOR_VERSION,
                )
            )
        db.execute(update(Song).where(Song.id == ready_id).values(pitch_ref_status="ready"))
        db.commit()
    finally:
        db.close()

    # draft 不扫；ready 无缺 → 不建任务
    assert scan_due_jobs() == 0

    db = _new_db()
    try:
        assert db.execute(select(PitchExtractJob)).scalars().all() == []
    finally:
        db.close()


def test_scan_does_not_create_duplicate_when_active_job_exists():
    from app.sing.jobs import scan_due_jobs

    db = _new_db()
    try:
        song_id = _seed_song(db)
        lrc_id = db.execute(select(Lrc.id).where(Lrc.song_id == song_id).limit(1)).scalar()
        db.add(
            PitchExtractJob(song_id=song_id, lrc_id=int(lrc_id), revision="lrc-m1", status="queued")
        )
        db.commit()
    finally:
        db.close()
    assert scan_due_jobs() == 0


# ---------------------------------------------------------------------------
# 工作器 + 委托
# ---------------------------------------------------------------------------
def test_run_job_writes_refs_and_delegates_camelcase(monkeypatch, tmp_path):
    from app.sing.jobs import scan_due_jobs

    captured = _install_fake_post(monkeypatch)
    audio = _wav_audio(tmp_path)
    db = _new_db()
    try:
        song_id = _seed_song(db)
        db.execute(update(Song).where(Song.id == song_id).values(audio_url=audio))
        db.commit()
    finally:
        db.close()

    assert scan_due_jobs() == 1
    jobs = _install_jobs_stubs(monkeypatch, tmp_path, audio)
    db = _new_db()
    try:
        job_id = int(db.execute(select(PitchExtractJob)).scalar_one().id)
    finally:
        db.close()
    jobs.run_job_sync(job_id)

    db = _new_db()
    try:
        job = db.execute(select(PitchExtractJob)).scalar_one()
        assert job.status == PitchJobStatus.DONE
        assert job.attempts == 0
        refs = db.execute(select(SongPitchRef)).scalars().all()
        assert len(refs) == 2
        assert all(r.version == EXTRACTOR_VERSION for r in refs)
        assert refs[0].pitch_ref["f0s"] != []
        # pyin-v2：pitch_ref 必含参考音符级 onset（item7 参考侧数据源；BUG-1 修复的落库契约）
        assert "onsets_ms" in refs[0].pitch_ref
        # 委托契约：camelCase 键名 + 路径参数 + Bearer + 3s（P0-6 类回归）
        assert len(captured["calls"]) == 1
        call = captured["calls"][0]
        assert call["url"].endswith(f"/internal/song/{song_id}/pitch-status")
        assert call["json"] == {"songId": song_id, "status": "ready", "version": EXTRACTOR_VERSION}
        assert "songId" in call["json"] and "song_id" not in call["json"]
        assert call["headers"]["Authorization"].startswith("Bearer ")
        assert call["timeout"] == 3.0
    finally:
        db.close()


def test_run_job_delegation_failure_keeps_done_and_compensates(monkeypatch, tmp_path):
    from app.sing.jobs import scan_due_jobs

    captured = {"calls": []}

    class FakeResp:
        status_code = 200

        def raise_for_status(self):
            return None

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["calls"].append({"url": url, "json": json or {}})
        if len(captured["calls"]) == 1:
            raise RuntimeError("java down")
        return FakeResp()

    monkeypatch.setattr("app.core.internal_client.httpx.post", fake_post)
    audio = _wav_audio(tmp_path)
    db = _new_db()
    try:
        song_id = _seed_song(db)
        db.execute(update(Song).where(Song.id == song_id).values(audio_url=audio))
        db.commit()
    finally:
        db.close()

    assert scan_due_jobs() == 1
    jobs = _install_jobs_stubs(monkeypatch, tmp_path, audio)
    db = _new_db()
    try:
        job_id = int(db.execute(select(PitchExtractJob)).scalar_one().id)
    finally:
        db.close()
    jobs.run_job_sync(job_id)

    db = _new_db()
    try:
        job = db.execute(select(PitchExtractJob)).scalar_one()
        assert job.status == PitchJobStatus.DONE  # 提取成功不因委托失败回滚
        assert "delegation_error" in (job.payload or {})
    finally:
        db.close()

    # 补偿：扫描重发委托（幂等，同值无害；songs 表 Python 不 UPDATE，门禁仍 missing）
    assert scan_due_jobs() == 0  # refs 齐全 → 不建新任务
    assert len(captured["calls"]) == 2
    assert captured["calls"][1]["json"] == {
        "songId": song_id,
        "status": "ready",
        "version": EXTRACTOR_VERSION,
    }


def test_scan_rebuilds_refs_when_extractor_generation_is_old(monkeypatch, tmp_path):
    """**提取器世代升级自动重建（BUG-1/A2 的新行为）**：refs 齐全但 version=pyin-v1
    （旧世代，无 onsets_ms）→ `_refs_ready` 判定"世代旧" → 扫描建任务重建。

    这是 pyin-v2 上线后 3 首 demo 自动重提取的机制（不触碰 Java 独占写的 songs 表；
    门禁状态仍由内部 REST 委托翻转）。
    """
    from app.sing.jobs import scan_due_jobs

    _install_fake_post(monkeypatch)
    audio = _wav_audio(tmp_path)
    db = _new_db()
    try:
        song_id = _seed_song(db)
        db.execute(update(Song).where(Song.id == song_id).values(audio_url=audio))
        lrc_ids = db.execute(select(Lrc.id).where(Lrc.song_id == song_id)).scalars().all()
        for lid in lrc_ids:
            db.add(
                SongPitchRef(
                    lrc_id=int(lid),
                    start_ms=0,
                    end_ms=3000,
                    pitch_ref={"f0s": [440.0], "notes": ["A4"]},  # 旧世代无 onsets_ms
                    version="pyin-v1",
                )
            )
        db.commit()
    finally:
        db.close()

    assert scan_due_jobs() == 1, "旧世代 refs 应触发重建任务"


def test_run_job_extraction_failure_marks_failed_and_retries_to_cap(monkeypatch, tmp_path):
    from app.sing.jobs import scan_due_jobs

    _install_fake_post(monkeypatch)
    db = _new_db()
    try:
        song_id = _seed_song(db)
        # 音频 URL 指向不存在的文件 → 提取失败（路径归一返回 None）
        db.execute(update(Song).where(Song.id == song_id).values(audio_url="/data/audio/nope.wav"))
        db.commit()
    finally:
        db.close()

    jobs = _install_jobs_stubs(monkeypatch, tmp_path, None)

    for attempt in range(3):
        assert scan_due_jobs() in (0, 1)  # 第一次建任务；随后重试重置（此时无 active → 1）
        db = _new_db()
        try:
            job = db.execute(select(PitchExtractJob)).scalar_one()
            assert job.status == PitchJobStatus.QUEUED
            job_id = int(job.id)
        finally:
            db.close()
        jobs.run_job_sync(job_id)
        db = _new_db()
        try:
            job = db.execute(select(PitchExtractJob)).scalar_one()
            assert job.status == PitchJobStatus.FAILED
            assert job.attempts == attempt + 1
            assert "error" in (job.payload or {})
        finally:
            db.close()

    # 达上限：扫描不再自动重建（保留失败证据）
    assert scan_due_jobs() == 0
    db = _new_db()
    try:
        job = db.execute(select(PitchExtractJob)).scalar_one()
        assert job.attempts == 3
        assert job.status == PitchJobStatus.FAILED
    finally:
        db.close()


def test_lrc_rewrite_cascades_job_and_rebuilds(monkeypatch, tmp_path):
    """LRC 整首重写（删旧插新）→ 旧 job 级联删除 → 扫描按新世代重建。"""
    # SQLite 默认不开 FK（CASCADE 不生效）：显式开启（StaticPool 单连接，PRAGMA 即生效）
    from app.db import get_engine
    from app.sing.jobs import scan_due_jobs

    engine = get_engine()
    with engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA foreign_keys=ON")

    _install_fake_post(monkeypatch)
    audio = _wav_audio(tmp_path)
    db = _new_db()
    try:
        song_id = _seed_song(db)
        db.execute(update(Song).where(Song.id == song_id).values(audio_url=audio))
        db.commit()
    finally:
        db.close()

    assert scan_due_jobs() == 1
    db = _new_db()
    try:
        # 整首重写：删旧 → 插新（seq 重排、id 变化）
        db.execute(delete(Lrc).where(Lrc.song_id == song_id))
        for i in range(2):
            db.add(
                Lrc(
                    song_id=song_id,
                    seq=i + 1,
                    offset_ms=i * 4000,
                    end_offset_ms=(i + 1) * 4000,
                    line_text=f"new line {i + 1}",
                )
            )
        db.commit()
        new_lrc_ids = [
            int(x) for x in db.execute(select(Lrc.id).where(Lrc.song_id == song_id)).scalars().all()
        ]
        # 旧 job（引用旧 lrc_id）被 CASCADE 清除
        assert db.execute(select(PitchExtractJob)).scalars().all() == []
    finally:
        db.close()

    assert scan_due_jobs() == 1
    db = _new_db()
    try:
        job = db.execute(select(PitchExtractJob)).scalar_one()
        # 语义断言：新 job 引用新世代 LRC 行；旧 job 已随 CASCADE 删除（上方已断言）
        # （revision 在 PG IDENTITY 下单调（max id 严格递增）；SQLite 删空后 rowid 复用，
        #  故不比对 revision 字符串，只比对引用与行身份）
        assert job.lrc_id in new_lrc_ids
        assert job.revision.startswith("lrc-m")
    finally:
        db.close()


# ---------------------------------------------------------------------------
# P1-12：并发闸门 + 重试上限的世代复位（2026-09-10 修复回归）
# ---------------------------------------------------------------------------
def test_drain_queue_caps_concurrency_to_setting(monkeypatch):
    """并发上限 = `pitch_extract_concurrency`（docs/06 §8③ 的 CPU 队列语义）。

    修复前必失败：旧实现 `async with _sem(): await gather(*(to_thread(...)))` 只取 **1 个**许可
    就并发跑满一批——实测并发 = 批大小（5），配置值 2 形同虚设（8 个任务同时 pyin = 8×CPU）。
    """
    import asyncio
    import time

    import app.sing.jobs as jobs
    from app.core.config import get_settings

    limit = get_settings().pitch_extract_concurrency
    monkeypatch.setattr(jobs, "_extract_sem", None)  # 丢掉单例，按当前配置重建

    batch = limit + 3
    db = _new_db()
    try:
        song_id = _seed_song(db, with_lrc=batch)
        lrc_ids = [
            int(x) for x in db.execute(select(Lrc.id).where(Lrc.song_id == song_id)).scalars().all()
        ]
        # 进行中任务有 UNIQUE(lrc_id) 部分索引 → 每个任务引用不同 LRC 行（与真实扫描一致）
        for lrc_id in lrc_ids:
            db.add(
                PitchExtractJob(
                    song_id=song_id,
                    lrc_id=lrc_id,
                    revision="lrc-m1",
                    status=PitchJobStatus.QUEUED,
                    payload={},
                )
            )
        db.commit()
    finally:
        db.close()

    state = {"cur": 0, "max": 0}

    def fake_run_sync(job_id: int, max_attempts: int = 3) -> None:
        state["cur"] += 1
        state["max"] = max(state["max"], state["cur"])
        time.sleep(0.05)
        state["cur"] -= 1

    monkeypatch.setattr(jobs, "run_job_sync", fake_run_sync)
    asyncio.run(jobs._drain_queue())

    assert state["max"] == limit, f"并发应被信号量限到 {limit}，实测 {state['max']}"


def test_scan_revives_capped_job_after_extractor_generation_change(monkeypatch):
    """提取器换代后，撞了重试上限的失败任务必须重建（P1-12 修复）。

    真实事故（BUG-2）：pyin-v1 的 upsert 缺陷让 3 首 demo 的提取任务 attempts=3 全 failed；
    换代到 pyin-v2 并修好缺陷后，旧判据 `attempts >= max → 永久跳过` 让这些歌**再也不会被重建**
    （refs 永远 missing，跟唱入口 40905），只能人工改库。
    修复前必失败：`assert scan_due_jobs() == 1` 实测 0。
    """
    from app.sing.jobs import scan_due_jobs

    _install_fake_post(monkeypatch)  # 即便走委托也不发真实请求
    db = _new_db()
    try:
        song_id = _seed_song(db)
        lrc_ids = [
            int(x) for x in db.execute(select(Lrc.id).where(Lrc.song_id == song_id)).scalars().all()
        ]
        from app.sing.jobs import lrc_generation

        revision = lrc_generation(db, song_id)[1]  # **当前**世代：排除 revision 分支干扰
        db.add(
            PitchExtractJob(
                song_id=song_id,
                lrc_id=lrc_ids[0],
                revision=revision,
                status=PitchJobStatus.FAILED,
                attempts=3,
                payload={
                    "error": "UniqueViolation(uq_song_pitch_refs_lrc_id)",
                    "extractor_version": "pyin-v1",  # ← 失败发生在旧提取器世代
                },
            )
        )
        db.commit()
    finally:
        db.close()

    assert scan_due_jobs() == 1, "换代后应重建（修复前 attempts=3 撞上限 → 永久跳过）"
    db = _new_db()
    try:
        job = db.execute(select(PitchExtractJob)).scalar_one()
        assert job.status == PitchJobStatus.QUEUED
        assert job.attempts == 0, "新世代应拿到完整重试预算（旧世代的失败不消耗它）"
    finally:
        db.close()


def test_scan_probes_legacy_capped_job_only_once(monkeypatch, tmp_path):
    """历史失败行（payload 无提取器版本快照）→ 只放行**一次**探针，不重置预算。

    本次修复前落库的失败行没有 `extractor_version`，无法判断是否换代；一律跳过会永久卡死，
    一律重置则等于取消重试上限。取折中：放行一次、失败后（已记录当前版本）立即回到上限。
    修复前必失败：`assert scan_due_jobs() == 1` 实测 0。
    """
    from app.sing.jobs import lrc_generation, scan_due_jobs

    _install_fake_post(monkeypatch)
    db = _new_db()
    try:
        song_id = _seed_song(db)
        db.execute(update(Song).where(Song.id == song_id).values(audio_url="/data/audio/nope.wav"))
        lrc_ids = [
            int(x) for x in db.execute(select(Lrc.id).where(Lrc.song_id == song_id)).scalars().all()
        ]
        db.add(
            PitchExtractJob(
                song_id=song_id,
                lrc_id=lrc_ids[0],
                revision=lrc_generation(db, song_id)[1],
                status=PitchJobStatus.FAILED,
                attempts=3,
                payload={"error": "音频文件不可达"},  # 无 extractor_version（历史行）
            )
        )
        db.commit()
    finally:
        db.close()

    jobs = _install_jobs_stubs(monkeypatch, tmp_path, None)
    assert scan_due_jobs() == 1, "世代不明的历史失败行应放行一次探针（修复前永久跳过）"
    db = _new_db()
    try:
        job = db.execute(select(PitchExtractJob)).scalar_one()
        assert job.attempts == 3, "探针不重置预算（只多给这一次）"
        job_id = int(job.id)
    finally:
        db.close()

    jobs.run_job_sync(job_id)  # 探针再失败 → attempts=4 且 payload 记下当前世代
    db = _new_db()
    try:
        job = db.get(PitchExtractJob, job_id)
        assert job.attempts == 4
        assert job.payload["extractor_version"] == EXTRACTOR_VERSION
    finally:
        db.close()
    assert scan_due_jobs() == 0, "记录版本后回到上限约束（不会无限探针）"


def test_retry_decision_matrix():
    """`retry_decision` 四态（P1-12）：

    换代 reset / 撞上限 skip / 无版本 probe / 未达上限 requeue。
    """
    from app.sing.jobs import (
        RETRY_PROBE,
        RETRY_REQUEUE,
        RETRY_RESET,
        RETRY_SKIP,
        retry_decision,
    )

    class _Row:
        """轻量替身：只用 attempts / revision / payload 三个属性。"""

        def __init__(self, attempts: int, revision: str, payload: dict):
            self.attempts = attempts
            self.revision = revision
            self.payload = payload

    cur = {"extractor_version": EXTRACTOR_VERSION}
    assert retry_decision(None, "lrc-m1", 3) == RETRY_REQUEUE  # 无 failed 行 → 走新建分支
    assert retry_decision(_Row(1, "lrc-m1", cur), "lrc-m1", 3) == RETRY_REQUEUE
    assert retry_decision(_Row(3, "lrc-m1", cur), "lrc-m1", 3) == RETRY_SKIP
    assert retry_decision(_Row(3, "lrc-m1", {"extractor_version": "pyin-v0"}), "lrc-m1", 3) == (
        RETRY_RESET
    )
    assert retry_decision(_Row(3, "lrc-m-old", cur), "lrc-m1", 3) == RETRY_RESET
    assert retry_decision(_Row(3, "lrc-m1", {"error": "boom"}), "lrc-m1", 3) == RETRY_PROBE
