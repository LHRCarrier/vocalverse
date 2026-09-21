"""M3 指标聚合（docs/53 P2）：四指标 / 个人报表 / 控制台看板端点。

口径见 ``app/insight/service.py``（docs/06 §9.1 修订：参与会话 = >10s 或 关键事件 或 ≥2 pageview）。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.db import get_session_factory
from app.models.analytics import Event
from app.models.base import SessionKinds, SessionStatus
from app.models.content import Song
from app.models.practice import Attempt, Session as PracticeSession, SingAttempt
from app.models.trpg import TrpgCampaign, TrpgMessage
from app.models.user import Placement, User, UserProfile
from tests.console.helpers import console_headers


def _now() -> datetime:
    return datetime.now(UTC)


def _user(level: str = "L3") -> int:
    db = get_session_factory()()
    try:
        user = User(username="insight_u", nickname="i", password_hash="x")
        db.add(user)
        db.flush()
        db.add(UserProfile(user_id=user.id, age_group="adult", cefr_level=level))
        db.commit()
        return int(user.id)
    finally:
        db.close()


def _event(**kwargs) -> None:
    db = get_session_factory()()
    try:
        kwargs.setdefault("occurred_at", _now())
        kwargs.setdefault("channel", "web")
        kwargs.setdefault("payload", {})
        db.add(Event(**kwargs))
        db.commit()
    finally:
        db.close()


def _seed_engagement(user_id: int) -> None:
    """两个浏览会话：A 含关键事件（参与）/ B 单个 page_view（跳出）。"""
    now = _now()
    _event(
        user_id=user_id,
        browse_session_id="browse-A",
        event_type="page_view",
        occurred_at=now - timedelta(minutes=5),
    )
    _event(
        user_id=user_id,
        browse_session_id="browse-A",
        event_type="word_lookup",
        occurred_at=now - timedelta(minutes=4),
    )
    _event(
        user_id=user_id,
        browse_session_id="browse-B",
        event_type="page_view",
        occurred_at=now - timedelta(minutes=3),
    )


def test_overview_four_metrics(client, auth_headers):
    user_id = _user()
    _seed_engagement(user_id)

    # CTR：曝光组 g1（+5min 点击命中）；曝光组 g2（无点击）
    now = _now()
    _event(
        user_id=user_id,
        event_type="recommend_impression",
        recommend_group_id="g1",
        occurred_at=now - timedelta(minutes=30),
    )
    _event(
        user_id=user_id,
        event_type="recommend_click",
        recommend_group_id="g1",
        occurred_at=now - timedelta(minutes=25),
    )
    _event(
        user_id=user_id,
        event_type="recommend_impression",
        recommend_group_id="g2",
        occurred_at=now - timedelta(minutes=20),
    )

    # 完成率：唱吧 1/2；酒馆 1/2（有玩家消息）；答辩 0/1；入学测试 1/1
    db = get_session_factory()()
    try:
        db.add(
            PracticeSession(user_id=user_id, kind=SessionKinds.SING, status=SessionStatus.COMPLETED)
        )
        db.add(
            PracticeSession(user_id=user_id, kind=SessionKinds.SING, status=SessionStatus.ACTIVE)
        )
        db.add(
            PracticeSession(
                user_id=user_id,
                kind=SessionKinds.DEFENSE,
                status=SessionStatus.ACTIVE,
                assigned_turns=5,
                user_turn_count=3,
            )
        )
        db.flush()
        camp = TrpgCampaign(user_id=user_id, name="迷雾酒馆")
        camp2 = TrpgCampaign(user_id=user_id, name="没开成的局")
        db.add_all([camp, camp2])
        db.flush()
        db.add(TrpgMessage(campaign_id=camp.id, role="user", content="我观察四周"))
        db.add(TrpgMessage(campaign_id=camp.id, role="assistant", content="你看到吧台"))
        db.add(TrpgMessage(campaign_id=camp.id, role="assistant", content="DM 继续叙述"))
        db.add(Placement(user_id=user_id, status="completed", completed_at=_now()))
        db.add(Placement(user_id=user_id, status="in_progress"))
        db.commit()
    finally:
        db.close()

    r = client.get("/api/v1/stats/overview?days=30", headers=auth_headers)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    m = data["metrics"]

    assert m["ctr"]["denominator"] == 2 and m["ctr"]["numerator"] == 1
    assert m["ctr"]["rate"] == 0.5
    # 完成率：sing 1/2 + trpg 1/2 + defense 0/1 + placement 1/2 = 3/7
    assert m["completion_rate"]["denominator"] == 7
    assert m["completion_rate"]["numerator"] == 3
    assert m["completion_rate"]["units"]["placement"] == {"total": 2, "done": 1}
    assert m["completion_rate"]["units"]["trpg"] == {"total": 2, "done": 1}
    # 互动率：分子 = 酒馆 user 1 + 答辩作答 3 = 4；分母 = 酒馆 user 1 + dm 2 + 答辩分配 5 = 8
    assert m["interaction_rate"]["numerator"] == 4
    assert m["interaction_rate"]["denominator"] == 8
    assert m["interaction_rate"]["rate"] == 0.5
    # 跳出率：2 会话 1 参与 → 0.5
    assert m["bounce_rate"]["denominator"] == 2
    assert m["bounce_rate"]["engaged_sessions"] == 1
    assert m["bounce_rate"]["rate"] == 0.5
    # 趋势与维度存在
    assert data["trend"] and data["trend"][0]["events"] >= 1
    assert (
        any(d["key"] == "/m/home" for d in data["dimensions"]["page"]) is False
    )  # 本用例没写 page
    assert any(d["key"] == "word_lookup" for d in data["dimensions"]["target_type"]) is False


def test_me_report_radar_and_trend(client, auth_headers):
    user_id = _user()
    db = get_session_factory()()
    try:
        yesterday = _now() - timedelta(days=1)
        db.add(
            Attempt(
                user_id=user_id,
                kind="placement_item",
                pron_score=80,
                flu_score=70,
                gram_score=60,
                overall_score=72,
                created_at=yesterday,
            )
        )
        db.add(
            Attempt(
                user_id=user_id,
                kind="defense_answer",
                pron_score=90,
                flu_score=80,
                gram_score=70,
                overall_score=82,
            )
        )
        song = Song(title="Demo Song", level=1, audio_url="/api/v1/audio/demo.mp3")
        db.add(song)
        db.flush()
        db.add(
            SingAttempt(
                user_id=user_id,
                song_id=song.id,
                duration_s=180,
                pitch_score=88,
                rhythm_score=76,
                overall_score=80,
            )
        )
        db.add(
            PracticeSession(
                user_id=user_id,
                kind=SessionKinds.SING,
                status=SessionStatus.COMPLETED,
                duration_s=180,
            )
        )
        db.commit()
    finally:
        db.close()

    r = client.get("/api/v1/stats/me?days=30", headers=auth_headers)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["summary"]["attempts"] == 2
    assert data["summary"]["sing_attempts"] == 1
    assert data["summary"]["practice_minutes"] == 3
    assert data["summary"]["best_overall"] == 82.0
    assert data["radar"]["axes"] == ["发音", "流利", "语法", "音准", "节奏"]
    assert data["radar"]["values"] == [85.0, 75.0, 65.0, 88.0, 76.0]
    assert len(data["trend"]) >= 1
    kinds = {row["kind"]: row for row in data["by_kind"]}
    assert kinds["sing"]["count"] == 1 and kinds["sing"]["avg_overall"] == 80.0


def test_console_insight_perm_and_payload(client):
    ok_headers = console_headers(perms=("ops:metric:read",))
    r = client.get("/api/v1/console/insight/overview?days=7", headers=ok_headers)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert set(data["metrics"]) == {"ctr", "completion_rate", "interaction_rate", "bounce_rate"}
    assert data["requested_by"] == "ops-admin"

    denied = client.get(
        "/api/v1/console/insight/overview", headers=console_headers(perms=("content:song:read",))
    )
    assert denied.status_code == 403 and denied.json()["code"] == 46002
