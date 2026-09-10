"""内部 REST 统一客户端（docs/21 §4：Python → Java 跨服务委托的唯一出入口）。

与「级联功能随手内联 httpx」的旧模式（placement._callback_level，P0-6）不同：
- 3s 超时（docs/06 §1 内部通信默认）；
- 失败**抛异常+日志**（调用方决定是否降级，禁止静默吞 4xx/5xx——P0-6 正是静默吞
  导致档位回写 100% 断链）；
- 鉴权头 `Authorization: Bearer <service-token>`（R-17：文档与代码对齐，
  SecurityConfig ServiceTokenFilter 读同头）；
- **`X-Request-Id` 透传**（docs/50 §9.2 断点 1）：此前 Python→Java 的内部调用不带
  correlation id，控制台的"管理员操作 → Java → Python"跨服务审计链**每一跳都断**，
  日志无法 join。这里统一注入 ``get_request_id()``（非请求上下文时为 ``-``，则不注入）。

当前内部端点：POST /internal/level（档位回写）、POST /internal/checkin（打卡卡物化）。
"""

from __future__ import annotations

import logging

import httpx

from app.core.config import get_settings
from app.core.trace import REQUEST_ID_HEADER, get_request_id

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 3.0


def internal_headers() -> dict[str, str]:
    """内部调用统一头（鉴权 + 请求 id 透传）；独立成函数便于单测与将来接更多委托。"""
    settings = get_settings()
    headers = {"Authorization": f"Bearer {settings.service_token}"}
    request_id = get_request_id()
    # "-" = 不在请求上下文（后台任务/脚本）：不注入空 id，避免把 Java 侧 MDC 覆盖成 "-"
    if request_id and request_id != "-":
        headers[REQUEST_ID_HEADER] = request_id
    return headers


def post_internal(path: str, payload: dict) -> httpx.Response:
    """POST 内部端点；非 2xx 抛 httpx.HTTPStatusError（调用方捕获并降级+告警）。"""
    settings = get_settings()
    resp = httpx.post(
        f"{settings.java_base_url}{path}",
        json=payload,
        headers=internal_headers(),
        timeout=TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    return resp
