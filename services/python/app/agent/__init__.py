"""VocalVerse Agent 框架（docs/26：对齐 ai4u 分层架构的模式迁移，代码全部自研）。

分层：
- runtime/     回合执行（turn_runner）、上下文组装（context_builder）、
                META 权威执行（meta_executor）
- domains/     学习者画像（learner）等领域逻辑
- hooks/       回合后兜底钩子（后续）
- scenes/      场景门面（后续收敛）
"""

from __future__ import annotations

__all__: list[str] = []
