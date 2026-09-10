"""跟唱收藏（唱吧「收藏」tab 的事实源；2026-09-10 组长需求）。

语义（docs/10 §3 / docs/21 §3.6）：
- 收藏 = ``song_favorites`` 存在 (user_id, song_id) 行；取消收藏 = 删除该行（无软删状态列）；
- **幂等**：重复收藏不报错（唯一键冲突视为已收藏）、重复取消不报错（0 行删除也算成功）——
  前端「再点一次取消」在弱网重试/双击下必须稳定，不能出现 500 或状态翻转；
- 归属：本表 Python 写；``songs`` 仍是 Java 独占写（此处只读校验「歌曲存在且已发布」）。

调用方：``app/api/routes/singing.py``（PUT/DELETE ``/api/v1/songs/{id}/favorite`` +
``GET /songs``/``GET /songs/{id}`` 的 ``favorited`` 标记），全部经 ``asyncio.to_thread``
执行（与既有路由同款的同步 DB 调用约定）。
"""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.response import BizError
from app.db import get_session_factory
from app.models import Song, SongFavorite
from app.models.base import ContentStatus


def favorite_song_ids(user_id: int, db: Session | None = None) -> set[int]:
    """该用户已收藏的歌曲 id 集合（列表/详情一次性取，避免逐首查）。

    ``db`` 可传入调用方会话（路由内与歌曲列表同会话，省一次连接）；
    不传则自建会话并负责关闭。
    """
    own = db is None
    session = db if db is not None else get_session_factory()()
    try:
        rows = (
            session.execute(select(SongFavorite.song_id).where(SongFavorite.user_id == user_id))
            .scalars()
            .all()
        )
        return {int(r) for r in rows}
    finally:
        if own:
            session.close()


def _published_song(db, song_id: int) -> Song:
    """歌曲必须存在且已发布（与 GET /songs/{id} 同口径：否则 40401）。"""
    song = db.get(Song, song_id)
    if song is None or song.status != ContentStatus.PUBLISHED:
        raise BizError(http_status=404, code=40401, message="song not found")
    return song


def set_song_favorite(user_id: int, song_id: int, favorited: bool) -> dict:
    """收藏（favorited=True）/取消收藏（False）；幂等，返回 ``{song_id, favorited}``。"""
    db = get_session_factory()()
    try:
        _published_song(db, song_id)
        existing = db.execute(
            select(SongFavorite).where(
                SongFavorite.user_id == user_id, SongFavorite.song_id == song_id
            )
        ).scalar_one_or_none()

        if favorited and existing is None:
            db.add(SongFavorite(user_id=user_id, song_id=song_id))
            try:
                db.commit()
            except IntegrityError:
                # 并发/双击下唯一键冲突 = 已收藏（幂等语义，不是错误）
                db.rollback()
        elif not favorited and existing is not None:
            db.execute(
                delete(SongFavorite).where(
                    SongFavorite.user_id == user_id, SongFavorite.song_id == song_id
                )
            )
            db.commit()
        return {"song_id": song_id, "favorited": favorited}
    finally:
        db.close()
