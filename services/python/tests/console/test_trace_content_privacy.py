"""内容捕获隐私测试（docs/50 §14.2 第 6 条 + 合规硬禁采清单）。

三条闸门逐条验证：

1. ``APP_LLM_TRACE_CONTENT_CAPTURE=false``（默认）→ ``llm_span_contents`` **零行**，
   ``llm_traces.content_captured=false``；
2. 开启时普通 kind 能落内容（证明第 1 条不是"因为压根写不进去"而绿）；
3. 开启时 ``kind='defense'`` **仍然零行** —— 答辩链路整条 prompt 是用户论文正文，
   脱敏规则（邮箱/手机号/密钥）对开放文本无能为力，只能硬禁采（docs/06 §9.7 红线）。
"""

from __future__ import annotations

import pytest
from app.console.trace.recorder import note_llm_request, note_llm_result, span, trace
from app.console.trace.redact import redact
from app.console.trace.sink import reset_sink_for_tests
from app.core.config import get_settings
from sqlalchemy import func, select

from .helpers import console_headers


@pytest.fixture
def capture_on(monkeypatch):
    monkeypatch.setattr(get_settings(), "llm_trace_content_capture", True)
    return True


@pytest.fixture
def capture_off(monkeypatch):
    monkeypatch.setattr(get_settings(), "llm_trace_content_capture", False)
    return False


def _run_trace(kind: str, prompt: str, answer: str):
    """跑一条带内容的 trace，并同步写出（走真实 sink.write_batch 路径）。"""
    sink = reset_sink_for_tests()
    with trace(kind=kind) as rec, span("LLM"):
        note_llm_request("deepseek-chat", [{"role": "user", "content": prompt}])
        note_llm_result(output_text=answer, finish_reason="stop", ttft_ms=12)
    assert rec is not None
    batch = sink._take_batch()
    assert batch == [rec]
    sink.write_batch(batch)
    return rec


def _content_rows() -> int:
    from app.db import get_session_factory
    from app.models.console_telemetry import LlmSpanContent

    db = get_session_factory()()
    try:
        return int(db.execute(select(func.count()).select_from(LlmSpanContent)).scalar() or 0)
    finally:
        db.close()


def _trace_row(trace_id: str):
    from app.db import get_session_factory
    from app.models.console_telemetry import LlmTrace

    db = get_session_factory()()
    try:
        return db.execute(select(LlmTrace).where(LlmTrace.trace_id == trace_id)).scalar_one()
    finally:
        db.close()


def test_capture_disabled_writes_zero_content_rows(capture_off) -> None:
    """默认关：内容表必须零行，且 trace 声明 content_captured=false。"""
    rec = _run_trace("turn", "my secret prompt user@example.com", "the answer")
    assert _content_rows() == 0, "内容捕获关闭时 llm_span_contents 必须零行"
    assert _trace_row(rec.trace_id).content_captured is False


def test_capture_enabled_writes_rows_for_normal_kind(capture_on) -> None:
    """开启后普通 kind 能落内容（反向证明上一条不是假绿）。"""
    rec = _run_trace("turn", "hello user@example.com", "the answer")
    assert _content_rows() == 2  # input + output
    assert _trace_row(rec.trace_id).content_captured is True


def test_capture_enabled_but_defense_kind_writes_zero_rows(capture_on) -> None:
    """**硬禁采**：即使内容捕获开启，答辩（defense）trace 也一个内容字都不落。"""
    rec = _run_trace("defense", "我的论文全文：……", "generated bank json")
    assert _content_rows() == 0, "defense 链路必须整条禁采内容"
    row = _trace_row(rec.trace_id)
    assert row.content_captured is False
    assert row.attrs["content_capture"] == "denied"
    assert row.attrs["content_capture_reason"] == "deny_list:thesis-bearing-kind"


