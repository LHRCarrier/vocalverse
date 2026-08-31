"""X-Request-Id 全链路透传（docs/06 §11）。

- 纯 ASGI 中间件（不用 BaseHTTPMiddleware，避免对 SSE 流式响应缓冲）；
- 读入上游 X-Request-Id（nginx 已兜底生成），无则自生成，并回写响应头；
- 经 ContextVar 注入日志上下文，RequestIdLogFilter 把 id 刷到每条 LogRecord
  （handler 格式化串可引用 %(request_id)s；后续接 loguru/JSON 时取 get_request_id()）。
"""

from __future__ import annotations

import logging
import uuid
from contextvars import ContextVar

REQUEST_ID_HEADER = "X-Request-Id"

_request_id: ContextVar[str] = ContextVar("request_id", default="-")


def get_request_id() -> str:
    """当前请求 id（非请求上下文内返回 '-'）。"""
    return _request_id.get()


class RequestIdLogFilter(logging.Filter):
    """把当前请求 id 注入 LogRecord.request_id。"""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id.get()
        return True


class RequestIdMiddleware:
    """纯 ASGI 中间件：读入/生成 → ContextVar 注入 → 响应头回写。"""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = ""
        for key, value in scope.get("headers", []):
            if key == b"x-request-id":
                request_id = value.decode("latin-1")
                break
        if not request_id:
            request_id = uuid.uuid4().hex

        started = False

        async def send_wrapper(message):
            nonlocal started
            if message["type"] == "http.response.start" and not started:
                started = True
                headers = [
                    (k, v) for k, v in message.get("headers", []) if k.lower() != b"x-request-id"
                ]
                headers.append((b"x-request-id", request_id.encode("latin-1")))
                message["headers"] = headers
            await send(message)

        token = _request_id.set(request_id)
        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            _request_id.reset(token)
