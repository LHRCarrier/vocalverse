"""M2 核心测试（docs/18 §5.1：语料/元数据/状态锁/回合全链路/答辩/音频/埋点/限流）。"""

from __future__ import annotations

import json

from app.practice.corpus import match_rule, parse_corpus
from app.practice.meta import extract_meta, render_meta
from app.practice.orchestrator import save_audio_bytes
from app.practice.service import validate_bank
from app.practice.state import StateStore


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
def test_full_dialog_turn_sse_flow(client, auth_headers):
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
        files={"audio": ("a.webm", b"fake-audio-bytes", "audio/webm")},
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
        files={"audio": ("a.webm", b"fake-audio-bytes", "audio/webm")},
        headers=auth_headers,
    )
    assert resp2.status_code == 200 and "turn_index" in resp2.text


def test_turn_stale_expected_turn_rejected(client, auth_headers):
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
        files={"audio": ("a.webm", b"fake-audio-bytes", "audio/webm")},
        headers=auth_headers,
    )
    assert resp.status_code == 409


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
        files={"audio": ("a.webm", b"fake", "audio/webm")},
        headers=auth_headers,
    )
    # 会话预检先于限流？依赖顺序先跑 → 429
    assert resp.status_code == 429
