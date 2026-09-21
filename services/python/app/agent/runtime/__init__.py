"""Agent 运行时层（docs/26 runtime）：当前仅 turn_runner（自由对话/答辩/影子共用）。

2026-09-21（酒馆迁移）：context_builder（对话上下文组装）与 meta_executor（META 权威执行，
覆盖度/教练笔记/收尾判定）随英语场景对话移除；酒馆走独立工具循环（app/trpg/turn.py）。
"""

from __future__ import annotations

__all__: list[str] = []
