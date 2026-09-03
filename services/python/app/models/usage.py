"""LLM 用量日志（迁移 0004；对照 ai4u usage_log，docs/26 §10.3②）。

Python 写（唯一写方 app.agent.domains.usage）；M3 报表成本溯源；
source：turn（回合）/ meta_compensate（META 补偿）/ summary（滚动摘要）/ conclude（收尾总结）。
"""

from __future__ import annotations

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, bigint_pk


class UsageLog(TimestampMixin, Base):
    __tablename__ = "usage_log"

    id: Mapped[int] = bigint_pk()
    source: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # turn | meta_compensate | summary | conclude
    model: Mapped[str] = mapped_column(String(64), nullable=False, server_default="")
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    meta: Mapped[str | None] = mapped_column(Text)  # 附加信息（session_id/user_id 等 JSON 字符串）
