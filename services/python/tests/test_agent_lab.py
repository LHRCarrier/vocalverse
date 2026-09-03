"""Agent Lab（test-only 测试台）可用性 + 无影响验证（docs/26 §8）。

- 默认关闭：路由未注册 → 404，打开 /openapi.json 无 agent-lab（契约快照零影响）；
- 函数级：_run_turn 用 FakeLLM 走通「流式 META → 命中」与「无 META → 补偿」两条路径。
"""

from __future__ import annotations

import pytest
from app.api.routes.agent_lab import AgentTurnRequest, _run_turn
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
    """流式不带 META → 触发补偿（chat 返回无 JSON → 补偿失败但流程不崩）。"""

    async def stream(self, messages, temperature=0.6, max_tokens=512):
        yield "That'll be three dollars, please."


@pytest.mark.anyio
async def test_run_turn_compensates_on_missing_meta(monkeypatch) -> None:
    state = SessionState(session_id=0, kind="dialog")
    out = await _run_turn(_req(), state, "I'd like a coffee please", 1, _NoMetaLLM())
    assert out.compensated is True  # 走了补偿分支
    assert out.reply == "That'll be three dollars, please."  # 回复不丢失
    # 规则通道与 META 无关：无 META 时命中仍由规则权威给出（这正是设计——META 缺失只丢
    # coach_note/grammar/LLM 兜底命中，不丢规则命中）
    assert any(h.get("phrase") == "I'd like a coffee, please." for h in out.corpus_hits)
