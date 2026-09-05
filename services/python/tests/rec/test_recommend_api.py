"""第八步：/api/v1/recommendations 路由契约（TestClient）。

契约（docs/06 §7）：envelope {code, message, data}；type∈{scene,shadow}（pattern 校验）；
limit∈[1,20]；需要认证（测试模式 X-Test-User-Id，否则 Bearer，缺失 → 401）。
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from app.db import get_session_factory
from app.models import MaterialDifficulty, Scenario, User, UserProfile, UserSkillState


def _mk_user(level: str, tags: list[str]) -> int:
    db = get_session_factory()()
    try:
        u = User(username=f"r{uuid4().hex[:8]}", nickname="t", password_hash="x")
        db.add(u)
        db.flush()
        uid = int(u.id)
        db.add(UserProfile(user_id=uid, interest_tags=tags, cefr_level=level))
        db.add(
            UserSkillState(
                user_id=uid,
                pron_est=0,
                flu_est=0,
                est_score=0,
                est_level=level,
                confidence=Decimal("1.0"),
            )
        )
        db.commit()
        return uid
    finally:
        db.close()


def _mk_scene(title: str, diff_level: str, tags: list[str], scene_type: str = "cafe") -> int:
    db = get_session_factory()()
    try:
        s = Scenario(
            title=title,
            scene_type=scene_type,
            difficulty=2,
            system_prompt="p",
            opening_line="o",
            target_corpus="Hi|你好",
            interest_tags=tags,
            status="published",
        )
        db.add(s)
        db.flush()
        db.add(
            MaterialDifficulty(
                content_type="scene",
                content_id=s.id,
                diff_score=Decimal("70"),
                diff_level=diff_level,
                version="expert-v1",
            )
        )
        db.commit()
        return int(s.id)
    finally:
        db.close()


def test_recommendations_success_envelope(client, auth_headers) -> None:
    """GET ?type=scene&limit=5 → 200 + envelope{code:0, data:{type, items}}，items 非空。"""
    _mk_user("L2", ["coffee"])  # Auth 头 X-Test-User-Id=1 → 用户 id 1
    _mk_scene("s", "L2", ["coffee"], "cafe")
    resp = client.get(
        "/api/v1/recommendations", params={"type": "scene", "limit": 5}, headers=auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["type"] == "scene"
    assert isinstance(body["data"]["items"], list) and body["data"]["items"]
    assert any(it["title"] == "s" for it in body["data"]["items"])


def test_recommendations_type_validation(client, auth_headers) -> None:
    """type 非法（非 scene/shadow）→ 422。"""
    resp = client.get("/api/v1/recommendations", params={"type": "bogus"}, headers=auth_headers)
    assert resp.status_code == 422


def test_recommendations_limit_bounds(client, auth_headers) -> None:
    """limit 越界（0 或 21）→ 422；边界 1/20 通过。"""
    assert (
        client.get(
            "/api/v1/recommendations", params={"type": "scene", "limit": 0}, headers=auth_headers
        ).status_code
        == 422
    )
    assert (
        client.get(
            "/api/v1/recommendations", params={"type": "scene", "limit": 21}, headers=auth_headers
        ).status_code
        == 422
    )
    _mk_user("L2", ["coffee"])
    assert (
        client.get(
            "/api/v1/recommendations", params={"type": "scene", "limit": 1}, headers=auth_headers
        ).status_code
        == 200
    )
    assert (
        client.get(
            "/api/v1/recommendations", params={"type": "scene", "limit": 20}, headers=auth_headers
        ).status_code
        == 200
    )


def test_recommendations_requires_auth(client) -> None:
    """无任何认证头 → 401（missing bearer token）。"""
    assert client.get("/api/v1/recommendations", params={"type": "scene"}).status_code == 401


def test_recommendations_shadow_type(client, auth_headers) -> None:
    """type=shadow → data.type='shadow'；无影子素材也返回合法 envelope（items 可为空）。"""
    resp = client.get("/api/v1/recommendations", params={"type": "shadow"}, headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["type"] == "shadow"
    assert isinstance(body["data"]["items"], list)
