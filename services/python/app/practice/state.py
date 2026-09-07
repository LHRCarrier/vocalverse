"""会话运行时状态（docs/14 §3.2/§6.2：Redis session:{id} TTL 30min + 进程内降级）。

- 只存**运行时事实**（state/current_turn/next_seq/digest/锁），权威历史永远在
  scenario_messages（不可变只 INSERT）——刷新恢复（P2 延期）时据此重建；
- 会话锁：SETNX 语义（防双开/重复提交破坏 (session_id, seq) 唯一），每会话一把；
- **P0-1（docs/19 P0-1 / 审计 R-12，2026-09-07）**：生产后端切 Redis——
  `RedisStateStore`（JSON + EX 1800 + `SET NX EX 60` 锁 + **Lua 比较删除**释放，防错删他人锁）；
  内存实现保留为**单测桩与降级后端**（接口稳定声明兑现：M2 承诺"接口稳后切 Redis"）；
- **降级语义（docs/06 §10.2 + 组内拍板 2026-09-07）**：Redis 异常默认降级内存并限频告警；
  `redis_required=True`（严格模式）时降级点抛错（可感知），不再静默。
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field

from app.core.config import get_settings
from app.core.redis_client import get_redis

logger = logging.getLogger("vocalverse")

TTL_S = 30 * 60  # 30min（docs/06 §10.2）
LOCK_TTL_S = 30

# Lua 原子释放：仅当锁仍属于调用方（nonce 一致）才删除——防"超时后删除他人锁"（docs/19 P0-1）
_RELEASE_LOCK = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
else
  return 0
end
"""

# 降级告警限频（每 op 每 60s 一次，防 Redis 抖动刷爆日志）
_warned: dict[str, float] = {}


def _warn_limited(op: str, exc: Exception) -> None:
    now = time.time()
    if now - _warned.get(op, 0) < 60:
        return
    _warned[op] = now
    logger.warning("state store redis op=%s degraded to memory: %s", op, exc)


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
    # py-10：META 补偿连续失败计数（≥2 后跳过补偿，规则兜底，控 LLM 配额）
    meta_failures: int = 0


class MemoryStateStore:
    """内存后端（单测桩 + Redis 不可用时的降级后端；语义与 RedisStateStore 对齐）。"""

    def __init__(self) -> None:
        self._data: dict[int, tuple[SessionState, float]] = {}
        self._locks: dict[int, tuple[str, float]] = {}  # session_id -> (nonce, expires)

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

    async def acquire_lock(self, session_id: int) -> str | None:
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


class RedisStateStore:
    """生产后端：Redis 会话态 + SETNX 锁（docs/19 P0-1）。

    - 键：`session:{id}`（JSON, EX 1800）/ `lock:{id}`（nonce, NX EX 60）；
    - 锁释放用 Lua 比较删除（原子，防"超时后误删他人锁"）；
    - 任一 op 异常 → 降级内存（默认；redis_required=True 时抛错，可感知）。
    """

    def __init__(self, client, fallback: MemoryStateStore | None = None) -> None:
        self._client = client
        self._fallback = fallback or MemoryStateStore()

    async def _degrade(self, op: str, exc: Exception, fallback_factory):
        """降级统一出口：告警限频 → 严格模式抛错 → 否则惰性执行内存后端。

        fallback_factory 为**协程工厂**（lambda）而非协程对象——严格模式抛错时
        不创建协程，避免 "coroutine was never awaited" 警告（健壮性细节）。
        """
        _warn_limited(op, exc)
        if get_settings().redis_required:
            raise RuntimeError(f"Redis required but unavailable (state:{op}): {exc}") from exc
        return await fallback_factory()

    async def get(self, session_id: int) -> SessionState | None:
        try:
            raw = await self._client.get(f"session:{session_id}")
            if raw is None:
                return None
            return SessionState(**json.loads(raw))
        except Exception as exc:
            return await self._degrade("get", exc, lambda: self._fallback.get(session_id))

    async def put(self, state: SessionState) -> None:
        try:
            await self._client.set(
                f"session:{state.session_id}",
                json.dumps(asdict(state), ensure_ascii=False),
                ex=TTL_S,
            )
        except Exception as exc:
            await self._degrade("put", exc, lambda: self._fallback.put(state))

    async def delete(self, session_id: int) -> None:
        try:
            pipe = self._client.pipeline()
            pipe.delete(f"session:{session_id}")
            pipe.delete(f"lock:{session_id}")
            await pipe.execute()
        except Exception as exc:
            await self._degrade("delete", exc, lambda: self._fallback.delete(session_id))

    async def acquire_lock(self, session_id: int) -> str | None:
        try:
            nonce = uuid.uuid4().hex
            ok = await self._client.set(f"lock:{session_id}", nonce, nx=True, ex=LOCK_TTL_S)
            return nonce if ok else None
        except Exception as exc:
            return await self._degrade(
                "acquire_lock", exc, lambda: self._fallback.acquire_lock(session_id)
            )

    async def release_lock(self, session_id: int, nonce: str) -> None:
        try:
            await self._client.eval(_RELEASE_LOCK, 1, f"lock:{session_id}", nonce)
        except Exception as exc:
            await self._degrade(
                "release_lock", exc, lambda: self._fallback.release_lock(session_id, nonce)
            )


class StateStore:
    """组合门面（工厂返回；测试直接实例化=测试模式强制内存，行为与原实现一致）。

    选择逻辑：`get_redis()` 非 None → Redis 后端；否则内存后端
    （测试/CI `settings.testing=true` 恒 None→内存，docs/06 §6 零外部依赖；docs/06 §10.2 降级）。
    """

    def __init__(self) -> None:
        client = get_redis()
        self._impl: MemoryStateStore | RedisStateStore = (
            RedisStateStore(client) if client is not None else MemoryStateStore()
        )

    async def get(self, session_id: int) -> SessionState | None:
        return await self._impl.get(session_id)

    async def put(self, state: SessionState) -> None:
        await self._impl.put(state)

    async def delete(self, session_id: int) -> None:
        await self._impl.delete(session_id)

    async def acquire_lock(self, session_id: int) -> str | None:
        return await self._impl.acquire_lock(session_id)

    async def release_lock(self, session_id: int, nonce: str) -> None:
        await self._impl.release_lock(session_id, nonce)


_store: StateStore | None = None


def get_state_store() -> StateStore:
    """单例工厂。初始化仅为同步内存操作（无 await 点），不存在并发竞态。"""
    global _store
    if _store is None:
        _store = StateStore()
    return _store
