"""控制台鉴权测试（docs/50 §14.2 第 4 条 + 双身份闸门）。

三个闸门：

1. ``aud`` 不符的控制台令牌 → 46001（跨域令牌硬闸，§4.1 C-4）；
2. ``iss``/``typ`` 不符 → 46001；
3. **控制台令牌不得当学习者身份用**（``get_current_user_id`` 必须拒），
   也不得被学习者令牌顶替（console 端点只认控制台密钥）。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

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


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _hs384_console_token() -> str:
    """手签一个 **HS384** 的控制台令牌（claims 全合法，只有算法不同）。

    模拟的就是 Java 侧"密钥 ≥48 字节 → JJWT 选 HmacSHA384"的真实产物。
    """
    secret = get_settings().console_jwt_secret
    now = int(time.time())
    header = {"alg": "HS384", "typ": "JWT"}
    body = {
        "sub": "7",
        "aud": CONSOLE_AUDIENCE,
        "iss": CONSOLE_ISSUER,
        "typ": CONSOLE_TOKEN_TYPE,
        "role": "ops",
        "perms": ["ops:metric:read"],
        "iat": now,
        "exp": now + 3600,
    }
    h = _b64url(json.dumps(header, separators=(",", ":")).encode())
    p = _b64url(json.dumps(body, separators=(",", ":")).encode())
    sig = _b64url(hmac.new(secret.encode(), f"{h}.{p}".encode(), hashlib.sha384).digest())
    return f"{h}.{p}.{sig}"


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


def test_non_hs256_alg_rejected_with_actionable_message(client) -> None:
    """非 HS256 的令牌 → 46001，且 message 必须**点出算法**（2026-09-10 实测缺陷的回归）。

    背景：Java 侧 ``Keys.hmacShaKeyFor`` 会按**密钥长度**自动选算法（≥48 字节 → HS384），
    而 ``.signWith(key)`` 用的就是它；本服务只算 HMAC-SHA256。于是密钥一旦 ≥48 字节，
    Java 签的令牌到这里全是 46001 —— 而当时的报错只有 "bad signature"，把"算法不一致"
    伪装成"密钥不对"（实测排查了好几轮）。这里钉住两件事：**拒绝**，且**说清是 alg 的问题**。
    """
    token = _hs384_console_token()
    resp = client.get("/api/v1/console/ops/overview", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401
    body = resp.json()
    assert body["code"] == 46001
    assert "HS384" in body["message"], f"报错必须点出实际算法，否则会误导排查方向：{body}"


def test_same_secret_signed_hs256_still_accepted(client) -> None:
    """同一密钥、HS256（正确算法）→ 正常通过：证明上一条拒的是**算法**而不是密钥。

    端点选 ``/ops/metrics/catalog`` 与 ``console_headers()`` 的默认权限码
    ``ops:metric:read`` 配套（用 ``/ops/overview`` 会因为要 ``ops:overview:read`` 而 46002，
    那是权限问题、与本用例要证的算法问题无关）。
    """
    resp = client.get("/api/v1/console/ops/metrics/catalog", headers=console_headers())
    assert resp.json()["code"] == 0


def test_java_style_array_audience_accepted(client) -> None:
    """``aud`` 为**数组**时必须放行 —— 这正是 Java/JJWT 签出来的形状（2026-09-10 实测缺陷的回归）。

    Java 用 ``.audience().add("vocalverse-console").and()`` 签发，产出 ``["vocalverse-console"]``；
    RFC 7519 两种形态都合法。修复前这里直接与裸字符串比较，导致**真 Java 令牌在 Python 侧一律
    46001 bad audience** —— 而本文件其余用例全用 Python 自签的**字符串** aud，所以一直绿。
    这条用例就是把"跨服务那一跳"钉住：形状按 Java 的真实产物来。
    """
    secret = get_settings().console_jwt_secret
    token = create_jwt(
        {
            "sub": "1",
            "aud": [CONSOLE_AUDIENCE],
            "iss": CONSOLE_ISSUER,
            "typ": CONSOLE_TOKEN_TYPE,
            "role": "super",
            "perms": ["ops:metric:read"],
        },
        secret,
    )
    resp = client.get(
        "/api/v1/console/ops/metrics/catalog", headers={"Authorization": f"Bearer {token}"}
    )
    body = resp.json()
    assert body["code"] == 0, f"数组形态的 aud 必须被接受（Java 就是这么签的）：{body}"


def test_array_audience_not_containing_console_still_rejected(client) -> None:
    """数组里**没有**控制台 aud → 仍必须拒（放行的是形态，不是放宽校验）。"""
    token = create_jwt(
        {
            "sub": "1",
            "aud": ["vocalverse-app"],
            "iss": CONSOLE_ISSUER,
            "typ": CONSOLE_TOKEN_TYPE,
        },
        get_settings().console_jwt_secret,
    )
    resp = client.get(
        "/api/v1/console/ops/metrics/catalog", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == 46001


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
