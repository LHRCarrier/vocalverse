"""M2 核心测试（docs/18 §5.1：语料/元数据/状态锁/回合全链路/答辩/音频/埋点/限流）。"""

from __future__ import annotations

import json

import pytest
from app.practice.corpus import match_rule, parse_corpus
from app.practice.meta import extract_meta, render_meta
from app.practice.orchestrator import save_audio_bytes
from app.practice.service import validate_bank
from app.practice.state import StateStore

# 合法录音体积占位：需过 settings.min_upload_bytes（40002 下界），
# 这些用例验的是业务链路而非音频有效性，故取一个正常作答量级的字节数。
FAKE_AUDIO = b"fake-audio-bytes" * 128


# ---------------------------------------------------------------------------
# 语料匹配（规则通道权威）
# ---------------------------------------------------------------------------
def test_corpus_parse_and_match():
    corpus = parse_corpus("I'd like a coffee, please.|请给我来杯咖啡\nHow much is it?|多少钱")
    assert len(corpus) == 2
    assert corpus[0].gloss == "请给我来杯咖啡"
    hits = match_rule("Hi! I'd like a coffee, please. Thanks!", corpus)
    assert hits == ["I'd like a coffee, please."]


def test_corpus_case_punctuation_insensitive():
    corpus = parse_corpus("Can I have a cappuccino?|能给我一杯卡布奇诺吗？")
    hits = match_rule("sure, CAN I HAVE a cappuccino now", corpus)
    assert hits == ["Can I have a cappuccino?"]


def test_corpus_no_false_positive_for_single_word():
    corpus = parse_corpus("it|它")
    assert match_rule("it is raining", corpus) == []


# ---------------------------------------------------------------------------
# META 提取
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

    state = SessionState(session_id=7, kind="dialog")
    await store.put(state)
    assert (await store.get(7)) is not None
    # 手动过期
    store._data[7] = (state, time.time() - 1)
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
def _seed_completed_placement(user_id: int) -> None:
    """D1：给测试用户补一条 completed 定档（否则 /sessions 40303 拦截）。"""
    from datetime import UTC, datetime

    from app.db import get_session_factory
    from app.models import Placement

    db = get_session_factory()()
    try:
        db.add(
            Placement(
                user_id=user_id,
                status="completed",
                completed_at=datetime.now(UTC),
                level="L2",
                exam_revision=1,
            )
        )
        db.commit()
    finally:
        db.close()


