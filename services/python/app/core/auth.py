"""认证辅助（docs/06 §11：Java 签发 JWT，Python 验签）。

- HS256 手写实现（无额外依赖）：与 Java 侧 jjwt 默认 HS256 兼容（base64url 无 padding）；
- 测试模式（APP_TESTING=true）允许 X-Test-User-Id 头直传（CI/本地无 Java 时联通性自测）。

**控制台令牌（docs/50 §4.1，2026-09-10 新增）**：管理端是**独立身份**，
令牌 claims 为 ``sub/aud/iss/role/perms/typ/jti``，其中：

- ``aud`` = ``vocalverse-console`` 是**硬闸**：App 令牌拿去访问控制台、控制台令牌拿去
  访问 App API，都必须被拒（§4.1 C-4）；
- ``typ`` = ``console-access``；
- 双密钥：控制台令牌用 ``APP_CONSOLE_JWT_SECRET`` 签，与学习者 ``APP_JWT_SECRET`` 不同。

**兼容口径（禁止扩大打击面）**：既有 App 令牌**没有** ``aud`` claim，
所以 App 侧只拒绝"**携带外来 aud**"的令牌 —— 给存量令牌补 aud 会让全体在线用户登出（§4.1 C-4）。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

from fastapi import Header, HTTPException

from app.core.config import get_settings

#: 控制台令牌固定口径（与 Java ConsoleJwtService 对齐，docs/50 §4.1）
CONSOLE_AUDIENCE = "vocalverse-console"
CONSOLE_ISSUER = "vocalverse-java"
CONSOLE_TOKEN_TYPE = "console-access"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def create_jwt(payload: dict[str, Any], secret: str, ttl_s: int = 3600) -> str:
    """仅供测试/内部使用（正式签发在 Java；本函数为联调与单测提供同格式令牌）。"""
    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    body = {"exp": now + ttl_s, "iat": now, **payload}
    h = _b64url(json.dumps(header, separators=(",", ":")).encode())
    p = _b64url(json.dumps(body, separators=(",", ":")).encode())
    sig = _b64url(hmac.new(secret.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest())
    return f"{h}.{p}.{sig}"


def decode_jwt(token: str, secret: str) -> dict[str, Any]:
    """验签 + 过期检查；失败抛 ValueError。"""
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("bad token")
    h, p, sig = parts
    expected = hmac.new(secret.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest()
    actual = _b64url_decode(sig)
    if not hmac.compare_digest(expected, actual):
        raise ValueError("bad signature")
    payload = json.loads(_b64url_decode(p))
    if payload.get("exp", 0) < int(time.time()):
        raise ValueError("token expired")
    return payload


def decode_console_jwt(
    token: str,
    secret: str,
    *,
    audience: str = CONSOLE_AUDIENCE,
    issuer: str = CONSOLE_ISSUER,
) -> dict[str, Any]:
    """验签 + ``aud``/``iss``/``typ`` 三重校验；任一项不符抛 ``ValueError``。

    **为什么三重都要**（docs/50 §4.1）：只验签名时，任何用同一密钥签的令牌都能进控制台；
    只验 ``aud`` 时，签发方把 iss/typ 写错不会被发现。控制台能看别人的 prompt，
    鉴权面必须"默认拒绝、逐项放行"。
    """
    payload = decode_jwt(token, secret)
    aud = payload.get("aud")
    if aud != audience:
        raise ValueError(f"bad audience: {aud!r}")
    iss = payload.get("iss")
    if iss != issuer:
        raise ValueError(f"bad issuer: {iss!r}")
    typ = payload.get("typ") or payload.get("type")
    if typ != CONSOLE_TOKEN_TYPE:
        raise ValueError(f"bad token type: {typ!r}")
    return payload


def is_console_token(payload: dict[str, Any]) -> bool:
    """是否为控制台令牌（按 ``aud``/``typ`` 判定，不看密钥 —— 双密钥是第二道闸）。"""
    typ = payload.get("typ") or payload.get("type")
    return payload.get("aud") == CONSOLE_AUDIENCE or typ == CONSOLE_TOKEN_TYPE


async def get_current_user_id(
    authorization: str = Header(default=""),
    x_test_user_id: str | None = Header(default=None),
) -> int:
    """FastAPI 依赖：返回当前用户 id（JWT sub 或测试头）。

    **控制台令牌必须在此被拒**（docs/50 §4.1）：管理员不是学习者，
    若控制台令牌能当学习者身份用，``sub``（adminUserId）会撞进 ``users.id`` 空间，
    等于把管理端账号变成任意用户身份的通行证。
    """
    settings = get_settings()
    if settings.testing and x_test_user_id:
        return int(x_test_user_id)
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    try:
        payload = decode_jwt(authorization[7:], settings.jwt_secret)
        _reject_foreign_token(payload)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="invalid token") from exc
    uid = payload.get("sub") or payload.get("user_id")
    if uid is None:
        raise HTTPException(status_code=401, detail="token missing sub")
    return int(uid)


def _reject_foreign_token(payload: dict[str, Any]) -> None:
    """拒绝非学习者令牌（docs/50 §4.1 C-4 口径：**只拒携带外来 aud 的令牌**）。

    既有 App 令牌**没有** ``aud`` claim，因此本检查对在线用户零影响；
    给存量令牌补 ``aud`` 会让全体登出，故此处**不要求** App 令牌带 aud，只拒绝"带了"的。
    """
    if payload.get("aud") is not None:
        raise ValueError("foreign audience token")
    if is_console_token(payload):
        raise ValueError("console token cannot be used as learner identity")
