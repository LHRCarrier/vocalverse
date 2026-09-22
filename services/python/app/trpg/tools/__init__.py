"""酒馆工具集（2026-09-22 重构：平铺 if/elif → 注册表 + 一工具一文件）。

新增工具三步：
1. 新建本目录 ``<tool_name>.py``：写 schema 常量 + ``async def handle(args, campaign_id)``；
2. 文件末尾 ``register(ToolSpec(name="<tool_name>", schema=..., handler=handle))``；
3. 在本文件 import 该模块（触发注册副作用）并加进 ``__all__``。

注册顺序 = :func:`build_trpg_tools` 下发顺序（保持稳定，便于测试断言）：
基础三件（roll_dice / set_scene / show_portrait）+ 闭环十件
（tick_clock / complete_quest / enter_character / exit_character / attack / use_item /
grant_item / start_encounter / next_turn / end_encounter，docs/56 §3 + docs/57 §3.1）。
执行契约见 :mod:`app.trpg.tools.registry`；``turn.py`` 只依赖 build/execute 两个入口。
"""

from app.trpg.tools import (  # noqa: F401  # 注册副作用
    attack,
    complete_quest,
    end_encounter,
    enter_character,
    exit_character,
    grant_item,
    next_turn,
    roll_dice,
    set_scene,
    show_portrait,
    start_encounter,
    tick_clock,
    use_item,
)
from app.trpg.tools.registry import (
    ToolSpec,
    build_trpg_tools,
    execute_tool,
    parse_tool_args,
    register,
)

__all__ = [
    "ToolSpec",
    "build_trpg_tools",
    "execute_tool",
    "parse_tool_args",
    "register",
    "attack",
    "complete_quest",
    "end_encounter",
    "enter_character",
    "exit_character",
    "grant_item",
    "next_turn",
    "roll_dice",
    "set_scene",
    "show_portrait",
    "start_encounter",
    "tick_clock",
    "use_item",
]
