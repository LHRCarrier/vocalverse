"""M3 P5：C 端搜索三 tab 真源（docs/53 §1 P5 DoD ①）。

数据源 = Java 写、Python 只读映射：posts / users+user_profiles / listening_materials；
本文件验证可见性过滤、大小写不敏感、handle 命中、LIKE 通配转义与未知 type 400。
"""

from __future__ import annotations

from app.db import get_session_factory
from app.models.community import Post
from app.models.content import ListeningMaterial
from app.models.user import User, UserProfile


def _user(username: str, nickname: str, handle: str | None = None) -> int:
    db = get_session_factory()()
    try:
        user = User(username=username, nickname=nickname, password_hash="x")
        db.add(user)
        db.flush()
        db.add(
            UserProfile(
                user_id=user.id,
                age_group="adult",
                cefr_level="L3",
                handle=handle,
                tint="#37546e",
            )
        )
        db.commit()
        return int(user.id)
    finally:
        db.close()


def _post(author_id: int, title: str, body: str, status: str = "visible") -> None:
    db = get_session_factory()()
    try:
        db.add(Post(author_id=author_id, kind="article", title=title, body=body, status=status))
        db.commit()
    finally:
        db.close()


def _material(title: str, status: str) -> None:
    db = get_session_factory()()
    try:
        db.add(
            ListeningMaterial(
                title=title,
                level=1,
                audio_url="/api/v1/audio/demo.mp3",
                status=status,
                interest_tags=["口语"],
            )
        )
        db.commit()
    finally:
        db.close()


def _seed() -> int:
    me = _user("search_me", "我自己", "me_search")
    author = _user("search_author", "Teacher Amy", "amyteach")
    _post(author, "Three words for small talk", "Listen, shadow, compare")
    _post(author, "Hidden draft", "should not appear", status="hidden")
    _post(author, "Deleted post", "should not appear", status="deleted")
    _material("Shadowing tutorial · 10 minutes", "published")
    _material("Draft tutorial", "draft")
    return me


def test_search_posts_filters_visibility_and_case(client, auth_headers):
    me = _seed()
    r = client.get("/api/v1/search?type=posts&q=SHADOW", headers=auth_headers)
    assert r.status_code == 200, r.text
    items = r.json()["data"]["items"]
    assert [i["title"] for i in items] == ["Three words for small talk"]
    assert items[0]["author"]["handle"] == "amyteach"

    hidden = client.get("/api/v1/search?type=posts&q=should not appear", headers=auth_headers)
    assert hidden.json()["data"]["items"] == []
    assert me != 0


def test_search_users_matches_handle_and_excludes_self(client, auth_headers):
    _seed()
    by_handle = client.get("/api/v1/search?type=users&q=amyteach", headers=auth_headers)
    items = by_handle.json()["data"]["items"]
    assert [i["nickname"] for i in items] == ["Teacher Amy"]

    by_nickname = client.get("/api/v1/search?type=users&q=teacher", headers=auth_headers)
    assert [i["nickname"] for i in by_nickname.json()["data"]["items"]] == ["Teacher Amy"]

    # 自己不出现（搜索自己昵称/用户名/handle 都无结果）
    for q in ("我自己", "search_me", "me_search"):
        r = client.get(f"/api/v1/search?type=users&q={q}", headers=auth_headers)
        assert r.json()["data"]["items"] == [], q


def test_search_tutorials_only_published(client, auth_headers):
    _seed()
    r = client.get("/api/v1/search?type=tutorials&q=tutorial", headers=auth_headers)
    items = r.json()["data"]["items"]
    assert [i["title"] for i in items] == ["Shadowing tutorial · 10 minutes"]
    assert items[0]["tags"] == ["口语"] and items[0]["level"] == 1


def test_search_wildcard_escaped_and_empty_query(client, auth_headers):
    _seed()
    # `%` / `_` 是 LIKE 通配符，必须转义为字面量 → 不得变成全表匹配
    for q in ("%", "_", "%%"):
        r = client.get(f"/api/v1/search?type=posts&q={q}", headers=auth_headers)
        assert r.json()["data"]["items"] == [], q
    empty = client.get("/api/v1/search?type=posts&q=", headers=auth_headers)
    assert empty.json()["data"]["items"] == []


def test_search_unknown_type_400(client, auth_headers):
    r = client.get("/api/v1/search?type=hack&q=x", headers=auth_headers)
    assert r.status_code == 400
