"""Agent Lab（test-only 测试台）可用性 + 无影响验证（docs/26 §8）。

- 默认关闭：路由未注册 → 404，打开 /openapi.json 无 agent-lab（契约快照零影响）；
- 函数级：_run_turn 用 FakeLLM 走通「流式 META → 命中」与「无 META → 补偿」两条路径。
"""

from __future__ import annotations

import pytest
from app.api.routes.agent_lab import AgentTurnRequest, _run_turn, build_context_for_display
from app.audio.stubs import FakeLLMClient
from app.practice.state import SessionState


def _req(**kw) -> AgentTurnRequest:
    return AgentTurnRequest(
        scenario_prompt="You are Maya, a friendly barista.",
        corpus_text="I'd like a coffee, please.|请给我来杯咖啡",
        difficulty=2,
        user_text="I'd like a coffee please",
        **kw,
    )


def test_agent_lab_disabled_returns_404(client) -> None:
    """默认 agent_lab_enabled=False：路由未注册 → 404（对其它代码零影响）。"""
    r = client.post("/api/v1/agent-lab/turn", json={})
    assert r.status_code == 404
    schemas = client.get("/openapi.json").json()
    assert "/api/v1/agent-lab" not in schemas["paths"]  # include_in_schema=False：契约快照零 diff


def test_effective_by_turn_last_round_auto() -> None:
    """回归：连跑末轮自动视为「回合上限已到」（POC 冒烟同款 concluded_by_turn=(i>=n)）。

    修复前 /turns 全轮共用表单开关（默认 False）→ 冒烟第 5 轮上下文永远是
    "Turn limit reached: False" → conclude 必为 false（2026-09-03 实测 5/5 false）。
    """
    from app.api.routes.agent_lab import _effective_by_turn

    assert _effective_by_turn(False, 4, 5) is False  # 非末轮不注入
    assert _effective_by_turn(False, 5, 5) is True  # 末轮自动注入
    assert _effective_by_turn(True, 2, 5) is True  # 勾选 → 全轮 True（保留原语义）


def test_display_payload_is_flat_text() -> None:
    """回归：/turn 展示载荷 system/user 必须是**字符串**（前端 NCode 直显原文）。

    修复前 /turn 把 build_context_for_display 的 {system,user} 再包一层 →
    data.system 变成对象 → 前端渲染 [object Object]、user 卡片空白（2026-09-03 实测）。
    """
    state = SessionState(session_id=0, kind="dialog")
    disp = build_context_for_display(_req(), state)
    assert set(disp) == {"system", "user"}
    assert isinstance(disp["system"], str) and disp["system"].startswith("You are Maya")
    assert isinstance(disp["user"], str) and "[context]" in disp["user"]


@pytest.mark.anyio
async def test_run_turn_meta_via_fake_stream(monkeypatch) -> None:
    """FakeLLM 流式自带 META → meta_ok=True、规则命中。"""
    from app.audio.stubs import FakeLLMClient as Fake

    state = SessionState(session_id=0, kind="dialog")
    out = await _run_turn(_req(), state, "I'd like a coffee please", 1, Fake())
    assert out.meta_ok is True
    assert out.compensated is False
    assert any(h.get("phrase") == "I'd like a coffee, please." for h in out.corpus_hits)


class _NoMetaLLM(FakeLLMClient):
    """流式不带 META（覆盖 stream_rich；True实现 TurnRunner 走富流）→ 触发补偿。"""

    async def stream_rich(self, messages, temperature=0.6, max_tokens=512):
        yield ("delta", "That'll be three dollars, please.")
        yield ("usage", {"model": "fake", "prompt_tokens": 10, "completion_tokens": 5})


@pytest.mark.anyio
async def test_run_turn_compensates_on_missing_meta(monkeypatch) -> None:
    state = SessionState(session_id=0, kind="dialog")
    out = await _run_turn(_req(), state, "I'd like a coffee please", 1, _NoMetaLLM())
    assert out.compensated is True  # 走了补偿分支
    assert out.reply == "That'll be three dollars, please."  # 回复不丢失
    # 规则通道与 META 无关：无 META 时命中仍由规则权威给出（这正是设计——META 缺失只丢
    # coach_note/grammar/LLM 兜底命中，不丢规则命中）
    assert any(h.get("phrase") == "I'd like a coffee, please." for h in out.corpus_hits)
