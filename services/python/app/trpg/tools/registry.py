"""酒馆工具注册表：ToolSpec 定义 + 注册 / 下发 / 执行（2026-09-22 从平铺 tools.py 抽离）。

契约（与旧 ``app/trpg/tools.py`` 逐字对齐，SSE / 前端无感）：
- :func:`build_trpg_tools` 返回**注册顺序**的 OpenAI function schema 列表（DM 工具面）；
- :func:`execute_tool` 按名字分发到 handler；参数坏 JSON 宽容解析为 ``{}``（handler 报可读错误）；
- handler 返回 ``{text, status_stage?}``：text 回填模型；status_stage 由 ``turn.py`` 转 SSE status；
- 未注册工具 / handler 抛异常 → 返回错误文本，**不向上抛**（单个工具失败不打断回合）。

新增工具见 :mod:`app.trpg.tools` 包文档（一工具一文件 + register，注册顺序即下发顺序）。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("vocalverse")

ToolArgs = dict[str, Any]
ToolOutcome = dict[str, Any]
ToolHandler = Callable[[ToolArgs, int], Awaitable[ToolOutcome]]


@dataclass(frozen=True)
class ToolSpec:
    """单个工具的完整定义（schema 与 handler 同文件，避免两处漂移）。"""

    name: str
    schema: dict[str, Any]
    handler: ToolHandler


_REGISTRY: dict[str, ToolSpec] = {}


def register(spec: ToolSpec) -> ToolSpec:
    """注册工具；重复名直接报错（同进程内每个工具只有一个真源）。"""
    if spec.name in _REGISTRY:
        raise ValueError(f"工具重复注册：{spec.name}")
    _REGISTRY[spec.name] = spec
    return spec


def build_trpg_tools() -> list[dict[str, Any]]:
    """DM 工具面：注册顺序即下发顺序（顺序稳定 = 测试可断言 / 利于 prompt 缓存）。"""
    return [spec.schema for spec in _REGISTRY.values()]


def parse_tool_args(raw: str) -> ToolArgs:
    """宽容解析工具参数 JSON；坏输入返回 {}（执行层再报可读错误）。"""
    try:
        parsed = json.loads(raw or "{}")
    except (ValueError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


async def execute_tool(name: str, raw_args: str, campaign_id: int) -> ToolOutcome:
    """执行工具调用；返回 ``{text, status_stage?}``（工具文本回填模型，status 供 SSE 指示）。"""
    spec = _REGISTRY.get(name)
    if spec is None:
        return {"text": f"未知工具：{name}（本场景未注册）。"}
    try:
        return await spec.handler(parse_tool_args(raw_args), campaign_id)
    except Exception as exc:  # noqa: BLE001 - 工具失败不打断回合（模型如实告知玩家）
        logger.exception("酒馆工具执行失败 name=%s campaign_id=%s", name, campaign_id)
        return {"text": f"工具 {name} 执行失败：{exc}。请如实告诉玩家本回合该动作尚未生效。"}
