"""M2 核心测试（docs/18 §5.1：元数据/状态锁/回合全链路/答辩/音频/埋点/限流）。

2026-09-21（酒馆迁移）：语料解析/命中（``app.practice.corpus``）与英语场景对话
（dialog）用例随模块移除删除（SSE 回合链路改由影子跟读覆盖，见 test_shadow.py）；
本文件保留 defense/shadow 的通用能力回归：META 解析（``app.practice.meta`` 仍服务
答辩/酒馆）、状态锁与 TTL、答辩知识包校验、影子回合 SSE、答辩生命周期、音频归属/过期、
埋点幂等、限流与 422/40002 输入守卫。
"""

from __future__ import annotations

import json

from app.practice.meta import extract_meta, render_meta
from app.practice.orchestrator import save_audio_bytes
from app.practice.service import validate_bank
from app.practice.state import StateStore

# 合法录音体积占位：需过 settings.min_upload_bytes（40002 下界），
# 这些用例验的是业务链路而非音频有效性，故取一个正常作答量级的字节数。
FAKE_AUDIO = b"fake-audio-bytes" * 128


# ---------------------------------------------------------------------------
# META 提取（app.practice.meta：turn_runner / 答辩 / 酒馆共用解析器）
# ---------------------------------------------------------------------------
def test_extract_meta_ok():
    reply = "Hi there! How are you? "
    meta = render_meta(
        {"score": 90, "errors": []}, "Nice!", [{"phrase": "p", "state": "ok"}], 0, False
    )
    result = extract_meta(reply + meta)
    assert result.ok and result.reply == reply.strip()
    assert result.grammar == {"score": 90, "errors": []}
    assert result.coach_note == "Nice!"


def test_extract_meta_semantic_subscores():
    """③ 语义子分：content/vocab 解析 + 非 dict 防御（模型裸数字不崩、不伪造）。"""
    meta = render_meta(
        {"score": 90, "errors": []},
        "Nice!",
        [],
        0,
        False,
        content={"score": 88, "note": "On-topic."},
        vocab={"score": 84, "note": "Good variety."},
    )
    result = extract_meta("Hello. " + meta)
    assert result.content == {"score": 88, "note": "On-topic."}
    assert result.vocab == {"score": 84, "note": "Good variety."}
    # 防御：裸数字/字符串 meta 项 → properties 返回 None（不崩、不伪造）
    m2 = extract_meta("a [-META-]" + '{"content": 77, "vocab": "88", "conclude": false}')
    assert m2.ok
    assert m2.content is None and m2.vocab is None


def test_extract_meta_missing_degrade():
    result = extract_meta("Just a plain reply without meta.")
    assert result.ok is False and result.reply == "Just a plain reply without meta."


def test_extract_meta_split_across_whitespace():
    reply = "Bye!"
    result = extract_meta(f"{reply} {render_meta(None, 'ok', [], 0, True)}")
    assert result.ok and result.conclude is True


# ---------------------------------------------------------------------------
# 会话状态与锁
# ---------------------------------------------------------------------------
async def test_state_store_lock_prevents_second():
    store = StateStore()
    nonce1 = await store.acquire_lock(1)
    assert nonce1 is not None
    assert await store.acquire_lock(1) is None
    await store.release_lock(1, nonce1)
    assert await store.acquire_lock(1) is not None


async def test_state_ttl():
    import time

    store = StateStore()
    from app.practice.state import SessionState

    state = SessionState(session_id=7, kind="shadow")
    await store.put(state)
    assert (await store.get(7)) is not None
    # 手动过期：P0-1 门面化后测试环境强制内存后端（get_redis→None），内部实现为 _impl
    store._impl._data[7] = (state, time.time() - 1)
    assert (await store.get(7)) is None


# ---------------------------------------------------------------------------
# 知识包校验（6 条规则）
# ---------------------------------------------------------------------------
def _good_bank():
    return {
        "questions": [
            {
                "id": "q1",
                "tier": 1,
                "question": "What is your research question?",
                "basis": "abstract sentence here",
                "key_points": ["research question", "gap"],
                "followups": ["Why?", "How?"],
            },
            {
                "id": "q2",
                "tier": 2,
                "question": "Why this method?",
                "basis": "another sentence",
                "key_points": ["compare", "tradeoff"],
                "followups": ["What if?", "Scale?"],
            },
            {
                "id": "q3",
                "tier": 3,
                "question": "How could it be applied in industry?",
                "basis": "outline line",
                "key_points": ["industry", "impact"],
                "followups": ["Who pays?", "Risk?"],
            },
        ],
        "suggested_order": ["q1", "q2", "q3"],
    }