def test_full_dialog_turn_sse_flow(client, auth_headers):
    # D1：先完成一次定档，否则 /sessions 40303 拦截（见 _seed_completed_placement）
    _seed_completed_placement(1)
    # 预置场景（直接走 DB 建一条 Published 场景）
    from app.db import get_session_factory
    from app.models import Scenario

    db = get_session_factory()()
    scenario = Scenario(
        title="测试咖啡馆",
        scene_type="cafe",
        difficulty=1,
        system_prompt="You are Bella, a friendly barista. Keep sentences short.",
        opening_line="Hi there! Welcome to Moonbean.",
        target_corpus="I'd like a coffee, please.|请给我来杯咖啡\nHow much is it?|多少钱",
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
    session_id = resp.json()["data"]["id"]

    # 回合 1（正常录音 → Fake ASR 命中语料）
    resp = client.post(
        f"/api/v1/sessions/{session_id}/turns",
        data={"action": "normal"},
        files={"audio": ("a.webm", FAKE_AUDIO, "audio/webm")},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    text = resp.text
    assert "turn_start" in text and "text_delta" in text
    assert "coach_note" in text or "meta_block" in text
    assert "corpus_hits" in text
    assert "turn_end" in text
    # 事件全部可解析
    for line in text.splitlines():
        if line.startswith("data: "):
            ev = json.loads(line[6:])
            assert "type" in ev

    # 回合 2：8 轮上限内的 continue；直接 simulate conclude via turn counter? 此处仅验状态推进
    resp2 = client.post(
        f"/api/v1/sessions/{session_id}/turns",
        data={"action": "normal"},
        files={"audio": ("a.webm", FAKE_AUDIO, "audio/webm")},
        headers=auth_headers,
    )
    assert resp2.status_code == 200 and "turn_index" in resp2.text


def test_turn_stale_expected_turn_rejected(client, auth_headers):
    _seed_completed_placement(1)  # D1
    from app.db import get_session_factory
    from app.models import Scenario

    db = get_session_factory()()
    scenario = Scenario(
        title="T2",
        scene_type="cafe",
        difficulty=1,
        system_prompt="x",
        opening_line="hi",
        target_corpus="a|A",
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
    session_id = resp.json()["data"]["id"]
    resp = client.post(
        f"/api/v1/sessions/{session_id}/turns",
        data={"action": "normal", "expected_turn": "99"},  # 过期轮次
        files={"audio": ("a.webm", FAKE_AUDIO, "audio/webm")},
        headers=auth_headers,
    )
    assert resp.status_code == 409


def test_dialog_session_requires_placement(client, auth_headers):
    """D1：未完成定档（无 completed placement）→ POST /sessions 403 + 40303。"""
    from app.db import get_session_factory
    from app.models import Scenario

    db = get_session_factory()()
    scenario = Scenario(
        title="T-no-placement",
        scene_type="cafe",
        difficulty=1,
        system_prompt="x",
        opening_line="hi",
        target_corpus="a|A",
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
    assert resp.status_code == 403, resp.text
    assert resp.json()["code"] == 40303


def test_fluency_features_flow_into_attempt_and_report(client, auth_headers):
    """集成：对话回合（Fake ASR 词级时间戳）→ attempts.wpm/details.fluency → 报告透出。

    修复前 wpm 列从未写入（attempts.wpm 恒 NULL），流利度时间戳特征无处呈现。
    Fake 词表含 1.05s 停顿：wpm=145.83 / pause_count=1 / long_pause_count=1。
    """
    _seed_completed_placement(1)  # D1：40303 门禁要求先定档
    from app.db import get_session_factory
    from app.models import Attempt, Scenario
    from sqlalchemy import select

    db = get_session_factory()()
    scenario = Scenario(
        title="流利度特征测试",
        scene_type="cafe",
        difficulty=1,
        system_prompt="You are Bella, a friendly barista.",
        opening_line="Hi there!",
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
    session_id = resp.json()["data"]["id"]
    resp = client.post(
        f"/api/v1/sessions/{session_id}/turns",
        data={"action": "normal"},
        files={"audio": ("a.webm", FAKE_AUDIO, "audio/webm")},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    # ③ 语义子分经 Fake META（stream_rich render_meta content/vocab）透出到 SSE
    assert '"content": {"score": 88' in resp.text
    assert '"vocab": {"score": 84' in resp.text

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

    resp = client.post(f"/api/v1/sessions/{session_id}/complete", headers=auth_headers)
    assert resp.status_code == 200
    report_id = resp.json()["data"]["report_id"]
    resp = client.get(f"/api/v1/reports/{report_id}", headers=auth_headers)
    assert resp.status_code == 200
    attempts = resp.json()["data"]["metrics"]["attempts"]
    assert attempts[0]["wpm"] == 145.83
    assert attempts[0]["fluency_features"]["pause_count"] == 1
    assert attempts[0]["fluency_features"]["wpm"] == 145.83
    # ③ 报告语义子分聚合（Fake META：content 88 / vocab 84，1 轮）
    semantic = resp.json()["data"]["metrics"]["semantic"]
    assert semantic == {
        "content": {"score": 88.0, "turns": 1},
        "vocab": {"score": 84.0, "turns": 1},
    }


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


def test_event_types_all_10_insertable(client, auth_headers):
    """docs/06 §9.1：10 类事件逐类可落库（防常量/CHECK 漂移）。"""
    import time

    from app.models.base import EventTypes

    allowed = {v for k, v in vars(EventTypes).items() if k.isupper() and not k.startswith("__")}
    assert len(allowed) == 10, f"事件类应有 10 个：{allowed}"
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
    resp = client.post(
        "/api/v1/sessions/1/turns",
        data={"action": "normal"},
        files={"audio": ("a.webm", FAKE_AUDIO, "audio/webm")},
        headers=auth_headers,
    )
    # 会话预检先于限流？依赖顺序先跑 → 429
    assert resp.status_code == 429


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
    """对话回合同样挡空录音：否则会推进 current_turn 且不可重来。"""
    resp = client.post(
        "/api/v1/sessions/999999/turns",
        data={"action": "normal"},
        files={"audio": ("a.webm", b"\x1aE\xdf\xa3", "audio/webm")},
        headers=auth_headers,
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["code"] == 40002


def test_stub_pipeline_endpoints_keep_no_lower_bound(client, auth_headers):
    """/asr /score 保持 min_bytes=0 的历史行为（P0-6 起需鉴权+限流，但不下界拦截小音频）。"""
    resp = client.post(
        "/api/v1/asr",
        files={"audio": ("tiny.wav", b"RIFF__tiny__", "audio/wav")},
        data={"language": "en"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["code"] == 0


def test_pipeline_endpoints_require_auth(client):
    """P0-6：/asr /score /tts /llm/chat 无 token → 401（修复前 200，修复后 401）。"""
    for path in ("/api/v1/asr", "/api/v1/score", "/api/v1/tts", "/api/v1/llm/chat"):
        resp = client.post(path)
        assert resp.status_code == 401, f"{path} 应 401，实际 {resp.status_code}"


def test_idor_cross_user_session_ops(client, auth_headers):
    """P0-3/P0-4/P0-5：跨用户对会话发回合/收尾/读报告 → 403（修复前 200）。"""
    _seed_completed_placement(1)  # user 1 定档（40303 门禁）
    from app.db import get_session_factory
    from app.models import Scenario

    db = get_session_factory()()
    scenario = Scenario(
        title="IDOR",
        scene_type="cafe",
        difficulty=1,
        system_prompt="x",
        opening_line="hi",
        target_corpus="a|A",
        interest_tags=[],
        status="published",
    )
    db.add(scenario)
    db.commit()
    sid = scenario.id
    db.close()
    h1 = {"X-Test-User-Id": "1"}
    h2 = {"X-Test-User-Id": "2"}
    session_id = client.post(
        "/api/v1/sessions", json={"kind": "dialog", "scenario_id": sid}, headers=h1
    ).json()["data"]["id"]

    # user 2 发回合 → 403
    turn = client.post(
        f"/api/v1/sessions/{session_id}/turns",
        data={"action": "normal"},
        files={"audio": ("a.webm", b"\x1aE\xdf\xa3\xa3" + b"\x00" * 4096, "audio/webm")},
        headers=h2,
    )
    assert turn.status_code == 403, turn.text

    # user 2 收尾 → 403
    c2 = client.post(f"/api/v1/sessions/{session_id}/complete", headers=h2)
    assert c2.status_code == 403, c2.text

    # user 1 收尾 → 200（拿到 report_id）
    c1 = client.post(f"/api/v1/sessions/{session_id}/complete", headers=h1)
    assert c1.status_code == 200, c1.text
    report_id = c1.json()["data"]["report_id"]

    # user 2 读报告 → 403；user 1 读 → 200
    gr2 = client.get(f"/api/v1/reports/{report_id}", headers=h2)
    assert gr2.status_code == 403, gr2.text
    gr1 = client.get(f"/api/v1/reports/{report_id}", headers=h1)
    assert gr1.status_code == 200, gr1.text


def test_production_config_rejects_default_secrets():
    """P0-1：app_env=production + 默认密钥 → Settings() 抛 ValueError（修复前不抛）。

    用 init 参数（pydantic-settings 最高优先级）绕过本地 .env/环境优先级，确定性触发 validator。
    """
    from app.core.config import Settings

    with pytest.raises(ValueError):
        Settings(
            app_env="production",
            jwt_secret="vocalverse-dev-jwt-secret-0123456789abcdef",
            service_token="change-me-internal-service-token",
        )
