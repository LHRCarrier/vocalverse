"""C 端搜索（docs/53 P5）：帖子 / 用户 / 教程（听力素材）三 tab 真源。

- 数据源（全部 Java 写、Python **只读**映射，docs/10 §3.1 写方矩阵）：
  ``posts``（可见帖）/ ``users + user_profiles``（active 用户）/
  ``listening_materials``（published）；
- 口径：关键词大小写不敏感子串匹配（SQL LIKE；``%``/``_``/``\\`` 显式转义，防通配注入）；
  空关键词返回空列表（不扫全表）；``limit`` 上限 50；
- 检索实现：本期 PG LIKE 即满足 demo（docs/42 §14：ES/Meilisearch 后置），不引搜索基础设施。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.auth import get_current_user_id
from app.core.response import ok
from app.db import get_session_factory
from app.models.base import ContentStatus
from app.models.community import Post
from app.models.content import ListeningMaterial
from app.models.user import User, UserProfile

router = APIRouter(prefix="/api/v1/search", tags=["search"])

SEARCH_KINDS = ("posts", "users", "tutorials")


def _like(column, q: str):
    """大小写不敏感子串匹配；转义 LIKE 通配符（用户输入 `%` 不得变成全表匹配）。"""
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return func.lower(column).like(f"%{escaped.lower()}%", escape="\\")


def _db() -> Session:
    return get_session_factory()()


def search_posts(db: Session, needle: str, limit: int) -> list[dict[str, Any]]:
    rows = db.execute(
        select(Post, User, UserProfile)
        .join(User, User.id == Post.author_id)
        .outerjoin(UserProfile, UserProfile.user_id == Post.author_id)
        .where(
            Post.status.not_in(("hidden", "deleted")),
            or_(_like(Post.title, needle), _like(Post.body, needle)),
        )
        .order_by(Post.id.desc())
        .limit(limit)
    ).all()
    return [
        {
            "id": int(p.id),
            "title": p.title or (p.body or "")[:40],
            "domain": p.domain,
            "kind": p.kind,
            "author": {
                "nickname": u.nickname,
                "handle": prof.handle if prof else None,
                "tint": prof.tint if prof else None,
                "avatar_url": prof.avatar_url if prof else None,
            },
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p, u, prof in rows
    ]


def search_users(db: Session, me: int, needle: str, limit: int) -> list[dict[str, Any]]:
    rows = db.execute(
        select(User, UserProfile)
        .outerjoin(UserProfile, UserProfile.user_id == User.id)
        .where(
            User.status == "active",
            User.id != me,
            or_(
                _like(User.username, needle),
                _like(User.nickname, needle),
                _like(UserProfile.handle, needle),
            ),
        )
        .order_by(User.id)
        .limit(limit)
    ).all()
    return [
        {
            "user_id": int(u.id),
            "nickname": u.nickname,
            "handle": prof.handle if prof else None,
            "tint": prof.tint if prof else None,
            "avatar_url": prof.avatar_url if prof else None,
            "cefr_level": prof.cefr_level if prof else None,
        }
        for u, prof in rows
    ]


def search_tutorials(db: Session, needle: str, limit: int) -> list[dict[str, Any]]:
    rows = (
        db.execute(
            select(ListeningMaterial)
            .where(
                ListeningMaterial.status == ContentStatus.PUBLISHED,
                _like(ListeningMaterial.title, needle),
            )
            .order_by(ListeningMaterial.id.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": int(m.id),
            "title": m.title,
            "level": int(m.level),
            "duration_s": int(m.duration_s) if m.duration_s else None,
            "source": m.source,
            "tags": m.interest_tags if isinstance(m.interest_tags, list) else [],
        }
        for m in rows
    ]


@router.get("")
async def search(
    q: str = Query(default="", max_length=60),
    kind: str = Query(default="posts", alias="type"),
    limit: int = Query(default=20, ge=1, le=50),
    user_id: int = Depends(get_current_user_id),
):
    """三 tab 统一入口（docs/53 P5）：``?type=posts|users|tutorials&q=``。"""
    if kind not in SEARCH_KINDS:
        raise HTTPException(status_code=400, detail="unknown search type")
    needle = q.strip()
    if not needle:
        return ok({"type": kind, "items": []})
    db = _db()
    try:
        if kind == "posts":
            items = search_posts(db, needle, limit)
        elif kind == "users":
            items = search_users(db, user_id, needle, limit)
        else:
            items = search_tutorials(db, needle, limit)
        return ok({"type": kind, "items": items})
    finally:
        db.close()
