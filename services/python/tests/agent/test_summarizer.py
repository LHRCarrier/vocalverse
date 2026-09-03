"""摘要双轨 + 用量记账单测（docs/26 §10.3①/②，迁移 0004）。

覆盖：触发门槛（>RECENT_N 才压）、增量窗口与首尾保底、失败标记、summary_for、
log_usage 落库、TurnRunner 富流用量透传。修复前必失败：迁移 0004 之前本域不存在。
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from app.agent.domains.summarizer import SummarizerService, get_session_summary
from app.agent.domains.usage import log_usage
from app.db import get_session_factory
from app.models import ScenarioMessage, UsageLog, User
from app.models import Session as DbSession
from app.models.base import SessionKinds, SessionStatus
from sqlalchemy import select


def _seed_session(n_msgs: int) -> int:
    """建 1 个会话 + n 条消息（seq 1..n）。"""
    db = get_session_factory()()
    try:
        u = User(username=f"su{uuid4().hex[:8]}", nickname="n", password_hash="x")
        db.add(u)
        db.flush()
        sess = DbSession(
            user_id=int(u.id),
            kind=SessionKinds.DIALOG,
            status=SessionStatus.COMPLETED,
            started_at=datetime.now(UTC),
        )
        db.add(sess)
        db.flush()
        sid = int(sess.id)
        for i in range(1, n_msgs + 1):
            db.add(
                ScenarioMessage(
                    session_id=sid,
                    seq=i,
                    role="user" if i % 2 else "assistant",
                    content=f"turn-{i} content",
                )
            )
        db.commit()
        return sid
    finally:
        db.close()


class _SummaryLLM:
    async def chat(self, messages, temperature=0.7, max_tokens=512) -> str:
        return "Learner practiced ordering coffee; target expressions hit well."

    async def chat_with_usage(self, messages, temperature=0.7, max_tokens=512):
        return (
            "Learner practiced ordering coffee; target expressions hit well.",
            {"model": "fake", "prompt_tokens": 500, "completion_tokens": 40},
        )


class _FailingLLM:
    async def chat(self, messages, temperature=0.7, max_tokens=512) -> str:
        raise RuntimeError("network down")

    async def chat_with_usage(self, messages, temperature=0.7, max_tokens=512):
        raise RuntimeError("network down")


@pytest.mark.anyio
async def test_maybe_summarize_writes_summary_and_usage() -> None:
    sid = _seed_session(n_msgs=12)  # > RECENT_N(6)
    await SummarizerService(_SummaryLLM()).maybe_summarize(sid)
    db = get_session_factory()()
    try:
        row = db.execute(select(DbSession.summary).where(DbSession.id == sid)).scalar_one()
        assert "coffee" in row and row is not None
        row2 = db.execute(select(DbSession).where(DbSession.id == sid)).scalar_one()
        assert row2.summary_updated_at is not None
        assert row2.summary_failed_at is None
        # 用量记账（chat_with_usage 路径）
        usage_rows = list(db.execute(select(UsageLog)).scalars())
        assert any(r.source == "summary" and r.prompt_tokens == 500 for r in usage_rows)
    finally:
        db.close()


@pytest.mark.anyio
async def test_maybe_summarize_skips_within_window() -> None:
    sid = _seed_session(n_msgs=6)  # == RECENT_N → 原文窗口内不压缩
    await SummarizerService(_SummaryLLM()).maybe_summarize(sid)
    assert get_session_summary(sid) is None


@pytest.mark.anyio
async def test_maybe_summarize_failure_marks_flag() -> None:
    sid = _seed_session(n_msgs=10)
    await SummarizerService(_FailingLLM()).maybe_summarize(sid)
    db = get_session_factory()()
    try:
        row = db.execute(select(DbSession).where(DbSession.id == sid)).scalar_one()
        assert row.summary_failed_at is not None
        assert row.summary is None
    finally:
        db.close()


@pytest.mark.anyio
async def test_first_summary_triggers_with_few_older() -> None:
    sid = _seed_session(n_msgs=7)  # 7 > RECENT_N(6)：首轮只要窗口外有消息即压缩（ai4u 同款）
    await SummarizerService(_SummaryLLM()).maybe_summarize(sid)
    assert get_session_summary(sid) is not None


# ---------------------------------------------------------------------------
# 用量记账
# ---------------------------------------------------------------------------
def test_log_usage_writes_row() -> None:
    log_usage(
        "turn",
        {"model": "deepseek-chat", "prompt_tokens": 100, "completion_tokens": 30},
        meta={"session_id": 1},
    )
    db = get_session_factory()()
    try:
        row = db.execute(select(UsageLog)).scalar_one()
        assert row.source == "turn"
        assert row.prompt_tokens == 100 and row.completion_tokens == 30
        assert "session_id" in (row.meta or "")
    finally:
        db.close()


def test_log_usage_none_ignored() -> None:
    log_usage("turn", None)
    db = get_session_factory()()
    try:
        assert db.execute(select(UsageLog)).first() is None
    finally:
        db.close()
