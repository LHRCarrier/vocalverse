"""会话运行时状态（docs/14 §3.2/§6.2：Redis session:{id} TTL 30min + 进程内降级）。

- 只存**运行时事实**（state/current_turn/next_seq/digest/锁），权威历史永远在
  scenario_messages（不可变只 INSERT）——刷新恢复（P2 延期）时据此重建；
- 会话锁：SETNX 语义（防双开/重复提交破坏 (session_id, seq) 唯一），每会话一把；
- Redis 断 → 内存 TTL 实现（进程内），语义与 docs/06 §10.2 降级一致。
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

TTL_S = 30 * 60  # 30min（docs/06 §10.2）
LOCK_TTL_S = 30


@dataclass
class SessionState:
    session_id: int
    kind: str  # dialog | defense
    state: str = "opening"  # opening|listening|processing|responding|awaiting_user|concluded
    current_turn: int = 0  # 已完成的用户轮数（user_turn_count 增量）
    next_seq: int = 1  # scenario_messages 下一个 seq
    digest: list[str] = field(default_factory=list)  # 3 轮滚动摘要（每轮 1 行）
    assembled: dict = field(default_factory=dict)  # LLM 组装上下文（角色/scenario 等）
    last_action: str = "normal"  # normal|retry|hint|demo|abandon
    failed_streak: int = 0  # 连续低质量轮数（触发 L2 代说）
    corpus_done: list[str] = field(default_factory=list)  # 已命中短语（摘要提示"换表达"）
    tier_index: int = 0  # defense：题目进度
    answered: list[int] = field(default_factory=list)  # defense：已答题目 id 集
    question_id: int | None = None  # defense：当前题 id
    pending: dict | None = None  # defense：等级阶梯选出的下一题
    updated_at: float = field(default_factory=time.time)


class StateStore:
    """内存后端（Redis 可插拔；M2 先落地内存，接口稳定后切 Redis）。"""

    def __init__(self) -> None:
        self._data: dict[int, tuple[SessionState, float]] = {}
        self._locks: dict[int, tuple[str, float]] = {}  # session_id -> (nonce, expires)

    # ---- 状态（TTL 30min） ----
    async def get(self, session_id: int) -> SessionState | None:
        item = self._data.get(session_id)
        if item is None:
            return None
        state, expires = item
        if expires < time.time():
            self._data.pop(session_id, None)
            return None
        return state

    async def put(self, state: SessionState) -> None:
        self._data[state.session_id] = (state, time.time() + TTL_S)

    async def delete(self, session_id: int) -> None:
        self._data.pop(session_id, None)
        self._locks.pop(session_id, None)

    # ---- 会话锁（SETNX 语义） ----
    async def acquire_lock(self, session_id: int) -> str | None:
        """获取会话锁；成功返回 nonce（随后 turn 请求须携带），失败返回 None（409 冲突）。"""
        now = time.time()
        held = self._locks.get(session_id)
        if held is not None and held[1] > now:
            return None  # 已被持有（含本会话并发请求 → 拒绝，客户端应幂等重试）
        nonce = uuid.uuid4().hex
        self._locks[session_id] = (nonce, now + LOCK_TTL_S)
        return nonce

    async def release_lock(self, session_id: int, nonce: str) -> None:
        held = self._locks.get(session_id)
        if held is not None and held[0] == nonce:
            self._locks.pop(session_id, None)


_store: StateStore | None = None


def get_state_store() -> StateStore:
    global _store
    if _store is None:
        _store = StateStore()
    return _store
