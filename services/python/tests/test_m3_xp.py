"""M3 P5：XP 后端聚合（docs/53 §1 P5 DoD ③）——经验/等级由服务端从事实表计算。

规则见 ``app/insight/xp.py``：attempt +15 / sing_attempt +15 / free_chat_turn +5 /
practice_complete +15；等级表 LV1~LV5 服务端为唯一真源。
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.db import get_session_factory
from app.models.analytics import Event
from app.models.content import Song
from app.models.practice import Attempt, SingAttempt
from app.models.user import User


def _user() -> int:
    db = get_session_factory()()
    try:
        user = User(username="xp_u", nickname="x", password_hash="x")
        db.add(user)
        db.commit()
        return int(user.id)
    finally:
        db.close()


def _event(user_id: int, event_type: str) -> None:
    db = get_session_factory()()
    try:
        db.add(
            Event(
                user_id=user_id,
                event_type=event_type,
                occurred_at=datetime.now(UTC),
                channel="web",
                payload={},
            )
        )
        db.commit()
    finally:
        db.close()


def _seed(user_id: int) -> None:
    db = get_session_factory()()
    try:
        db.add(
            Attempt(
                user_id=user_id,
                kind="defense_answer",
                pron_score=70,
                flu_score=60,
                gram_score=65,
                overall_score=65,
            )
        )
        db.add(
            Attempt(
                user_id=user_id,
                kind="shadow_speech",
                pron_score=80,
                flu_score=75,
                gram_score=78,
                overall_score=78,
            )
        )
        song = Song(title="XP Demo", level=1, audio_url="/api/v1/audio/demo.mp3")
        db.add(song)
        db.flush()
        db.add(SingAttempt(user_id=user_id, song_id=song.id, duration_s=120))
        db.commit()
    finally:
        db.close()
    for _ in range(3):
        _event(user_id, "free_chat_turn")
    _event(user_id, "practice_complete")
    _event(user_id, "page_view")  # 未列入 XP 规则的事件不计分


def test_xp_summary_aggregates_facts(client, auth_headers):
    user_id = _user()
    _seed(user_id)
    r = client.get("/api/v1/stats/progress", headers=auth_headers)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    # 2*15 + 1*15 + 3*5 + 1*15 = 75 → LV1
    assert data["xp"] == 75
    assert data["level"] == 1 and data["title"] == "英语新手"
    assert data["base"] == 0 and data["next"] == 100
    assert data["breakdown"] == {
        "attempt": 2,
        "sing_attempt": 1,
        "free_chat_turn": 3,
        "practice_complete": 1,
    }
    assert {r_["key"]: r_["xp"] for r_ in data["rules"]} == {
        "attempt": 15,
        "sing_attempt": 15,
        "free_chat_turn": 5,
        "practice_complete": 15,
    }


def test_xp_summary_empty_and_level_boundary(client, auth_headers):
    user_id = _user()
    empty = client.get("/api/v1/stats/progress", headers=auth_headers).json()["data"]
    assert empty["xp"] == 0 and empty["level"] == 1

    db = get_session_factory()()
    try:
        for _ in range(7):  # 7*15 = 105 → LV2 口语学徒（100~249）
            db.add(
                Attempt(
                    user_id=user_id,
                    kind="defense_answer",
                    pron_score=80,
                    flu_score=80,
                    gram_score=80,
                    overall_score=80,
                )
            )
        db.commit()
    finally:
        db.close()
    data = client.get("/api/v1/stats/progress", headers=auth_headers).json()["data"]
    assert data["xp"] == 105
    assert data["level"] == 2 and data["title"] == "口语学徒"
    assert data["base"] == 100 and data["next"] == 250
