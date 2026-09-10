"""控制台鉴权测试（docs/50 §14.2 第 4 条 + 双身份闸门）。

三个闸门：

1. ``aud`` 不符的控制台令牌 → 46001（跨域令牌硬闸，§4.1 C-4）；
2. ``iss``/``typ`` 不符 → 46001；
3. **控制台令牌不得当学习者身份用**（``get_current_user_id`` 必须拒），
   也不得被学习者令牌顶替（console 端点只认控制台密钥）。
"""

from __future__ import annotations

import pytest
from app.core.auth import (
    CONSOLE_AUDIENCE,
    CONSOLE_ISSUER,
    CONSOLE_TOKEN_TYPE,
    create_jwt,
    decode_console_jwt,
    get_current_user_id,
)
from app.core.config import get_settings
from fastapi import HTTPException

from .helpers import console_headers, console_token


def test_wrong_audience_rejected_by_console_admin(client) -> None:
    """``aud != vocalverse-console`` → 46001（其余 claims 全部合法）。"""
    headers = console_headers(aud="vocalverse-app")
    resp = client.get("/api/v1/console/ops/overview", headers=headers)
    assert resp.status_code == 401
    assert resp.json()["code"] == 46001


def test_wrong_issuer_and_type_rejected(client) -> None:
    assert (
        client.get(
            "/api/v1/console/ops/overview", headers=console_headers(iss="evil-issuer")
        ).json()["code"]
        == 46001
    )
    assert (
        client.get(
            "/api/v1/console/ops/overview", headers=console_headers(typ="app-access")
        ).json()["code"]
        == 46001
    )


def test_missing_token_rejected(client) -> None:
    resp = client.get("/api/v1/console/ops/overview")
    assert resp.status_code == 401
    assert resp.json()["code"] == 46001


def test_learner_token_cannot_access_console(client, auth_headers) -> None:
    """学习者令牌（无 aud，签的是 APP_JWT_SECRET）在控制台端点上必须无效。"""
    learner = create_jwt({"sub": "1"}, get_settings().jwt_secret)
    resp = client.get(
        "/api/v1/console/ops/overview", headers={"Authorization": f"Bearer {learner}"}
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == 46001


def test_console_token_rejected_as_learner_identity(client) -> None:
    """控制台令牌走学习者端点 → 401（管理端账号不得变成任意用户身份的通行证）。"""
    resp = client.get(
        "/api/v1/reading/books", headers={"Authorization": f"Bearer {console_token()}"}
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_id_rejects_console_token_directly() -> None:
    token = console_token()
    with pytest.raises(HTTPException) as exc:
        await get_current_user_id(authorization=f"Bearer {token}", x_test_user_id=None)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_id_still_accepts_legacy_app_token() -> None:
    """既有 App 令牌**不带 aud** → 必须继续可用（docs/50 §4.1 C-4：不得扩大打击面）。"""
    token = create_jwt({"sub": "42"}, get_settings().jwt_secret)
    uid = await get_current_user_id(authorization=f"Bearer {token}", x_test_user_id=None)
    assert uid == 42


def test_decode_console_jwt_happy_path() -> None:
    token = console_token()
    payload = decode_console_jwt(token, get_settings().console_jwt_secret)
    assert payload["aud"] == CONSOLE_AUDIENCE
    assert payload["iss"] == CONSOLE_ISSUER
    assert payload["typ"] == CONSOLE_TOKEN_TYPE


def test_missing_permission_returns_46002_with_required(client) -> None:
    """缺权限码 → 46002，``data.required`` 回传所需码（docs/50 §10.4）。"""
    headers = console_headers(perms=())
    resp = client.get("/api/v1/console/ops/metrics/catalog", headers=headers)
    assert resp.status_code == 403
    body = resp.json()
    assert body["code"] == 46002
    assert body["data"]["required"] == "ops:metric:read"


def test_super_role_passes_all_perms(client) -> None:
    headers = console_headers(role="super", perms=())
    resp = client.get("/api/v1/console/ops/metrics/catalog", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["code"] == 0
