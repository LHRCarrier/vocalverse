"""用户水平动态评价：update_user_level（**Python 写方**；local/31 §4.1 + local/32 修订）。

只写 ``user_skill_state``；``user_profiles.cefr_level``（权威档）唯一写方是 Java，Python 永不直写——
动态档经内部 REST 委托（local/27 §9.3 / local/32 A-2.1），本模块回调默认关（考试专属）。

核心公式（统一尺度左端，local/26 §2 / local/27 §4 + local/32 修订）：
- 样本分 s = 0.6·pron + 0.4·flu，难度归一化 s += (diff − 70)（**符号修正**：local/27 §4.1 写 −，
  应为 +——易素材虚高、难素材虚低，须加回难度溢价，见工作日志 2026-09-02 阶段 1）；
- 冷启动（n < min_samples）：est = w·P + (1−w)·mean，w = max(0.3, 0.7−0.1n)；
- 满窗：est = f·P + (1−f)·mean，f = max(0.15·2^(−d/60), skill_placement_floor)；
- confidence = min(1, n/window)（local/30 漏洞 1 修复：两分支统一，单调）；
- est_level = 滞回(est)（local/32 A-3.1：三档界逐档下降、禁止跨档）+ 低谷保护（A-3.2）；
- 单次降幅钳制 |Δ↓| ≤ skill_max_downgrade_per_update（A-4.1）。

幂等三层：attempts 不可变重算收敛 + ``with_for_update`` 行锁串行 + user_id 唯一约束。
事务：函数内 try/except → rollback → raise；调用方按降级纪律捕获（local/27 §9.4）。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import get_session_factory
from app.models import Attempt, MaterialDifficulty, Placement, UserSkillState
from app.models import Session as DbSession
from app.models.base import AttemptKinds, SessionKinds

logger = logging.getLogger("vocalverse")

# 定档分缺失时按档位映射的中值（冷启动兜底，local/27 §6）
BAND_MID = {"L1": 50.0, "L2": 62.0, "L3": 77.0, "L4": 92.0}
_LEVELS = ("L1", "L2", "L3", "L4")
DEFAULT_VERSION = "win-v1"


def _level_for(est: float) -> str:
    """统一尺度纯分档（85/70/55，local/26 §2）。"""
    if est >= 85:
        return "L4"
    if est >= 70:
        return "L3"
    if est >= 55:
        return "L2"
    return "L1"


def _idx(level: str | None) -> int:
    return _LEVELS.index(level) if level in _LEVELS else -1


def _level_hysteresis(est: float, prev_level: str | None, h: float) -> str:
    """滞回定档（local/32 A-3.1 修订）：三档界全部套 [thr−h, thr)，升档即时、降档只降一档。

    - 无旧档 或 原始档高于旧档 → 升档即时；
    - 同档 → 保持；
    - 原始档低于旧档 → 仅当 est < LO[旧档]−h 才降、且只降一档（禁止 L4→L2 跨档）；
      否则留在滞回带内保持旧档。
    """
    raw = _level_for(est)
    if prev_level is None or _idx(raw) > _idx(prev_level):
        return raw
    if _idx(raw) < _idx(prev_level):
        lo = {"L2": 55.0, "L3": 70.0, "L4": 85.0}.get(prev_level, 0.0)
        if est < lo - h:
            return _level_for(lo - h - 0.01)  # 逐档下降
        return prev_level  # 滞回带内保持
    return raw


def _placement_score(db: Session, user_id: int) -> tuple[float | None, datetime | None]:
    """最近一次 completed placement 的定档分。

    口径（local/27 §5）：优先 details.schema_version='2d' 的 overall_score（两维 S）；
    否则用 level 快照映射档中值（兼容存量三维行，不混标度）。
    """
    row = db.execute(
        select(Placement.overall_score, Placement.level, Placement.completed_at, Placement.details)
        .where(Placement.user_id == user_id, Placement.status == "completed")
        .order_by(Placement.completed_at.desc())
        .limit(1)
    ).first()
    if row is None:
        return None, None
    details = row.details or {}
    if details.get("schema_version") == "2d" and row.overall_score is not None:
        return float(row.overall_score), row.completed_at
    if row.level is not None and row.level in BAND_MID:
        return BAND_MID[row.level], row.completed_at
    return None, row.completed_at


def _window_samples(db: Session, user_id: int, window: int, normalize: bool) -> list[float]:
    """最近 window 个有效评分样本的能力分（已按素材难度归一化）。

    - 样本 = 单轮 attempts（pron/flu 均非空，kind∈dialog_speech/free_practice，dialog 会话）；
    - 缺分轮（ISE 失败）自然排除，不按 0 分计（local/32 A-3.3 Q14）；
    - 难度归一化（开关）：s += (diff − 70)。**符号修正**：local/27 §4.1 写 −，应为 +。
      diff 取场景级 material_difficulty.diff_score；缺行用内容方初评映射兜底。
    """
    rows = db.execute(
        select(Attempt.pron_score, Attempt.flu_score, DbSession.scenario_id)
        .join(DbSession, DbSession.id == Attempt.session_id)
        .where(
            Attempt.user_id == user_id,
            Attempt.pron_score.isnot(None),
            Attempt.flu_score.isnot(None),
            Attempt.kind.in_([AttemptKinds.DIALOG_SPEECH, AttemptKinds.FREE_PRACTICE]),
            DbSession.kind == SessionKinds.DIALOG,
        )
        .order_by(Attempt.created_at.desc())
        .limit(window)
    ).all()

    diff_map: dict[int, float] = {}
    if normalize:
        scen_ids = {r.scenario_id for r in rows if r.scenario_id is not None}
        if scen_ids:
            for m in db.execute(
                select(MaterialDifficulty).where(
                    MaterialDifficulty.content_type == "scene",
                    MaterialDifficulty.content_id.in_(scen_ids),
                )
            ).scalars():
                diff_map[m.content_id] = float(m.diff_score)

    out: list[float] = []
    for pron, flu, scenario_id in rows:
        if pron is None or flu is None:
            continue
        s = 0.6 * float(pron) + 0.4 * float(flu)
        if normalize and scenario_id is not None:
            diff = diff_map.get(scenario_id)
            if diff is not None:
                s += diff - 70.0  # 难度归一化（易素材虚高→减，难素材虚低→加）
        out.append(s)
    return out


def update_user_level(user_id: int, db: Session | None = None) -> dict:
    """重算并落库该用户的动态水平（同步；失败回滚不半写）。

    返回 {est_score, est_level, confidence, sample_count, source_version}。
    """
    cfg = get_settings()
    own_session = db is None
    session = db if db is not None else get_session_factory()()
    try:
        # ---- 行锁：幂等串行 + 读旧档（PG FOR UPDATE；SQLite 单进程 no-op） ----
        prev = session.execute(
            select(UserSkillState).where(UserSkillState.user_id == user_id).with_for_update()
        ).scalar_one_or_none()
        prev_est = float(prev.est_score) if prev else None
        prev_level = prev.est_level if prev else None

        # ---- 1) 窗口样本 + 定档分 ----
        samples = _window_samples(
            session, user_id, cfg.skill_window_size, cfg.skill_difficulty_normalize
        )
        n = len(samples)
        placement_score, placed_at = _placement_score(session, user_id)
        now = datetime.now(UTC)

        # ---- 2) 基础估计（冷启动 / 满窗） ----
        if n == 0 and placement_score is None:
            est = 50.0  # 完全冷启动兜底（理论不可达：40303 门禁）
        elif n < cfg.skill_min_samples:
            w = max(0.3, cfg.skill_blend_placement - cfg.skill_blend_step * n)
            base = placement_score if placement_score is not None else BAND_MID["L1"]
            mean_n = sum(samples) / n if n else base
            est = w * base + (1 - w) * mean_n
        else:
            mean_n = sum(samples) / n
            if placement_score is not None and placed_at is not None:
                if placed_at.tzinfo is None:  # SQLite naive → 归一 aware（docs/10 时间戳约定）
                    placed_at = placed_at.replace(tzinfo=UTC)
                days = max(0.0, (now - placed_at).total_seconds() / 86400.0)
                f = max(
                    cfg.skill_placement_holdout
                    * (2 ** (-days / cfg.skill_forgetting_halflife_days)),
                    cfg.skill_placement_floor,
                )
            else:
                f = 0.0
            est = f * (placement_score or mean_n) + (1 - f) * mean_n

        # ---- 3) 单次降幅钳制（A-4.1）：只限降、不限升 ----
        if prev_est is not None and est < prev_est - cfg.skill_max_downgrade_per_update:
            est = prev_est - cfg.skill_max_downgrade_per_update
        est = round(max(0.0, min(100.0, est)), 2)
        conf = min(1.0, n / cfg.skill_window_size)

        # ---- 4) 滞回定档 + 低谷保护（A-3.1 / A-3.2） ----
        h = cfg.skill_band_hysteresis
        level = _level_hysteresis(est, prev_level, h)
        streak = 0
        guard: datetime | None = None
        descend = _idx(_level_for(est)) < _idx(prev_level) if prev_level else False
        if prev is not None and prev.slump_guard_until is not None and now < prev.slump_guard_until:
            # 冻结期：档位不动，延续现状
            level = prev_level
            streak = prev.downgrade_streak
            guard = prev.slump_guard_until
        elif descend:
            # 本次发生降级：计数，达阈值则冻结档位（防雪崩）
            streak = prev.downgrade_streak + 1 if prev is not None else 1
            if streak >= cfg.skill_slump_streak:
                level = prev_level  # 冻结
                guard = now + timedelta(days=cfg.skill_slump_cooldown_days)
            else:
                level = _level_hysteresis(est, prev_level, h)  # 一档下降 / 滞回保持

        # ---- 5) 幂等写（唯一约束 + 先查后写） ----
        if prev is None:
            new = UserSkillState(
                user_id=user_id,
                pron_est=Decimal("0"),
                flu_est=Decimal("0"),
                est_score=Decimal(str(est)),
                est_level=level,
                confidence=Decimal(str(round(conf, 2))),
                sample_count=n,
                last_sample_at=now,
                downgrade_streak=streak,
                slump_guard_until=guard,
                source_version=DEFAULT_VERSION,
            )
            session.add(new)
        else:
            prev.est_score = Decimal(str(est))
            prev.est_level = level
            prev.confidence = Decimal(str(round(conf, 2)))
            prev.sample_count = n
            prev.last_sample_at = now
            prev.downgrade_streak = streak
            prev.slump_guard_until = guard
            prev.source_version = DEFAULT_VERSION

        if own_session:
            session.commit()
        logger.info(
            "user_skill_state updated user=%s level=%s score=%s conf=%s n=%s streak=%s",
            user_id,
            level,
            est,
            round(conf, 2),
            n,
            streak,
        )
        return {
            "user_id": user_id,
            "est_score": est,
            "est_level": level,
            "confidence": round(conf, 2),
            "sample_count": n,
            "source_version": DEFAULT_VERSION,
        }
    except Exception:
        if own_session:
            session.rollback()
        raise
    finally:
        if own_session:
            session.close()


async def notify_java_level(user_id: int, level: str, level_at: datetime) -> None:
    """委托 Java 更新 user_profiles.cefr_level（镜像 placement._callback_level + level_at 幂等）。

    - 默认关（skill_callback_enabled=False，考试专属）；失败不 raise、Q-B07 对账兜底
      （local/32 A-2.1）。
    """
    import httpx

    from app.core.config import get_settings

    s = get_settings()
    if not s.skill_callback_enabled:
        return
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            await client.post(
                f"{s.java_base_url}/internal/level",
                json={
                    "user_id": user_id,
                    "level": level,
                    "source": "skill",
                    "level_at": level_at.isoformat(),
                },
                headers={"Authorization": f"Bearer {s.service_token}"},
            )
    except Exception:
        logger.exception("java level callback failed user=%s (Q-B07 对账兜底)", user_id)
