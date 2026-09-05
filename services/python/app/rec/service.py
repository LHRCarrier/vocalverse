"""规则推荐引擎（**Python 写方**；local/31 §4.3 · local/29 §9）。

基于 SQLAlchemy ORM（跨 SQLite/PG），等价实现 local/31 §4.3 的 CTE SQL：候选过滤 [L, L+1]；
排序 未掌握>难度>兴趣>新鲜；同 scene_type ≤2（top-6 互异）；不足扩档；L4 复习席；曝光埋点。

写方唯一性：只读 scenarios/shadow_materials/user_profiles/user_skill_state/user_mastery/
material_difficulty；只写 events（曝光，仅追加）。Redis 缓存 rec:{uid}:{type}，写入后主动失效
（invalidate_recommendation_cache，local/32 A-2.4）。
"""

from __future__ import annotations

import contextlib
import json
import logging
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.redis_client import get_redis
from app.db import get_session_factory
from app.models import (
    Event,
    MaterialDifficulty,
    Scenario,
    ShadowMaterial,
    UserMastery,
    UserProfile,
    UserSkillState,
)
from app.models.base import EventTypes

logger = logging.getLogger("vocalverse")
RULE_VERSION = "rules-v1"
LEVELS = ("L1", "L2", "L3", "L4")
NEXT = {"L1": "L2", "L2": "L3", "L3": "L4", "L4": "L4"}  # L4 封顶（向上耗尽）
REVIEW_LEVEL = {"L4": "L3", "L3": "L2", "L2": "L1"}  # 复习席 = L−1（L1 无）
_FALLBACK = {1: "L1", 2: "L2", 3: "L3", 4: "L4"}
_STATUS_ORDER = {"not_mastered": 0, "in_progress": 1, "mastered": 2}
_MIN = datetime.min.replace(tzinfo=UTC)


def _idx(lv: str) -> int:
    return LEVELS.index(lv) if lv in LEVELS else -1


def _aware(dt) -> datetime | None:
    """归一 aware UTC（SQLite naive → UTC；与 _MIN/now 可比，docs/10 时间戳约定）。"""
    if dt is None:
        return None
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt


def _effective_levels(user_lvl: str) -> set[str]:
    return {user_lvl, NEXT[user_lvl]}


def _order(lvls: set[str], user_lvl: str) -> list[str]:
    """扩档顺序：仅在 L±1 档内、按距 L 近→远（防 L2 用户被推 L4，local/32 C8）。

    超过 ±1 档不扩（宁缺毋滥，local/31 §5.5）：不足 limit 就返回较少，不硬拉错档素材。
    """
    base = _idx(user_lvl)
    return sorted(
        (lv for lv in LEVELS if lv not in lvls and abs(_idx(lv) - base) <= 1),
        key=lambda lv: abs(_idx(lv) - base),
    )


def resolve_level(db: Session, user_id: int) -> str:
    """统一尺度左端：动态水平（conf≥阈值）→ 权威档 → L1（local/29 §9）。"""
    cfg = get_settings()
    row = db.execute(
        select(UserSkillState.est_level, UserSkillState.confidence).where(
            UserSkillState.user_id == user_id
        )
    ).first()
    if row and row.confidence is not None and float(row.confidence) >= cfg.skill_confidence_min:
        return row.est_level
    p = db.execute(select(UserProfile.cefr_level).where(UserProfile.user_id == user_id)).first()
    return p.cefr_level if p and p.cefr_level else "L1"


def _user_tags(db: Session, user_id: int) -> set[str]:
    p = db.execute(select(UserProfile.interest_tags).where(UserProfile.user_id == user_id)).first()
    return set(p.interest_tags or []) if p else set()


def _rank(items: list[dict], user_lvl: str, tags: set[str]) -> list[dict]:
    """排序：未掌握(0)<进行中(1)<已掌握(2) → 难度距离 → 兴趣命中 ↓ → 最近练过靠后。"""
    for it in items:
        it["_tag_hit"] = len(tags & set(it["interest_tags"]))
        it["_dist"] = abs(_idx(it["diff_level"]) - _idx(user_lvl))
    items.sort(
        key=lambda x: (
            _STATUS_ORDER[x["mstatus"]],
            x["_dist"],
            -x["_tag_hit"],
            x["last_practiced_at"] is not None,
            x["last_practiced_at"] or _MIN,
        )
    )
    return items


