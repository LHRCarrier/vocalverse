"""控制台 API 依赖（docs/50 §4.1 / §10.4 错误码 46xxx）。

- ``get_console_admin``：验 Java 签发的控制台 JWT（签名 + 过期 + ``aud`` + ``iss`` + ``typ``），
  失败一律 **46001（401）** —— 前端据此跳**控制台**登录页，绝不跳 App 登录；
- ``require_perm(code)``：读令牌 ``perms`` 数组，缺码 → **46002**（``data.required`` 回传所需码）；
- ``require_telemetry`` / ``require_llm_trace``：功能位闸门 → **46014**。

**fail-closed**：``APP_CONSOLE_JWT_SECRET`` 未配置时直接 46001，绝不用空密钥验签。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fastapi import Header

from app.core.auth import decode_console_jwt
from app.core.config import get_settings
from app.core.response import BizError


class ConsoleBizError(BizError):
    """控制台业务异常：比 ``BizError`` 多一个 ``data``（如 46002 的 ``required``）。"""

    def __init__(self, http_status: int, code: int, message: str, data: Any = None):
        super().__init__(http_status, code, message)
        self.data = data


@dataclass
class ConsoleAdmin:
    """控制台登录态（只放鉴权/审计需要的字段，不缓存业务数据）。"""

    admin_id: int
    username: str | None = None
    role: str | None = None
    perms: frozenset[str] = field(default_factory=frozenset)
    jti: str | None = None
    claims: dict[str, Any] = field(default_factory=dict)


async def get_console_admin(authorization: str = Header(default="")) -> ConsoleAdmin:
    """FastAPI 依赖：校验控制台令牌并返回登录态（任何失败 → 46001）。"""
    settings = get_settings()
    if not settings.console_jwt_secret:
        # 未配置 = 控制台不可用；绝不用空密钥"验签通过"（fail-closed）
        raise ConsoleBizError(401, 46001, "console auth not configured")
    if not authorization.startswith("Bearer "):
        raise ConsoleBizError(401, 46001, "missing console bearer token")
    try:
        payload = decode_console_jwt(
            authorization[7:],
            settings.console_jwt_secret,
            audience=settings.console_jwt_audience,
            issuer=settings.console_jwt_issuer,
        )
    except ValueError as exc:
        raise ConsoleBizError(401, 46001, f"invalid console token: {exc}") from exc
    sub = payload.get("sub")
    if sub is None:
        raise ConsoleBizError(401, 46001, "console token missing sub")
    perms = payload.get("perms") or []
    if isinstance(perms, str):
        perms = [perms]
    return ConsoleAdmin(
        admin_id=int(sub),
        username=payload.get("username") or payload.get("name"),
        role=payload.get("role"),
        perms=frozenset(str(p) for p in perms),
        jti=payload.get("jti"),
        claims=payload,
    )


def has_perm(admin: ConsoleAdmin, code: str) -> bool:
    """权限判定：``super`` 角色或 ``*`` 通配放行（docs/50 §4.3 前端同口径）。"""
    if admin.role == "super" or "*" in admin.perms or "console:super" in admin.perms:
        return True
    return code in admin.perms


def require_perm(code: str):
    """依赖工厂：``Depends(require_perm("ops:metric:read"))``（仅权限，不含功能位闸门）。"""
    from fastapi import Depends

    async def _dependency(admin: ConsoleAdmin = Depends(get_console_admin)) -> ConsoleAdmin:
        if not has_perm(admin, code):
            raise ConsoleBizError(403, 46002, f"permission required: {code}", {"required": code})
        return admin

    return _dependency


def console_guard(*, telemetry: bool = False, llm_trace: bool = False, perm: str | None = None):
    """组合依赖：功能位闸门 + 权限码（顺序：先闸门后权限——功能没开就没有"权限不足"一说）。"""
    from fastapi import Depends

    async def _dependency(admin: ConsoleAdmin = Depends(get_console_admin)) -> ConsoleAdmin:
        settings = get_settings()
        if telemetry and not settings.ops_telemetry_enabled:
            raise ConsoleBizError(403, 46014, "ops telemetry disabled (APP_OPS_TELEMETRY_ENABLED)")
        if llm_trace and not settings.llm_trace_enabled:
            raise ConsoleBizError(403, 46014, "llm trace disabled (APP_LLM_TRACE_ENABLED)")
        if perm and not has_perm(admin, perm):
            raise ConsoleBizError(403, 46002, f"permission required: {perm}", {"required": perm})
        return admin

    return _dependency


__all__ = [
    "ConsoleAdmin",
    "ConsoleBizError",
    "console_guard",
    "get_console_admin",
    "has_perm",
    "require_perm",
]
