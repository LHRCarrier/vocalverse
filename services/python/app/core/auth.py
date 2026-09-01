"""认证辅助（docs/06 §11：Java 签发 JWT，Python 验签）。

- HS256 手写实现（无额外依赖）：与 Java 侧 jjwt 默认 HS256 兼容（base64url 无 padding）；
- 测试模式（APP_TESTING=true）允许 X-Test-User-Id 头直传（CI/本地无 Java 时联通性自测）。
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


async def get_current_user_id(
    authorization: str = Header(default=""),
    x_test_user_id: str | None = Header(default=None),
) -> int:
    """FastAPI 依赖：返回当前用户 id（JWT sub 或测试头）。"""
    settings = get_settings()
    if settings.testing and x_test_user_id:
        return int(x_test_user_id)
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    try:
        payload = decode_jwt(authorization[7:], settings.jwt_secret)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="invalid token") from exc
    uid = payload.get("sub") or payload.get("user_id")
    if uid is None:
        raise HTTPException(status_code=401, detail="token missing sub")
    return int(uid)
