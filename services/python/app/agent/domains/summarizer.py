"""会话滚动摘要域（docs/26 §10.3①：ai4u summarizer 的 VocalVerse 版，摘要双轨）。

双轨：近 RECENT_N=6 条原文保留 + 更早消息增量压缩为一条滚动摘要（落 sessions.summary），
每次回合注入 ContextBuilder 的 user 尾部 [context]（**绝不进 system**——POC 铁证，
docs/26 §9.2）；收尾时 final summary 覆盖写入 complete_session。

魔数溯源（ai4u P1-12 同款，调整前重估）：
- TRIGGER_MESSAGES=4：增量压缩粒度——成本 × 新鲜度折中；
- SOURCE_LIMIT=40：单次压缩输入原始消息上限（超出部分由既有摘要承接）；
- 首尾保底 300/100：长消息关键信息常在尾部（结论/约定）——防永久丢失；
- recentN=6：保留原文窗口（与 ContextBuilder「Recent turns」一致，避免重复注入）。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import select

from app.db import get_session_factory
from app.models import ScenarioMessage
from app.models import Session as DbSession

logger = logging.getLogger("vocalverse")

TRIGGER_MESSAGES = 4
SOURCE_LIMIT = 40
RECENT_N = 6
SUMMARY_TARGET_LEN = 300
SUMMARY_MAX_TOKENS = 400
MSG_HEAD_KEEP = 300
MSG_TAIL_KEEP = 100
RETRY_MAX = 1
RETRY_BACKOFF_S = 1.5

_PROMPT_SYSTEM = (
    "You are a conversation summarizer for an English speaking-practice role-play. "
    "Compress the older turns into ONE coherent rolling summary. Requirements:\n"
    f"1. At most {SUMMARY_TARGET_LEN} characters.\n"
    "2. Keep facts, the learner's target expressions, difficulty trend, and emotional tone.\n"
    "3. Never list every turn; keep only what matters long-term.\n"
    "4. Reply with the summary text ONLY, no prefix, no quotes."
)


def _clip(text: str) -> str:
    if len(text) > MSG_HEAD_KEEP + MSG_TAIL_KEEP:
        return f"{text[:MSG_HEAD_KEEP]}\n…（中略）…\n{text[-MSG_TAIL_KEEP:]}"
    return text


class SummarizerService:
    """每会话一把进程内锁；防并发重写；失败落 summary_failed_at（前端提示 + 下次自动重试）。"""

    def __init__(self, llm) -> None:
        self._llm = llm
        self._locks: set[int] = set()

    async def maybe_summarize(self, session_id: int) -> None:
        """回合落库后调用（条件满足才压缩；任何异常不阻塞）。"""
        if session_id in self._locks:
            return
        db = get_session_factory()()
        try:
            session = db.get(DbSession, session_id)
            if session is None:
                return
            total = db.execute(
                select(ScenarioMessage.id).where(ScenarioMessage.session_id == session_id)
            ).scalars()
            if len(list(total)) <= RECENT_N:  # 总消息数在原文窗口内 → 无需压缩
                return
            recent = list(
                db.execute(
                    select(ScenarioMessage)
                    .where(ScenarioMessage.session_id == session_id)
                    .order_by(ScenarioMessage.seq.desc())
                    .limit(RECENT_N)
                ).scalars()
            )
            if not recent:
                return
            cutoff_seq = recent[-1].seq
            if _count_since(db, session_id, session.summary_updated_at) < TRIGGER_MESSAGES:
                return
            older = list(
                db.execute(
                    select(ScenarioMessage)
                    .where(
                        ScenarioMessage.session_id == session_id,
                        ScenarioMessage.seq < cutoff_seq,
                    )
                    .order_by(ScenarioMessage.seq.desc())
                    .limit(SOURCE_LIMIT)
                ).scalars()
            )
            if not older:
                return
            older.reverse()
            text = "\n".join(f"{m.role}: {_clip(m.content or '[action]')}" for m in older)
            prompt_user = (
                f"【existing summary】\n{session.summary or ''}\n\n" if session.summary else ""
            ) + f"【messages to compress】\n{text}"

            self._locks.add(session_id)
            raw, usage = await self._chat_with_usage(prompt_user)
            if not raw or not raw.strip():
                return
            session.summary = raw.strip()[: SUMMARY_TARGET_LEN * 2]
            session.summary_updated_at = datetime.now(UTC)
            session.summary_failed_at = None
            db.commit()
            if usage:
                self._log_usage(usage, session_id)
            logger.info("session summary updated: %s", session_id)
        except Exception as exc:
            logger.warning("summary failed session=%s: %s", session_id, exc)
            try:
                if db.get(DbSession, session_id) is not None:
                    row = db.get(DbSession, session_id)
                    if row is not None:
                        row.summary_failed_at = datetime.now(UTC)
                        db.commit()
            except Exception:
                db.rollback()
        finally:
            self._locks.discard(session_id)
            db.close()

    async def _chat_with_usage(self, prompt_user: str) -> tuple[str | None, dict | None]:
        """优先 chat_with_usage（真客户端带用量）；退化普通 chat（Fake）。失败重试一次。"""
        last_err: Exception | None = None
        fn = getattr(self._llm, "chat_with_usage", None)
        for attempt in range(RETRY_MAX + 1):
            try:
                if fn is not None:
                    raw, usage = await fn(
                        [
                            {"role": "system", "content": _PROMPT_SYSTEM},
                            {"role": "user", "content": prompt_user},
                        ],
                        temperature=0.3,
                        max_tokens=SUMMARY_MAX_TOKENS,
                    )
                    return raw, usage
                raw = await self._llm.chat(
                    [
                        {"role": "system", "content": _PROMPT_SYSTEM},
                        {"role": "user", "content": prompt_user},
                    ],
                    temperature=0.3,
                    max_tokens=SUMMARY_MAX_TOKENS,
                )
                return raw, None
            except Exception as exc:  # noqa: PERF203
                last_err = exc
                if attempt < RETRY_MAX:
                    await asyncio.sleep(RETRY_BACKOFF_S)
        if last_err:
            raise last_err
        return None, None

    @staticmethod
    def _log_usage(usage: dict, session_id: int) -> None:
        try:
            from app.agent.domains.usage import log_usage

            log_usage("summary", usage, meta={"session_id": session_id})
        except Exception as exc:
            logger.debug("usage log skipped: %s", exc)

    def summary_for(self, session_id: int) -> str | None:
        """同步读取滚动摘要（构建上下文用）；无摘要返回 None。"""
        return get_session_summary(session_id)


def get_session_summary(session_id: int) -> str | None:
    """模块级读取滚动摘要（orchestrator 构建上下文时用，避免为一次读建服务实例）。"""
    db = get_session_factory()()
    try:
        row = db.execute(
            select(DbSession.summary).where(DbSession.id == session_id)
        ).scalar_one_or_none()
        return (row or "").strip() or None
    finally:
        db.close()


def _count_since(db, session_id: int, summary_updated_at) -> int:
    """距上次摘要更新的新消息数（首轮 = 0 → 由 len(recent)>RECENT_N 保证首轮必然触发）。"""
    if summary_updated_at is None:
        return 999  # 首轮：直接压缩（外层已有 len(recent) > RECENT_N 门槛）
    rows = db.execute(
        select(ScenarioMessage.seq).where(
            ScenarioMessage.session_id == session_id,
            ScenarioMessage.created_at > summary_updated_at,
        )
    ).scalars()
    return len(list(rows))


__all__ = [
    "SummarizerService",
    "get_session_summary",
    "RECENT_N",
    "TRIGGER_MESSAGES",
    "SOURCE_LIMIT",
]
