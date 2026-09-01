"""答辩域：defense_profiles（Python 写；docs/14 §6.1 / docs/17 §4-D2 拍板）。

- 用户自定义答辩档案：论文输入 + 异步生成的知识包（三级题库/提问依据/要点/追问链）；
- 删除语义：**软删 + 脱敏**（status='deleted' + 清空 thesis_text/knowledge_bank），
  保留行保历史归因与审计，与 docs/10 P7「业务表禁止物理删除」一致；
- knowledge_bank 入库前必须过 Pydantic schema（docs/14 §4.2 校验 6 条），
  禁止将畸形 JSONB 写库；
- thesis_text 为可选（≤8000 字，服务层硬校验）；全文不进 knowledge_bank。
"""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, bigint_pk, jsonb


class DefenseProfile(TimestampMixin, Base):
    """一次用户自定义论文答辩档案（Python 写）。

    - emphasis：提问倾向（基础为主/均衡/发散为主），驱动知识包生成；
    - knowledge_bank：{bank_version, questions:[{id,tier,question,basis,key_points[],followups[]}],
      suggested_order[]}——含每问「提问依据 basis」（docs/14 §4.2 审计要求）；
    - bank_version：重新生成 +1 不覆盖（沿用 scenarios.prompt_version 约定）；
    - status：active | deleted | generating | failed（知识包生成态；deleted 时敏感字段已清空）。
    """

    __tablename__ = "defense_profiles"

    id: Mapped[int] = bigint_pk()
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    abstract: Mapped[str] = mapped_column(Text, nullable=False)
    outline: Mapped[str] = mapped_column(Text, nullable=False)
    highlights: Mapped[str] = mapped_column(Text, nullable=False)
    thesis_text: Mapped[str | None] = mapped_column(Text)  # 可选 ≤8000 字（服务层校验）
    question_count: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("6")
    )
    emphasis: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'balanced'")
    )
    knowledge_bank: Mapped[dict] = mapped_column(
        jsonb(), nullable=False, server_default=text("'{}'")
    )
    bank_version: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("1")
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'active'"))

    __table_args__ = (
        CheckConstraint("question_count BETWEEN 5 AND 8", name="question_count"),
        CheckConstraint("emphasis IN ('basic', 'balanced', 'divergent')", name="emphasis"),
        CheckConstraint("status IN ('active', 'deleted', 'generating', 'failed')", name="status"),
        Index("ix_defense_profiles_user_status", "user_id", "status"),
    )
