"""X-Request-Id 跨服务贯通测试（docs/50 §9.2 断点 1）。

修复前：Python → Java 的内部调用只带 ``Authorization``，correlation id 在**每一跳**断掉，
控制台的"管理员操作 → Java → Python"审计链无法 join。
"""

from __future__ import annotations

import pytest
from app.core import internal_client, trace


@pytest.fixture
def request_id():
    """在请求上下文外模拟"当前请求 id"。"""
    token = trace._request_id.set("req-abc123")
    yield "req-abc123"
    trace._request_id.reset(token)


def test_internal_headers_include_request_id(request_id: str) -> None:
    headers = internal_client.internal_headers()
    assert headers["X-Request-Id"] == request_id
    assert headers["Authorization"].startswith("Bearer ")


def test_internal_headers_omit_placeholder_outside_request() -> None:
    """非请求上下文（后台任务/脚本）时 id 是 '-'：不注入，避免把 Java 侧 MDC 覆盖成占位符。"""
    assert trace.get_request_id() == "-"
    assert "X-Request-Id" not in internal_client.internal_headers()


def test_post_internal_sends_request_id(monkeypatch, request_id: str) -> None:
    captured: dict = {}

    class _Resp:
        def raise_for_status(self) -> None:
            return None

    def _fake_post(url, **kwargs):
        captured["url"] = url
        captured["headers"] = kwargs["headers"]
        return _Resp()

    monkeypatch.setattr(internal_client.httpx, "post", _fake_post)
    internal_client.post_internal("/internal/level", {"level": "B1"})
    assert captured["headers"]["X-Request-Id"] == request_id


def test_post_internal_still_raises_on_error(monkeypatch) -> None:
    """回归 P0-6：内部调用失败必须抛，不许静默吞（吞掉就是档位回写 100% 断链）。"""

    class _Resp:
        def raise_for_status(self) -> None:
            raise RuntimeError("500")

    monkeypatch.setattr(internal_client.httpx, "post", lambda url, **kw: _Resp())
    with pytest.raises(RuntimeError):
        internal_client.post_internal("/internal/level", {})
