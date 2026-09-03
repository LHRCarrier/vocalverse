"""影子跟读（DoD ④）：三维评分纯函数 + 编排全链路 + 联调测试台。

口径 docs/06 §9.3（2026-09-04 定）：pron=ISE accuracy；speed_match=用户 wpm vs 素材
原声 wpm（缺素材 wpm → None 不造分）；pause_score=pause_ratio 分段；overall=0.4/0.3/0.3
加权（缺失维度按剩余权重归一）。
"""

from __future__ import annotations

import pytest
from app.practice.shadow import (
    coach_note,
    pause_density_score,
    shadow_scores,
    speed_match_score,
    split_sentences,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient

FAKE_AUDIO = b"fake-audio-bytes" * 128


# ---------------------------------------------------------------------------
# 纯函数
# ---------------------------------------------------------------------------
def test_split_sentences_lines_and_blanks():
    assert split_sentences("Hello.\n\nHow are you?\n  ") == ["Hello.", "How are you?"]
    assert split_sentences("Single line.") == ["Single line."]
    assert split_sentences("") == []
    assert split_sentences(None) == []


@pytest.mark.parametrize(
    ("user", "ref", "expected"),
    [
        (145, 145, 95.0),  # 0% 偏差
        (150, 145, 95.0),  # 3.4% ≤10%
        (170, 145, 85.0),  # 17.2% ≤20%
        (185, 145, 70.0),  # 27.6% ≤35%
        (210, 145, 55.0),  # 44.8% ≤50%
        (250, 145, 40.0),  # 72% >50%
        (None, 145, None),  # 无用户 wpm（ASR 无时间戳）
        (145, 0, None),  # 素材 wpm 非法
    ],
)
def test_speed_match_score_bands(user, ref, expected):
    assert speed_match_score(user, ref) == expected


@pytest.mark.parametrize(
    ("ratio", "expected"),
    [
        (0.02, 95.0),
        (0.10, 85.0),  # 边界 → ≤10% 档
        (0.15, 70.0),
        (0.35, 55.0),  # 边界 → ≤35% 档
        (0.50, 40.0),
        (None, None),
    ],
)
def test_pause_density_score_bands(ratio, expected):
    assert pause_density_score(ratio) == expected


def test_shadow_scores_missing_speed_dimension_renormalizes():
    """素材缺 wpm → speed=None；overall 按 pron/pause 权重归一（0.4/0.6）。"""
    sc = shadow_scores(60.0, 120.0, None, 0.05)
    assert sc.speed_match is None
    assert sc.pause_score == 95.0
    assert sc.overall == round((0.4 * 60 + 0.3 * 95) / 0.7)  # 72.14 → 72


def test_shadow_scores_all_missing():
    sc = shadow_scores(None, None, None, None)
    assert sc.overall is None
    assert coach_note(sc) is None


def test_coach_note_bands():
    sc = shadow_scores(95.0, 145.0, 145, 0.02)  # 全优 → 高段
    assert "Great" in (coach_note(sc) or "")
    sc2 = shadow_scores(50.0, 330.0, 145, 0.50)  # 三维全低 → 低段提示逐句慢练
    assert "Slow down" in (coach_note(sc2) or "")
    sc3 = shadow_scores(85.0, 210.0, 145, 0.50)  # 中段 → 具体给出短板
    note = coach_note(sc3) or ""
    assert "pausing" in note and "Keep practicing" in note


# ---------------------------------------------------------------------------
# 编排全链路（Fake clients，经由 API）
# ---------------------------------------------------------------------------
def _seed_material(
    sentences: str = "Hi, could I get a large flat white to go, please?\n"
    "Thanks for having me. Let me briefly walk you through my background.",
    wpm: int = 145,
) -> int:
    from app.db import get_session_factory
    from app.models import ShadowMaterial

    db = get_session_factory()()
    material = ShadowMaterial(
        title="测试跟读素材",
        level=2,
        text_content=sentences,
        audio_url="/demo/audio/shadow/test.mp3",
        wpm=wpm,
        duration_s=10,
        interest_tags=[],
        source="demo_only",
        status="published",
    )
    db.add(material)
    db.commit()
    mid = material.id
    db.close()
    return mid


def test_shadow_session_flow(client, auth_headers):
    """start（出句+示范）→ normal（跟读评分）→ 收尾报告；attempt 三维落库。"""
    mid = _seed_material()
    resp = client.post(
        "/api/v1/sessions",
        json={"kind": "shadow", "shadow_material_id": mid},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    sid = resp.json()["data"]["id"]
    assert resp.json()["data"]["shadow_material_id"] == mid

    # start：出句 + 示范 AudioChunk + TurnEnd(pending)
    resp = client.post(
        f"/api/v1/sessions/{sid}/turns",
        data={"action": "start"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert '"reference_text": "Hi, could I get a large flat white to go, please?"' in resp.text
    assert "audio_chunk" in resp.text
    assert '"score_status": "pending"' in resp.text

    # 第 1 句跟读（Fake ASR wpm=145.83 / pause_ratio=0.3646；ISE pron=90）
    resp = client.post(
        f"/api/v1/sessions/{sid}/turns",
        data={"action": "normal"},
        files={"audio": ("a.webm", FAKE_AUDIO, "audio/webm")},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert "meta_block" in resp.text and "score_delta" in resp.text
    assert '"conclude": false' in resp.text

    # 第 2 句（末句）→ SessionEnd + report
    resp = client.post(
        f"/api/v1/sessions/{sid}/turns",
        data={"action": "normal"},
        files={"audio": ("a.webm", FAKE_AUDIO, "audio/webm")},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert "session_end" in resp.text

    import json

    report_id = None
    for line in resp.text.splitlines():
        if line.startswith("data: "):
            ev = json.loads(line[6:])
            if ev.get("type") == "session_end":
                report_id = ev.get("report_id")
    assert report_id is not None

    # attempt 落库断言（Fake 数值：wpm=145.83 → speed 95；pause 0.3646 → 40；pron 90）
    from app.db import get_session_factory
    from app.models import Attempt
    from sqlalchemy import select

    db = get_session_factory()()
    try:
        attempts = list(db.execute(select(Attempt).where(Attempt.session_id == sid)).scalars())
        assert len(attempts) == 2
        a = attempts[0]
        assert a.kind == "shadow_speech"
        assert float(a.wpm) == 145.83
        shadow = (a.details or {}).get("shadow")
        assert shadow["speed_match"] == 95.0
        assert shadow["pause_score"] == 40.0
        assert shadow["pron"] == 90.0
        # overall = 0.4*90 + 0.3*95 + 0.3*40 = 76.5 → 76（banker's）
        assert shadow["overall"] == 76
    finally:
        db.close()

    # 报告透出
    resp = client.get(f"/api/v1/reports/{report_id}", headers=auth_headers)
    assert resp.status_code == 200
    attempts = resp.json()["data"]["metrics"]["attempts"]
    assert len(attempts) == 2
    assert attempts[0]["wpm"] == 145.83
    assert attempts[0]["fluency_features"]["pause_count"] == 1
    assert attempts[0]["details"]["shadow"]["overall"] == 76


def test_shadow_session_unknown_material_404(client, auth_headers):
    resp = client.post(
        "/api/v1/sessions",
        json={"kind": "shadow", "shadow_material_id": 999999},
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_shadow_turn_requires_audio_for_record(client, auth_headers):
    mid = _seed_material(sentences="Hi there.")
    resp = client.post(
        "/api/v1/sessions",
        json={"kind": "shadow", "shadow_material_id": mid},
        headers=auth_headers,
    )
    sid = resp.json()["data"]["id"]
    resp = client.post(
        f"/api/v1/sessions/{sid}/turns",
        data={"action": "normal"},
        headers=auth_headers,
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 联调测试台（test-only）
# ---------------------------------------------------------------------------
def test_shadow_preview_disabled_returns_404(client):
    r = client.get("/api/v1/shadow-preview/materials")
    assert r.status_code == 404
    assert "/api/v1/shadow-preview" not in client.get("/openapi.json").json()["paths"]


def _mounted_client() -> TestClient:
    from app.api.routes.shadow_preview import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_shadow_preview_materials_and_analyze(client, auth_headers):
    """联调台：素材列表（含句数）+ 跟读分析（Fake 三维分与 ISO 词典同构）。"""
    mid = _seed_material()
    c = _mounted_client()
    r = c.get("/api/v1/shadow-preview/materials")
    assert r.status_code == 200
    items = r.json()["data"]
    assert any(i["id"] == mid and i["sentence_count"] == 2 for i in items)

    r = c.post(
        "/api/v1/shadow-preview/analyze",
        files={"audio": ("a.webm", FAKE_AUDIO, "audio/webm")},
        data={"material_id": str(mid), "sentence_index": "0"},
    )
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["sentence"] == "Hi, could I get a large flat white to go, please?"
    assert d["shadow"]["pron"] == 90.0
    assert d["shadow"]["speed_match"] == 95.0
    assert d["ise"] is not None and d["ise"]["pron"] == 90.0


def test_shadow_preview_analyze_bad_index(client):
    mid = _seed_material(sentences="Only one.")
    c = _mounted_client()
    r = c.post(
        "/api/v1/shadow-preview/analyze",
        files={"audio": ("a.webm", FAKE_AUDIO, "audio/webm")},
        data={"material_id": str(mid), "sentence_index": "5"},
    )
    assert r.status_code == 422
