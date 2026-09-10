"""跟唱收藏端点测试（song_favorites · 2026-09-10）。

覆盖（组长需求：收藏必须由用户自主选择，每首歌一个按钮，再点取消）：
- 收藏/取消往返：PUT → favorited=true，DELETE → favorited=false（列表与详情两侧同步）；
- **幂等**：重复收藏只有一行、重复取消不报错（弱网重试/双击不得翻转状态或 5xx）；
- 用户隔离：他人收藏不出现在我的列表，我取消收藏不影响他人；
- 门禁：歌曲不存在/未发布 → 40401；未带令牌 → 401；
- 约束：`uq_song_favorites_user_song` 唯一键在 metadata 层存在（防被误删）。

**修复前必失败证据**：本文件引用的 `favorited` 字段与 PUT/DELETE `/songs/{id}/favorite`
在改动前均不存在（PUT/DELETE 命中 404/405，`favorited` 取值为 None）。
"""

from __future__ import annotations

import uuid

from app.models import Song, SongFavorite, User
from app.models.base import ContentStatus, PitchRefStatus


def _new_db():
    from app.db import get_session_factory

    return get_session_factory()()


def _seed_user(db, uid: int | None = None) -> int:
    user = User(
        username=f"fav_{uuid.uuid4().hex[:10]}",
        email=None,
        password_hash="x",
        nickname="U",
    )
    if uid is not None:
        user.id = uid
    db.add(user)
    db.flush()
    user_id = int(user.id)
    db.commit()
    return user_id


def _seed_song(db, *, status: str = ContentStatus.PUBLISHED) -> int:
    song = Song(
        title="Twinkle",
        level=1,
        audio_url="/data/audio/twinkle.wav",
        status=status,
        pitch_ref_status=PitchRefStatus.READY,
    )
    db.add(song)
    db.flush()
    song_id = int(song.id)
    db.commit()
    return song_id


def _headers(uid: int) -> dict[str, str]:
    return {"X-Test-User-Id": str(uid)}


def _fav_rows(user_id: int, song_id: int) -> int:
    db = _new_db()
    try:
        from sqlalchemy import func, select

        return int(
            db.execute(
                select(func.count())
                .select_from(SongFavorite)
                .where(SongFavorite.user_id == user_id, SongFavorite.song_id == song_id)
            ).scalar_one()
        )
    finally:
        db.close()


def _song_row(client, song_id: int, uid: int) -> dict:
    resp = client.get("/api/v1/songs", headers=_headers(uid))
    assert resp.status_code == 200
    return next(s for s in resp.json()["data"] if s["id"] == song_id)


def test_favorite_toggle_roundtrip(client):
    """收藏 → 列表/详情 favorited=true；取消 → false（同一首歌，不删歌曲）。"""
    db = _new_db()
    try:
        uid = _seed_user(db)
        song_id = _seed_song(db)
    finally:
        db.close()

    resp = client.put(f"/api/v1/songs/{song_id}/favorite", headers=_headers(uid))
    assert resp.status_code == 200
    assert resp.json()["data"] == {"song_id": song_id, "favorited": True}
    assert _song_row(client, song_id, uid)["favorited"] is True
    detail = client.get(f"/api/v1/songs/{song_id}", headers=_headers(uid)).json()["data"]
    assert detail["favorited"] is True
    assert _fav_rows(uid, song_id) == 1

    resp = client.delete(f"/api/v1/songs/{song_id}/favorite", headers=_headers(uid))
    assert resp.status_code == 200
    assert resp.json()["data"] == {"song_id": song_id, "favorited": False}
    assert _song_row(client, song_id, uid)["favorited"] is False
    detail = client.get(f"/api/v1/songs/{song_id}", headers=_headers(uid)).json()["data"]
    assert detail["favorited"] is False
    assert _fav_rows(uid, song_id) == 0


def test_favorite_is_idempotent(client):
    """重复收藏只留一行；重复取消不报错（前端再点/重试的稳定性保证）。"""
    db = _new_db()
    try:
        uid = _seed_user(db)
        song_id = _seed_song(db)
    finally:
        db.close()

    for _ in range(3):
        assert (
            client.put(f"/api/v1/songs/{song_id}/favorite", headers=_headers(uid)).status_code
            == 200
        )
    assert _fav_rows(uid, song_id) == 1

    for _ in range(3):
        assert (
            client.delete(f"/api/v1/songs/{song_id}/favorite", headers=_headers(uid)).status_code
            == 200
        )
    assert _fav_rows(uid, song_id) == 0


def test_favorite_isolated_between_users(client):
    """收藏按用户隔离：他人收藏不串号，取消只影响自己。"""
    db = _new_db()
    try:
        uid1 = _seed_user(db)
        uid2 = _seed_user(db)
        song_id = _seed_song(db)
    finally:
        db.close()

    client.put(f"/api/v1/songs/{song_id}/favorite", headers=_headers(uid1))
    assert _song_row(client, song_id, uid1)["favorited"] is True
    assert _song_row(client, song_id, uid2)["favorited"] is False

    # 用户 2 取消（本就没收藏）不影响用户 1
    client.delete(f"/api/v1/songs/{song_id}/favorite", headers=_headers(uid2))
    assert _song_row(client, song_id, uid1)["favorited"] is True
    assert _fav_rows(uid1, song_id) == 1
    assert _fav_rows(uid2, song_id) == 0


def test_favorite_unknown_song_404(client):
    """不存在的歌曲 → 40401（不写入幽灵收藏行）。"""
    db = _new_db()
    try:
        uid = _seed_user(db)
    finally:
        db.close()

    resp = client.put("/api/v1/songs/999999/favorite", headers=_headers(uid))
    assert resp.status_code == 404
    assert resp.json()["code"] == 40401
    resp = client.delete("/api/v1/songs/999999/favorite", headers=_headers(uid))
    assert resp.status_code == 404
    assert resp.json()["code"] == 40401


def test_favorite_unpublished_song_404(client):
    """未发布（draft/archived）歌曲不可收藏——与 GET /songs/{id} 同口径。"""
    db = _new_db()
    try:
        uid = _seed_user(db)
        song_id = _seed_song(db, status=ContentStatus.DRAFT)
    finally:
        db.close()

    resp = client.put(f"/api/v1/songs/{song_id}/favorite", headers=_headers(uid))
    assert resp.status_code == 404
    assert resp.json()["code"] == 40401
    assert _fav_rows(uid, song_id) == 0


def test_favorite_requires_bearer(client):
    """无令牌 → 401（收藏是用户数据，不可匿名写）。"""
    db = _new_db()
    try:
        song_id = _seed_song(db)
    finally:
        db.close()

    assert client.put(f"/api/v1/songs/{song_id}/favorite").status_code == 401
    assert client.delete(f"/api/v1/songs/{song_id}/favorite").status_code == 401


def test_song_favorites_unique_constraint_declared():
    """唯一键 (user_id, song_id) 必须在 metadata（幂等语义的地基，防误删）。"""
    names = {c.name for c in SongFavorite.__table__.constraints}
    assert "uq_song_favorites_user_song" in names