def _candidates(db: Session, user_id: int, ctype: str, levels: set[str]) -> list[dict]:
    """候选：published 内容 + 难度档 ∈ levels（md 优先，缺行内容方初评兜底）+ 掌握度。"""
    if ctype == "scene":
        stmt = (
            select(
                Scenario,
                MaterialDifficulty.diff_level,
                UserMastery.status,
                UserMastery.last_practiced_at,
            )
            .outerjoin(
                MaterialDifficulty,
                and_(
                    MaterialDifficulty.content_type == "scene",
                    MaterialDifficulty.content_id == Scenario.id,
                ),
            )
            .outerjoin(
                UserMastery,
                and_(
                    UserMastery.user_id == user_id,
                    UserMastery.content_type == "scene",
                    UserMastery.content_id == Scenario.id,
                ),
            )
            .where(Scenario.status == "published")
        )
    else:
        stmt = (
            select(
                ShadowMaterial,
                MaterialDifficulty.diff_level,
                UserMastery.status,
                UserMastery.last_practiced_at,
            )
            .outerjoin(
                MaterialDifficulty,
                and_(
                    MaterialDifficulty.content_type == "shadow",
                    MaterialDifficulty.content_id == ShadowMaterial.id,
                ),
            )
            .outerjoin(
                UserMastery,
                and_(
                    UserMastery.user_id == user_id,
                    UserMastery.content_type == "shadow",
                    UserMastery.content_id == ShadowMaterial.id,
                ),
            )
            .where(ShadowMaterial.status == "published")
        )
    out = []
    for head, diff_level, mstatus, last_practiced in db.execute(stmt).all():
        fb = (
            _FALLBACK.get(head.difficulty, "L1")
            if ctype == "scene"
            else _FALLBACK.get(head.level, "L1")
        )
        lvl = diff_level or fb
        if lvl not in levels:
            continue
        out.append(
            {
                "id": int(head.id),
                "title": head.title,
                "scene_type": getattr(head, "scene_type", None),
                "interest_tags": head.interest_tags or [],
                "diff_level": lvl,
                "mstatus": mstatus or "not_mastered",
                "last_practiced_at": _aware(last_practiced),
            }
        )
    return out


def _diversify(
    items: list[dict],
    scene_type_key: bool,
    limit: int,
    counts: dict[str, int] | None = None,
) -> list[dict]:
    """同 scene_type 至多 2（top-6 互异）；影子无该约束。

    ``counts`` 为跨阶段累计的 scene_type 计数（主窗+扩档共用同一字典），保证
    「同 scene_type ≤2」在**最终列表**上成立，而非仅在各阶段内部（local/31 §4.3）。
    """
    if not scene_type_key:
        return items[:limit]
    if counts is None:
        counts = {}
    out = []
    for it in items:
        if len(out) >= limit:
            break
        key = it.get("scene_type") or "none"
        if counts.get(key, 0) >= 2:
            continue
        out.append(it)
        counts[key] = counts.get(key, 0) + 1
    return out


def _review_slots(db: Session, user_id: int, user_lvl: str, ctype: str, n: int) -> list[dict]:
    """复习席：L−1 档、in_progress/mastered、距上次 ≥review_gap_days，掌握度最弱优先（A-4.4）。"""
    cfg = get_settings()
    lvl = REVIEW_LEVEL.get(user_lvl)
    if lvl is None:
        return []
    cutoff = datetime.now(UTC) - timedelta(days=cfg.review_gap_days)
    rows = _candidates(db, user_id, ctype, {lvl})
    pool = [
        it
        for it in rows
        if it["mstatus"] != "not_mastered"
        and it["last_practiced_at"] is not None
        and it["last_practiced_at"] < cutoff
    ]
    pool.sort(key=lambda x: x["last_practiced_at"] or _MIN)  # 最久未练在前（掌握度最弱近似）
    return pool[:n]