def test_bank_validation_passes():
    assert validate_bank(_good_bank(), 3) == []


def test_bank_validation_rejects():
    bank = _good_bank()
    bank["questions"][0]["basis"] = ""
    bank["questions"][0]["question"] = "这是中文问题"
    bank["suggested_order"] = ["q1", "q9"]
    errors = validate_bank(bank, 3)
    assert any("basis" in e for e in errors)
    assert any("英文" in e for e in errors)
    assert any("不存在" in e for e in errors)


def test_bank_validation_requires_three_tiers():
    bank = _good_bank()
    bank["questions"] = bank["questions"][:2]
    errors = validate_bank(bank, 3)
    assert any("全覆盖" in e for e in errors)


# ---------------------------------------------------------------------------
# 全链路（Fake clients，经由 API）
# ---------------------------------------------------------------------------
def _seed_shadow_material(
    sentences: str = "Hi, could I get a large flat white to go, please?\nThanks for having me.",
    wpm: int = 145,
) -> int:
    from app.db import get_session_factory
    from app.models import ShadowMaterial

    db = get_session_factory()()
    try:
        material = ShadowMaterial(
            title="m2-shadow",
            level=2,
            text_content=sentences,
            audio_url="/demo/audio/shadow/m2.mp3",
            wpm=wpm,
            duration_s=10,
            interest_tags=[],
            source="demo_only",
            status="published",
        )
        db.add(material)
        db.commit()
        return int(material.id)
    finally:
        db.close()


