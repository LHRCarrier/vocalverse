"""M3 P4：学习画像聚合（学习主页 + 模块详情）——docs/53 §1 P4 DoD。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.db import get_session_factory
from app.models.analytics import Event
from app.models.base import SessionKinds
from app.models.practice import Attempt, Score
from app.models.practice import Session as PracticeSession
from app.models.reading import UserVocabulary
from app.models.trpg import TrpgCampaign, TrpgMessage
from app.models.user import User, UserProfile


def _user() -> int:
    db = get_session_factory()()
    try:
        user = User(username="learn_u", nickname="l", password_hash="x")
        db.add(user)
        db.flush()
        db.add(UserProfile(user_id=user.id, age_group="adult", cefr_level="L3"))
        db.commit()
        return int(user.id)
    finally:
        db.close()


def _seed(user_id: int) -> None:
    now = datetime.now(UTC)
    db = get_session_factory()()
    try:
        # 事件（热力图 + 社区足迹）
        for i in range(3):
            db.add(
                Event(
                    user_id=user_id,
                    event_type="page_view",
                    occurred_at=now - timedelta(days=i),
                    page="/m/home",
                    channel="web",
                    payload={},
                )
            )
        db.add(
            Event(
                user_id=user_id,
                event_type="word_lookup",
                occurred_at=now - timedelta(days=1),
                page="/m/reader/1",
                channel="web",
                payload={"word": "coffee"},
            )
        )
        # 口语 attempts（含音素错误）
        a1 = Attempt(
            user_id=user_id,
            kind="defense_answer",
            pron_score=70,
            flu_score=60,
            gram_score=65,
            overall_score=65,
            created_at=now - timedelta(days=10),
        )
        a2 = Attempt(
            user_id=user_id,
            kind="defense_answer",
            pron_score=85,
            flu_score=80,
            gram_score=78,
            overall_score=82,
            created_at=now - timedelta(days=1),
        )
        db.add_all([a1, a2])
        db.flush()
        db.add(
            Score(
                attempt_id=a2.id,
                word_index=0,
                phoneme="th",
                score=55,
                error_type="mispronunciation",
            )
        )
        # 会话（练习分钟）
        db.add(
            PracticeSession(
                user_id=user_id,
                kind=SessionKinds.SING,
                status="completed",
                duration_s=300,
            )
        )
        # 生词本
        db.add(UserVocabulary(user_id=user_id, word="coffee", status="learning", scene="reading"))
        db.add(UserVocabulary(user_id=user_id, word="lighthouse", status="new", scene="reading"))
        # 酒馆剧本 + 回合
        camp = TrpgCampaign(user_id=user_id, name="迷雾酒馆")
        db.add(camp)
        db.flush()
        db.add(TrpgMessage(campaign_id=camp.id, role="user", content="我观察四周"))
        db.add(TrpgMessage(campaign_id=camp.id, role="assistant", content="你看到吧台"))
        db.commit()
    finally:
        db.close()


def test_learn_overview_aggregates_real_data(client, auth_headers):
    user_id = _user()
    _seed(user_id)
    r = client.get("/api/v1/stats/learn", headers=auth_headers)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert "练了" in data["profile_line"] and "2 次" in data["profile_line"]
    assert data["heatmap"], "热力图应有数据"
    assert any(c["count"] >= 1 for c in data["heatmap"])
    m = data["modules"]
    assert m["words"]["total"] == 2 and m["words"]["learning"] == 1
    assert m["speaking"]["pron"] == 77.5 and m["speaking"]["flu"] == 70.0
    assert m["practice"]["campaigns"] == 1 and m["practice"]["minutes"] == 5
    assert "社区" not in m["community"]["summary"] or m["community"]["events"] >= 3
    assert "forecast" in data  # 学习主页进步趋势（docs/06 §9.5）


def test_learn_overview_empty_state(client, auth_headers):
    _user()
    data = client.get("/api/v1/stats/learn", headers=auth_headers).json()["data"]
    assert "还没有练习记录" in data["profile_line"]
    assert data["heatmap"] == []
    assert data["modules"]["words"]["total"] == 0
    assert data["modules"]["speaking"]["pron"] is None


def test_learn_module_speaking_and_practice(client, auth_headers):
    user_id = _user()
    _seed(user_id)
    sp = client.get("/api/v1/stats/learn/speaking", headers=auth_headers).json()["data"]
    assert sp["dims"]["pron"] == 77.5
    assert len(sp["trend"]) == 2
    assert sp["weak_phonemes"] == [{"phoneme": "th", "count": 1, "avg": 55.0}]

    pr = client.get("/api/v1/stats/learn/practice", headers=auth_headers).json()["data"]
    assert pr["minutes"] == 5
    assert pr["campaigns"][0]["name"] == "迷雾酒馆" and pr["campaigns"][0]["user_turns"] == 1
    assert pr["heatmap"]


def test_learn_module_words_and_community(client, auth_headers):
    user_id = _user()
    _seed(user_id)
    words = client.get("/api/v1/stats/learn/words", headers=auth_headers).json()["data"]["items"]
    assert {w["word"] for w in words} == {"coffee", "lighthouse"}
    community = client.get("/api/v1/stats/learn/community", headers=auth_headers).json()["data"]
    assert community["pages"][0]["page"] == "/m/home"
    assert any(e["event_type"] == "word_lookup" for e in community["events"])


def test_learn_module_unknown_key(client, auth_headers):
    _user()
    r = client.get("/api/v1/stats/learn/hack", headers=auth_headers)
    assert r.status_code == 400
