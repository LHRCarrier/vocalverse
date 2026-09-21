"""VocalVerse Agent 框架（docs/26：对齐 ai4u 分层架构的模式迁移，代码全部自研）。

分层（2026-09-21 酒馆迁移后的现状）：
- runtime/     回合执行（turn_runner：LLM 流式 + META 拆分/泄漏门）；酒馆 DM 的
                工具循环在 app/trpg/turn.py（走 LLMClient.stream_with_tools）；
- domains/     领域逻辑（当前为空；学习者画像随场景对话移除）；
- scenes/      （未启用）
"""

from __future__ import annotations

__all__: list[str] = []
