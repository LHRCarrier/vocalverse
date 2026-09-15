"""控制台测试公共夹具：干净 sink/registry + 控制台令牌构造。"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest
from app.console.ops.metrics import reset_registry_for_tests
from app.console.trace.sink import reset_sink_for_tests
from app.core.auth import (
    CONSOLE_AUDIENCE,
    CONSOLE_ISSUER,
    CONSOLE_TOKEN_TYPE,
    create_jwt,
)
from app.core.config import get_settings


@pytest.fixture(autouse=True)
def _clean_console_state():
    """每个用例一套干净的 sink/registry（采集计数是全局的，跨用例必须隔离）。"""
    reset_sink_for_tests()
    reset_registry_for_tests()
    yield
    reset_sink_for_tests()
    reset_registry_for_tests()


def console_token(
    *,
    admin_id: int = 7,
    role: str = "ops",
    perms: tuple[str, ...] = ("ops:metric:read",),
    aud: str = CONSOLE_AUDIENCE,
    iss: str = CONSOLE_ISSUER,
    typ: str = CONSOLE_TOKEN_TYPE,
    username: str = "ops-admin",
    **extra: Any,
) -> str:
    """按 docs/50 §4.1 的 claims 规格签一个控制台令牌（testing 档固定密钥）。"""
    settings = get_settings()
    claims: dict[str, Any] = {
        "sub": str(admin_id),
        "aud": aud,
        "iss": iss,
        "typ": typ,
        "role": role,
        "perms": list(perms),
        "jti": "test-jti",
        "username": username,
    }
    claims.update(extra)
    return create_jwt(claims, settings.console_jwt_secret)


def console_headers(**kwargs: Any) -> dict[str, str]:
    return {"Authorization": f"Bearer {console_token(**kwargs)}"}


async def wait_for(predicate, timeout: float = 5.0, interval: float = 0.02) -> bool:
    """轮询等待（后台任务异步落库的测试辅助）。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        await asyncio.sleep(interval)
    return False