def _impression(db: Session, user_id: int, content_type: str, items: list[dict], lvl: str) -> None:
    """曝光埋点（只追加；成功才记）。"""
    db.add(
        Event(
            user_id=user_id,
            event_type=EventTypes.RECOMMEND_IMPRESSION,
            recommend_group_id=uuid4().hex,
            occurred_at=datetime.now(UTC),
            payload={
                "content_type": content_type,
                "items": [{"id": it["id"], "level": it["diff_level"]} for it in items],
                "user_level": lvl,
                "rule_version": RULE_VERSION,
            },
        )
    )


def _cache_get(key: str):
    r = get_redis()
    if r is None:
        return None
    try:
        val = r.get(key)
    except Exception:
        return None
    return json.loads(val) if val else None


def _cache_set(key: str, value, ttl_s: int) -> None:
    r = get_redis()
    if r is None:
        return
    with contextlib.suppress(Exception):
        r.set(key, json.dumps(value, ensure_ascii=False), ex=ttl_s)


def _clean(items: list[dict], ctype: str) -> list[dict]:
    """对外返回/落缓存：剥离内部字段（_tag_hit/_dist/interest_tags/datetime）。"""
    return [
        {
            "id": it["id"],
            "content_type": ctype,
            "title": it["title"],
            "scene_type": it.get("scene_type"),
            "diff_level": it["diff_level"],
            "mstatus": it["mstatus"],
            "tag_hit": it.get("_tag_hit", 0),
        }
        for it in items
    ]


def _recommend(user_id: int, ctype: str, limit: int, db: Session | None) -> list[dict]:
    cfg = get_settings()
    own = db is None
    session = db if db is not None else get_session_factory()()
    try:
        lvl = resolve_level(session, user_id)
        key = None
        if own:
            key = f"rec:{user_id}:{ctype}"
            cached = _cache_get(key)
            if cached is not None:
                return cached
        tags = _user_tags(session, user_id)
        cands = _rank(_candidates(session, user_id, ctype, _effective_levels(lvl)), lvl, tags)
        counts: dict[str, int] = {}
        items = _diversify(cands, scene_type_key=(ctype == "scene"), limit=limit, counts=counts)
        if len(items) < limit:  # 扩档：先近后远
            for lv in _order(_effective_levels(lvl), lvl):
                if len(items) >= limit:
                    break
                extra = _rank(_candidates(session, user_id, ctype, {lv}), lvl, tags)
                seen = {it["id"] for it in items}
                items += _diversify(
                    [it for it in extra if it["id"] not in seen],
                    scene_type_key=(ctype == "scene"),
                    limit=limit - len(items),
                    counts=counts,
                )
        if lvl in REVIEW_LEVEL and len(items) < limit:  # 复习席
            got = _review_slots(session, user_id, lvl, ctype, max(1, limit // 3))
            seen = {it["id"] for it in items}
            # 复习席刻意豁免 scene_type≤2（local/31 §4.3 的「top-6 互异」只约束主窗/扩档的新荐）：
            # 复习目标是「别忘旧材」，允许对已满类型追加，否则会压掉应复习的陈旧内容。
            items += [it for it in got if it["id"] not in seen]
        items = items[:limit]
        out = _clean(items, ctype)
        if own:
            _impression(session, user_id, ctype, items, lvl)
            session.commit()
            _cache_set(key, out, cfg.rec_cache_ttl_s)
        return out
    finally:
        if own:
            session.close()


def recommend_scenes(
    user_id: int, limit: int | None = None, db: Session | None = None
) -> list[dict]:
    """场景推荐（主窗 [L,L+1] + 扩档 + 复习席 + 曝光埋点）。"""
    cfg = get_settings()
    return _recommend(user_id, "scene", limit or cfg.rec_limit_scenes, db)


def recommend_shadow(
    user_id: int, limit: int | None = None, db: Session | None = None
) -> list[dict]:
    """影子跟读推荐（同规则，无 scene_type 多样性，复习席取 1）。"""
    cfg = get_settings()
    return _recommend(user_id, "shadow", limit or cfg.rec_limit_shadow, db)


def invalidate_recommendation_cache(user_id: int) -> None:
    """主动失效（local/32 A-2.4）：update_user_level / mastery / 难度变更后调用。"""
    r = get_redis()
    if r is None:
        return
    with contextlib.suppress(Exception):
        r.delete(f"rec:{user_id}:scene", f"rec:{user_id}:shadow")
