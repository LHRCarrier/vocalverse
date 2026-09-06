"""内部 REST 统一客户端（docs/21 §4：Python → Java 跨服务委托的唯一出入口）。

与「级联功能随手内联 httpx」的旧模式（placement._callback_level，P0-6）不同：
- 3s 超时（docs/06 §1 内部通信默认）；
- 失败**抛异常+日志**（调用方决定是否降级，禁止静默吞 4xx/5xx——P0-6 正是静默吞
  导致档位回写 100% 断链）；
- 鉴权头 `Authorization: Bearer <service-token>`（R-17：文档与代码对齐，
  SecurityConfig ServiceTokenFilter 读同头）。

当前内部端点：POST /internal/level（档位回写）、POST /internal/checkin（打卡卡物化）。
"""

from __future__ import annotations

import logging

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 3.0


def post_internal(path: str, payload: dict) -> httpx.Response:
    """POST 内部端点；非 2xx 抛 httpx.HTTPStatusError（调用方捕获并降级+告警）。"""
    settings = get_settings()
    resp = httpx.post(
        f"{settings.java_base_url}{path}",
        json=payload,
        headers={"Authorization": f"Bearer {settings.service_token}"},
        timeout=TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    return resp