def test_redaction_masks_secrets_and_marks_row(capture_on) -> None:
    """脱敏：邮箱/手机号/sk-*/Bearer 被替换，且行标 redacted=true。"""
    from app.db import get_session_factory
    from app.models.console_telemetry import LlmSpanContent

    text = "mail a.b@example.com phone 13800138000 key sk-abcdefgh12345678 auth Bearer abcdefgh1234"
    clean, hit = redact(text)
    assert hit is True
    assert "a.b@example.com" not in clean
    assert "13800138000" not in clean
    assert "sk-abcdefgh12345678" not in clean
    assert "Bearer abcdefgh1234" not in clean

    _run_trace("turn", text, "ok")
    db = get_session_factory()()
    try:
        rows = list(db.execute(select(LlmSpanContent)).scalars())
    finally:
        db.close()
    assert rows
    inputs = [r for r in rows if r.direction == "input"]
    assert inputs and all(r.redacted is True for r in inputs), "命中脱敏的输入行必须标 redacted"
    assert all("a.b@example.com" not in r.content for r in rows)


def test_truncation_sets_flag(capture_on, monkeypatch) -> None:
    """超过 content_max_chars 截断并置 truncated=true（DSH 默认 128000）。"""
    from app.db import get_session_factory
    from app.models.console_telemetry import LlmSpanContent

    monkeypatch.setattr(get_settings(), "llm_trace_content_max_chars", 100)
    _run_trace("turn", "x" * 500, "y" * 500)
    db = get_session_factory()()
    try:
        rows = list(db.execute(select(LlmSpanContent)).scalars())
    finally:
        db.close()
    assert rows
    assert all(r.truncated is True for r in rows)
    assert all(len(r.content) == 100 for r in rows)


# ---------------------------------------------------------------------------
# 端点层：独立权限码 + 读取留痕 + 功能位
# ---------------------------------------------------------------------------
def test_contents_endpoint_requires_separate_permission(client, capture_on) -> None:
    """读取内容需 ``ops:trace:content:read``（只有 ``ops:trace:read`` → 46002）。"""
    rec = _run_trace("turn", "hello", "world")
    url = f"/api/v1/console/ops/traces/{rec.trace_id}/contents"

    denied = client.get(url, headers=console_headers(perms=("ops:trace:read",)))
    assert denied.status_code == 403
    assert denied.json()["data"]["required"] == "ops:trace:content:read"

    allowed = client.get(url, headers=console_headers(perms=("ops:trace:content:read",)))
    assert allowed.status_code == 200
    data = allowed.json()["data"]
    assert data["captured"] is True
    assert data["total"] == 2


def test_content_read_is_audited(client, capture_on) -> None:
    """每次内容读取都要留痕（best-effort：``llm_traces.attrs.content_reads`` + 日志）。"""
    rec = _run_trace("turn", "hello", "world")
    url = f"/api/v1/console/ops/traces/{rec.trace_id}/contents"
    resp = client.get(url, headers=console_headers(perms=("ops:trace:content:read",)))
    assert resp.status_code == 200

    row = _trace_row(rec.trace_id)
    reads = row.attrs.get("content_reads") or []
    assert len(reads) == 1, "内容读取必须留痕（看别人的 prompt 是留痕行为）"
    assert reads[0]["action"] == "ops.trace.content.read"
    assert reads[0]["admin_id"] == 7


def test_contents_endpoint_reports_not_captured(client, capture_off) -> None:
    """未捕获 → ``data.captured=false``（界面据此显示"未捕获"而不是空表）。"""
    rec = _run_trace("turn", "hello", "world")
    resp = client.get(
        f"/api/v1/console/ops/traces/{rec.trace_id}/contents",
        headers=console_headers(perms=("ops:trace:content:read",)),
    )
    data = resp.json()["data"]
    assert data["captured"] is False
    assert data["items"] == []


def test_trace_endpoints_return_46014_when_trace_disabled(client, monkeypatch) -> None:
    """``APP_LLM_TRACE_ENABLED=false`` → trace 端点 46014（功能位闸门）。"""
    monkeypatch.setattr(get_settings(), "llm_trace_enabled", False)
    resp = client.get(
        "/api/v1/console/ops/traces", headers=console_headers(perms=("ops:trace:read",))
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == 46014
