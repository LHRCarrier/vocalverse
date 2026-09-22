"""酒馆工具注册表契约（2026-09-22 从平铺 tools.py 抽离的配套用例）。

覆盖：
- 内置工具注册顺序 / schema 形状（下发顺序稳定 = turn 测试与 prompt 缓存的前提）；
- 参数宽容解析（坏 JSON → {}，不抛）；
- 未注册工具 → 错误文本（不抛）；
- handler 抛异常 → 错误文本（工具失败不打断回合，turn.py 依赖此契约）；
- 重复注册报错；handler 收到解析后的 args 与 campaign_id。
"""

from __future__ import annotations

import asyncio

import pytest
from app.trpg import tools
from app.trpg.tools import registry


def _isolated_registry(monkeypatch) -> None:
    """每个用例用注册表副本：register 副作用不跨用例泄漏。"""
    monkeypatch.setattr(registry, "_REGISTRY", dict(registry._REGISTRY))


def test_builtin_tools_order_and_schema_shape():
    schemas = tools.build_trpg_tools()
    assert [s["function"]["name"] for s in schemas] == [
        "roll_dice",
        "set_scene",
        "show_portrait",
        # 闭环九件（docs/56 §3；顺序 = BUILTIN_TOOL_ORDER）
        "tick_clock",
        "complete_quest",
        "enter_character",
        "exit_character",
        "attack",
        "use_item",
        "start_encounter",
        "next_turn",
        "end_encounter",
    ]
    for schema in schemas:
        assert schema["type"] == "function"
        assert schema["function"]["description"]
        assert schema["function"]["parameters"]["type"] == "object"


def test_parse_tool_args_tolerates_bad_input():
    assert tools.parse_tool_args("") == {}
    assert tools.parse_tool_args("{oops") == {}
    assert tools.parse_tool_args("[1, 2]") == {}
    assert tools.parse_tool_args('"text"') == {}
    assert tools.parse_tool_args('{"dice": "d20"}') == {"dice": "d20"}


def test_execute_unknown_tool_returns_text():
    out = asyncio.run(tools.execute_tool("nope", "{}", 1))
    assert "未知工具" in out["text"] and "nope" in out["text"]


def test_execute_tool_handler_error_is_contained(monkeypatch):
    _isolated_registry(monkeypatch)

    async def boom(args, campaign_id):
        raise RuntimeError("炸了")

    registry.register(tools.ToolSpec(name="boom", schema={}, handler=boom))
    out = asyncio.run(tools.execute_tool("boom", "{}", 1))
    assert "boom" in out["text"] and "尚未生效" in out["text"]


def test_register_rejects_duplicate_name(monkeypatch):
    _isolated_registry(monkeypatch)

    async def noop(args, campaign_id):
        return {"text": ""}

    with pytest.raises(ValueError, match="重复注册"):
        registry.register(tools.ToolSpec(name="roll_dice", schema={}, handler=noop))


def test_execute_tool_passes_parsed_args_and_campaign(monkeypatch):
    _isolated_registry(monkeypatch)
    seen: dict = {}

    async def probe(args, campaign_id):
        seen.update(args=args, campaign_id=campaign_id)
        return {"text": "ok", "status_stage": "probe"}

    registry.register(tools.ToolSpec(name="probe", schema={}, handler=probe))
    out = asyncio.run(tools.execute_tool("probe", '{"scene": "酒馆"}', 42))
    assert seen == {"args": {"scene": "酒馆"}, "campaign_id": 42}
    assert out == {"text": "ok", "status_stage": "probe"}
