"""M3 P3：内容型推荐（歌/书/场景卡）+ 水平预测（docs/53 §1 P3 DoD）。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app.db import get_session_factory
from app.models.analytics import Event
from app.models.content import Song
from app.models.practice import Attempt
from app.models.reading import Book
from app.models.trpg import TrpgScenarioCard
from app.models.user import User, UserProfile
from sqlalchemy import select


def _user(tags: list[str] | None = None, level: str = "L3") -> int:
    db = get_session_factory()()
    try:
        user = User(username="reco_u", nickname="r", password_hash="x")
        db.add(user)
        db.flush()
        db.add(
            UserProfile(
                user_id=user.id,
                age_group="adult",
                cefr_level=level,
                interest_tags=tags or ["space", "music"],
            )
        )
        db.commit()
        return int(user.id)
    finally:
        db.close()


def _seed_content() -> None:
    db = get_session_factory()()
    try:
        db.add_all(
            [
                Song(
                    title="Space Song", artist="A", level=3, status="published", audio_url="/a.mp3"
                ),
                Song(
                    title="Easy Tune", artist="B", level=1, status="published", audio_url="/b.mp3"
                ),
                Book(title="Space Odyssey", author="C", level="L3", status="published"),
                TrpgScenarioCard(title="星港夜航", summary="太空港口的谜案", status="published"),
            ]
        )
        db.commit()
    finally:
        db.close()


def test_recommend_items_returns_ranked_and_writes_impression(client, auth_headers):
    _user()
    _seed_content()
    r = client.get("/api/v1/recommendations?type=items&limit=3", headers=auth_headers)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["type"] == "items" and data["level"] == "L3"
    assert len(data["items"]) == 3
    kinds = {it["kind"] for it in data["items"]}
    assert kinds == {"song", "book", "card"}
    # 水平匹配：L3 歌曲应排在 L1 歌曲之前（同为 song 类时）
    r_song = client.get("/api/v1/recommendations?type=items&kind=song", headers=auth_headers)
    songs = r_song.json()["data"]["items"]
    assert songs[0]["title"] == "Space Song" and songs[0]["level"] == "L3"
    assert songs[0]["reason"]

    # 曝光埋点（recommend_impression + recommend_group_id，CTR 的曝光分母）
    db = get_session_factory()()
    try:
        rows = list(
            db.execute(select(Event).where(Event.event_type == "recommend_impression")).scalars()
        )
    finally:
        db.close()
    assert rows, "推荐曝光未落库"
    hit = [e for e in rows if e.recommend_group_id == data["recommend_group_id"]]
    assert hit and hit[0].payload.get("content_type") == "items"


def test_recommend_items_kind_filter(client, auth_headers):
    _user()
    _seed_content()
    r = client.get("/api/v1/recommendations?type=items&kind=book", headers=auth_headers)
    items = r.json()["data"]["items"]
    assert len(items) == 1 and items[0]["kind"] == "book" and items[0]["title"] == "Space Odyssey"


def test_level_forecast_in_stats_me(client, auth_headers, tmp_path, monkeypatch):
    from app.core.config import get_settings
    from app.rec import level_model

    monkeypatch.setattr(get_settings(), "level_model_path", str(tmp_path / "model.joblib"))
    level_model._MODEL = None

    user_id = _user()
    # 无数据 → 空态（不伪造）
    empty = client.get("/api/v1/stats/me", headers=auth_headers).json()["data"]["forecast"]
    assert empty["available"] is False

    db = get_session_factory()()
    try:
        now = datetime.now(UTC)
        for i, score in enumerate([60, 66, 72, 80]):
            db.add(
                Attempt(
                    user_id=user_id,
                    kind="defense_answer",
                    overall_score=score,
                    created_at=now - timedelta(days=3 - i),
                )
            )
        db.commit()
    finally:
        db.close()

    data = client.get("/api/v1/stats/me", headers=auth_headers).json()["data"]
    fc = data["forecast"]
    assert fc["available"] is True and fc["direction"] == "up"
    assert fc["predicted_overall"] >= fc["current_avg"]
    assert fc["basis"]["attempts"] == 4
    assert (tmp_path / "model.joblib").exists(), "joblib 未持久化（训练一次 + 启动加载）"


def test_recommend_items_empty_pool_ok(client, auth_headers):
    """候选池为空时不报错（曝光埋点不写，返回空列表）。"""
    _user()
    r = client.get("/api/v1/recommendations?type=items", headers=auth_headers)
    assert r.status_code == 200 and r.json()["data"]["items"] == []


@pytest.mark.parametrize("bad", ["hack", "scenes"])
def test_recommend_type_whitelist(client, auth_headers, bad):
    r = client.get(f"/api/v1/recommendations?type={bad}", headers=auth_headers)
    assert r.status_code == 422