def _make_shadow_session(client, auth_headers, sentences: str | None = None) -> int:
    """建已发布影子素材 + 建会话，返回 session_id。"""
    mid = _seed_shadow_material() if sentences is None else _seed_shadow_material(sentences)
    resp = client.post(
        "/api/v1/sessions",
        json={"kind": "shadow", "shadow_material_id": mid},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    return int(resp.json()["data"]["id"])


def test_shadow_turn_sse_flow(client, auth_headers):
    """影子回合 SSE：start 出句+示范音频；normal 跟读评分；事件全部可解析。"""
    session_id = _make_shadow_session(client, auth_headers)

    resp = client.post(
        f"/api/v1/sessions/{session_id}/turns",
        data={"action": "start"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    text = resp.text
    assert "turn_start" in text and "audio_chunk" in text and "turn_end" in text

    resp = client.post(
        f"/api/v1/sessions/{session_id}/turns",
        data={"action": "normal"},
        files={"audio": ("a.webm", FAKE_AUDIO, "audio/webm")},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    text = resp.text
    assert "turn_start" in text and "meta_block" in text and "turn_end" in text
    # 事件全部可解析
    for line in text.splitlines():
        if line.startswith("data: "):
            ev = json.loads(line[6:])
            assert "type" in ev


def test_turn_stale_expected_turn_rejected(client, auth_headers):
    """过期 expected_turn → 409（路由预检，与 action/kind 无关）。"""
    session_id = _make_shadow_session(client, auth_headers)
    resp = client.post(
        f"/api/v1/sessions/{session_id}/turns",
        data={"action": "normal", "expected_turn": "99"},  # 过期轮次
        files={"audio": ("a.webm", FAKE_AUDIO, "audio/webm")},
        headers=auth_headers,
    )
    assert resp.status_code == 409


def test_fluency_features_flow_into_attempt_and_report(client, auth_headers):
    """集成：跟读回合（Fake ASR 词级时间戳）→ attempts.wpm/details.fluency → 报告透出。

    Fake 词表含 1.05s 停顿：wpm=145.83 / pause_count=1 / long_pause_count=1。
    单句素材：一轮即末句系结，自动收尾并生成报告。
    """
    from app.db import get_session_factory
    from app.models import Attempt
    from sqlalchemy import select

    session_id = _make_shadow_session(client, auth_headers, sentences="Hi there.")
    resp = client.post(
        f"/api/v1/sessions/{session_id}/turns",
        data={"action": "normal"},
        files={"audio": ("a.webm", FAKE_AUDIO, "audio/webm")},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    report_id = None
    for line in resp.text.splitlines():
        if line.startswith("data: "):
            ev = json.loads(line[6:])
            if ev.get("type") == "session_end":
                report_id = ev.get("report_id")
    assert report_id is not None, resp.text

    db = get_session_factory()()
    try:
        attempt = db.execute(select(Attempt).where(Attempt.session_id == session_id)).scalar_one()
        assert attempt.wpm is not None
        assert float(attempt.wpm) == 145.83
        features = (attempt.details or {}).get("fluency")
        assert features["word_count"] == 7
        assert features["pause_count"] == 1
        assert features["long_pause_count"] == 1
        assert features["max_pause_s"] == 1.05
    finally:
        db.close()

    resp = client.get(f"/api/v1/reports/{report_id}", headers=auth_headers)
    assert resp.status_code == 200
    metrics = resp.json()["data"]["metrics"]
    assert metrics["kind"] == "shadow"
    attempts = metrics["attempts"]
    assert attempts[0]["wpm"] == 145.83
    assert attempts[0]["fluency_features"]["pause_count"] == 1
    assert attempts[0]["fluency_features"]["wpm"] == 145.83


def test_defense_profile_lifecycle(client, auth_headers):
    resp = client.post(
        "/api/v1/defense/profiles",
        json={
            "title": "测试论文",
            "abstract": "This thesis studies speaking practice with AI.",
            "outline": "1. Introduction 2. Method 3. Results",
            "highlights": "A novel coverage metric.",
            "thesis_text": "This thesis studies speaking practice with AI agents.",
            "question_count": 5,
            "emphasis": "balanced",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    pid = resp.json()["data"]["id"]

    # 生成任务异步——测试模式 Fake LLM 返回非 JSON？generate_bank 会失败→failed；
    # 直接验证软删 + 脱敏语义
    resp = client.delete(f"/api/v1/defense/profiles/{pid}", headers=auth_headers)
    assert resp.status_code == 200
    resp = client.get(f"/api/v1/defense/profiles/{pid}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "deleted"
    # 脱敏：knowledge_bank 不返回
    assert resp.json()["data"]["knowledge_bank"] == {}

    # 越权：另一用户 404
    resp = client.get(f"/api/v1/defense/profiles/{pid}", headers={"X-Test-User-Id": "2"})
    assert resp.status_code == 404


def test_defense_profile_input_validation(client, auth_headers):
    resp = client.post(
        "/api/v1/defense/profiles",
        json={
            "title": "x",
            "abstract": "short",
            "outline": "o",
            "highlights": "h",
            "thesis_text": "y" * 9000,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 422  # abstract <20 或 thesis 超长


# ---------------------------------------------------------------------------
# 音频：鉴权 + 惰性过期 + 越权
# ---------------------------------------------------------------------------
def test_save_audio_and_ownership(client, auth_headers):
    url = save_audio_bytes(b"MP3 data for test")
    assert url.startswith("/api/v1/audio/")
    # 归属：未落 attempt/message → 403
    resp = client.get(url, headers=auth_headers)
    assert resp.status_code == 403


def test_published_song_asset_survives_ttl(client, auth_headers, settings):
    """平台素材（已发布歌曲参考旋律）不受 24h 惰性过期约束，且**不得被物理删除**。

    2026-09-10 BUG 回归（**修复前必失败**：旧实现「TTL+unlink」在素材豁免之前，
    超 24h 的参考旋律会被点一次「听参考旋律」直接删除 → demo 曲库不可逆损坏）。
    依据：docs/06 §8（音频存储与清理）、docs/21 §2.1 op11。
    """
    import os
    import time
    from pathlib import Path

    from app.db import get_session_factory
    from app.models import Song
    from app.models.base import ContentStatus, PitchRefStatus

    db = get_session_factory()()
    try:
        db.add(
            Song(
                title="TTL Probe",
                level=1,
                audio_url="/data/audio/song_ttl_probe.wav",
                status=ContentStatus.PUBLISHED,
                pitch_ref_status=PitchRefStatus.READY,
            )
        )
        db.commit()
    finally:
        db.close()

    asset = Path(settings.audio_dir) / "song_ttl_probe.wav"
    asset.parent.mkdir(parents=True, exist_ok=True)
    asset.write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt ")  # 有效 wav 头（回放不解码内容）
    expired = time.time() - (settings.audio_ttl_hours + 1) * 3600
    os.utime(asset, (expired, expired))

    resp = client.get("/api/v1/audio/song_ttl_probe.wav", headers=auth_headers)
    assert resp.status_code == 200, resp.text  # 修复前：410 audio expired
    assert asset.exists(), "平台素材被惰性清理删除（修复前行为）"


def test_published_song_flac_asset_playable(client, auth_headers, settings):
    """已发布歌曲的 **flac** 参考旋律可回放（2026-09-22 本地演示曲库回归）。

    修复前必失败：文件名白名单只认 `mp3|wav|m4a|ogg|webm`，本地演示曲库 8 首里有 7 首是
    flac → 唱吧「听参考旋律」全部 **400 bad audio name**（浏览器网络面板实测），
    mp3 那首正常——即用户在控制台看到的 `demo_*.flac 400`。
    """
    from pathlib import Path

    from app.db import get_session_factory
    from app.models import Song
    from app.models.base import ContentStatus, PitchRefStatus

    db = get_session_factory()()
    try:
        db.add(
            Song(
                title="FLAC Probe",
                level=1,
                audio_url="/data/audio/demo_flac_probe.flac",
                status=ContentStatus.PUBLISHED,
                pitch_ref_status=PitchRefStatus.READY,
            )
        )
        db.commit()
    finally:
        db.close()

    asset = Path(settings.audio_dir) / "demo_flac_probe.flac"
    asset.parent.mkdir(parents=True, exist_ok=True)
    asset.write_bytes(b"fLaC\x00\x00\x00\x22")  # 有效 flac 魔数（回放不解码内容）

    resp = client.get("/api/v1/audio/demo_flac_probe.flac", headers=auth_headers)
    assert resp.status_code == 200, resp.text  # 修复前：400 bad audio name
    assert resp.headers["content-type"].startswith("audio/flac")  # 修复前：audio/mpeg


def test_user_recording_still_expires_after_ttl(client, auth_headers, settings):
    """用户录音的 24h 保留期不因上面的分流而失效（隐私口径回归护栏）。

    素材豁免只对「已发布歌曲引用的文件」生效；普通录音超 TTL 仍应删除并 410（docs/06 §9.7）。
    """
    import time
    from pathlib import Path

    rec = Path(settings.audio_dir) / "deadbeef00.mp3"
    rec.parent.mkdir(parents=True, exist_ok=True)
    rec.write_bytes(b"ID3\x03\x00\x00\x00")
    expired = time.time() - (settings.audio_ttl_hours + 1) * 3600
    import os

    os.utime(rec, (expired, expired))

    resp = client.get("/api/v1/audio/deadbeef00.mp3", headers=auth_headers)
    assert resp.status_code == 410
    assert resp.json()["code"] == 41001
    assert not rec.exists(), "超期用户录音应被惰性清理"


# ---------------------------------------------------------------------------
# 埋点：幂等去重
# ---------------------------------------------------------------------------
def test_events_idempotent(client, auth_headers):
    import time

    payload = {
        "event_type": "page_view",
        "client_event_id": "e-001",
        "occurred_at": int(time.time()),
    }
    r1 = client.post("/api/v1/events", json=payload, headers=auth_headers)
    assert r1.status_code == 200 and r1.json()["data"]["dedup"] is False
    r2 = client.post("/api/v1/events", json=payload, headers=auth_headers)
    assert r2.status_code == 200 and r2.json()["data"]["dedup"] is True


def test_events_unknown_type_ignored(client, auth_headers):
    r = client.post("/api/v1/events", json={"event_type": "hack_event"}, headers=auth_headers)
    assert r.status_code == 200 and r.json()["data"]["dedup"] is True


def test_event_types_all_20_insertable(client, auth_headers):
    """docs/06 §9.1：20 类事件逐类可落库（防常量/CHECK 漂移；15 类既有 + 读书域 5 类）。"""
    import time

    from app.models.base import EventTypes

    allowed = {v for k, v in vars(EventTypes).items() if k.isupper() and not k.startswith("__")}
    assert len(allowed) == 20, f"事件类应有 20 个：{allowed}"
    now = int(time.time())
    for i, name in enumerate(sorted(allowed)):
        r = client.post(
            "/api/v1/events",
            json={
                "event_type": name,
                "client_event_id": f"all-types-{i}",
                "occurred_at": now,
            },
            headers=auth_headers,
        )
        assert r.status_code == 200, f"{name}: {r.text}"
    # 维度快照列（docs/06 §9.1）同时带 payload 校验一次
    r = client.post(
        "/api/v1/events",
        json={
            "event_type": "corpus_hit",
            "client_event_id": "all-types-99",
            "occurred_at": now,
            "scene_id": 1,
            "payload": {"phrase": "I would like a coffee, please", "state": "ok"},
        },
        headers=auth_headers,
    )
    assert r.status_code == 200 and r.json()["data"]["dedup"] is False


# ---------------------------------------------------------------------------
# 限流：LLM 桶 429
# ---------------------------------------------------------------------------
def test_rate_limit_429(client, auth_headers, monkeypatch):
    import app.core.ratelimit as rl

    async def fake_consume(bucket, limit, user_id):
        raise __import__("fastapi").HTTPException(status_code=429, detail="rate limited (llm)")

    monkeypatch.setattr(rl, "_redis_consume", fake_consume)
    session_id = _make_shadow_session(client, auth_headers)
    resp = client.post(
        f"/api/v1/sessions/{session_id}/turns",
        data={"action": "normal"},
        files={"audio": ("a.webm", FAKE_AUDIO, "audio/webm")},
        headers=auth_headers,
    )
    # 顺序：归属 ✓ → 状态预检 ✓ → 音频校验 ✓ → 限流 → 429
    assert resp.status_code == 429


def test_turn_rate_limit_buckets_by_action(client, auth_headers, monkeypatch):
    """2026-09-07 评审：分桶按 action **实际消耗**扣（此前无差别扣 asr+ise+llm 三桶——
    hint/demo/abandon 零管线消耗也扣，会误耗尽用户配额）。修复前 hint/abandon 断言失败。
    """
    import app.core.ratelimit as rl

    buckets: list[str] = []

    async def fake_consume(bucket, limit, user_id):
        buckets.append(bucket)
        return 0, 60

    monkeypatch.setattr(rl, "_redis_consume", fake_consume)

    def turn(session_id: int, action: str, audio: bool):
        kwargs: dict = {"data": {"action": action}, "headers": auth_headers}
        if audio:
            kwargs["files"] = {"audio": ("a.webm", FAKE_AUDIO, "audio/webm")}
        resp = client.post(f"/api/v1/sessions/{session_id}/turns", **kwargs)
        assert resp.status_code == 200, resp.text

    # normal（音频回合）：ASR + ISE + LLM 三桶各 1
    sid = _make_shadow_session(client, auth_headers)
    turn(sid, "normal", audio=True)
    assert buckets == ["asr", "ise", "llm"], buckets

    # start：无转写/评分，仅 LLM 出句/示范
    buckets.clear()
    sid = _make_shadow_session(client, auth_headers)
    turn(sid, "start", audio=False)
    assert buckets == ["llm"], buckets

    # hint（无音频轻分支）：零管线消耗 → 零扣（影子回合流内以 422 error 事件收场）
    buckets.clear()
    sid = _make_shadow_session(client, auth_headers)
    turn(sid, "hint", audio=False)
    assert buckets == [], buckets

    # abandon（收尾）：仅 LLM 摘要
    buckets.clear()
    sid = _make_shadow_session(client, auth_headers)
    turn(sid, "abandon", audio=False)
    assert buckets == ["llm"], buckets


# ---------------------------------------------------------------------------
# 音频下界守卫（40002）：前端停止键可用后，误触会产出 ~0ms 的 webm
# ---------------------------------------------------------------------------
def test_placement_rejects_empty_audio(client, auth_headers):
    """空/近空录音返回 400 + 40002，且**先于**题目查找与限流扣减发生。

    刻意用一个不存在的 item_id：若守卫没有前置，会先撞 404 而不是 40002。
    """
    resp = client.post(
        "/api/v1/placement/items/999999/audio",
        files={"audio": ("a.webm", b"\x1aE\xdf\xa3", "audio/webm")},  # 近空 webm 头
        headers=auth_headers,
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["code"] == 40002


def test_placement_size_guard_lets_normal_audio_through(client, auth_headers):
    """正常体积的录音不被下界拦下——此时才轮到题目查找（404）。"""
    resp = client.post(
        "/api/v1/placement/items/999999/audio",
        files={"audio": ("a.webm", FAKE_AUDIO, "audio/webm")},
        headers=auth_headers,
    )
    assert resp.status_code == 404, resp.text


def test_turn_rejects_empty_audio(client, auth_headers):
    """跟读回合同样挡空录音：否则会推进 current_turn 且不可重来。

    （P0-3 后顺序：归属校验 → 音频下界守卫 → 状态预检，故须用真实会话验证 40002。）
    """
    session_id = _make_shadow_session(client, auth_headers)
    resp = client.post(
        f"/api/v1/sessions/{session_id}/turns",
        data={"action": "normal"},
        files={"audio": ("a.webm", b"\x1aE\xdf\xa3", "audio/webm")},
        headers=auth_headers,
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["code"] == 40002


def test_stub_pipeline_endpoints_keep_no_lower_bound(client, auth_headers):
    """/asr /score 是无状态管线端点，不消耗可耗尽资源 → 保持 min_bytes=0 的历史行为。

    （docs/19 P0-4 起需鉴权——auth_headers 直通；下界行为不变。）
    """
    resp = client.post(
        "/api/v1/asr",
        files={"audio": ("tiny.wav", b"RIFF__tiny__", "audio/wav")},
        data={"language": "en"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["code"] == 0
