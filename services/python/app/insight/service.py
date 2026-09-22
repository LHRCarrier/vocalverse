"""指标聚合服务（docs/06 §9.1 修订口径 · docs/53 P2）。

口径（2026-09-21 修订，来源 = GA4/PostHog/Plausible 通行定义 + 现玩法）：

- **参与会话**：同一 `browse_session_id` 在窗口内满足任一条件 —— 时长 >10s、含关键事件
  （非 page_view）、或 ≥2 个 page_view；**跳出率 = 1 − 参与会话数 / 会话总数**；
- **点击率 CTR**：曝光 = 有 `recommend_impression` 的 `recommend_group_id` 去重；
  点击 = 该组在曝光后 30min 内出现 `recommend_click`（同组去重）；
- **完成率**：完成单元 / 发起单元（三类单元，分子分母同存可审计）：
  * 唱吧 = `sessions.kind='sing'` 且 status='completed' / 同期创建的 sing 会话；
  * 酒馆 = 同期创建的 campaign 中有 ≥1 条玩家消息 / 同期创建 campaign 总数；
  * 答辩 = `sessions.kind='defense'` 且 status='completed' / 同期创建 defense 会话；
  * 入学测试 = `placements.status='completed'` / 同期创建 placements；
- **互动率**：酒馆玩家消息 / DM 消息（同期）；答辩有效作答轮次 / 分配轮次；
  自由对话无服务端会话（无状态转发），**不计入**并在 `notes` 标注。

个人报表（`/api/v1/stats/me`）：练习趋势（按日 attempts/sing）、五维雷达
（发音/流利/语法/音准/节奏）、概览（会话数/录音数/练习分钟/最佳分）。
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from app.models.analytics import Event
from app.models.base import SessionKinds, SessionStatus
from app.models.practice import Attempt, SingAttempt
from app.models.practice import Session as PracticeSession
from app.models.trpg import TrpgCampaign, TrpgMessage
from app.models.user import Placement
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

#: 关键事件（非 page_view 即视为「有效互动」；docs/06 §9.1 修订）
KEY_EVENT_TYPES = (
    "scene_start",
    "recording_start",
    "recording_complete",
    "score_event",
    "practice_complete",
    "fun_action",
    "free_chat_open",
    "free_chat_turn",
    "recommend_click",
    "word_lookup",
    "vocab_add",
    "annotation_add",
    "tts_play",
    "tts_prepare",
)
ENGAGED_SECONDS = 10
CTR_WINDOW_MINUTES = 30


def _rate(num: int, den: int) -> float | None:
    return round(num / den, 4) if den else None


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat()


def _window(days: int) -> tuple[datetime, datetime]:
    end = datetime.now(UTC)
    start = end - timedelta(days=max(1, days))
    return start, end


def _engaged_sessions(db: Session, start: datetime, end: datetime) -> tuple[int, int]:
    """返回 (会话总数, 参与会话数)：按 browse_session_id 分组判定（docs/06 §9.1 修订口径）。"""
    rows = db.execute(
        select(
            Event.browse_session_id,
            func.min(Event.occurred_at),
            func.max(Event.occurred_at),
            func.count().label("n"),
            func.sum(case((Event.event_type.in_(KEY_EVENT_TYPES), 1), else_=0)).label("key_n"),
            func.sum(case((Event.event_type == "page_view", 1), else_=0)).label("pv_n"),
        )
        .where(
            Event.browse_session_id.is_not(None),
            Event.occurred_at >= start,
            Event.occurred_at <= end,
        )
        .group_by(Event.browse_session_id)
    ).all()
    engaged = 0
    for _sid, first, last, _n, key_n, pv_n in rows:
        span = (last - first).total_seconds() if first and last else 0
        if span > ENGAGED_SECONDS or (key_n or 0) > 0 or (pv_n or 0) >= 2:
            engaged += 1
    return len(rows), engaged


def _ctr(db: Session, start: datetime, end: datetime) -> tuple[int, int]:
    """返回 (曝光组数, 点击组数)：同 recommend_group_id，点击须落在曝光后 30min 内。"""
    impressions = db.execute(
        select(Event.recommend_group_id, func.min(Event.occurred_at).label("imp_at"))
        .where(
            Event.event_type == "recommend_impression",
            Event.recommend_group_id.is_not(None),
            Event.occurred_at >= start,
            Event.occurred_at <= end,
        )
        .group_by(Event.recommend_group_id)
    ).all()
    if not impressions:
        return 0, 0
    imp_map = {gid: imp_at for gid, imp_at in impressions}
    clicks = db.execute(
        select(Event.recommend_group_id, func.min(Event.occurred_at).label("clk_at"))
        .where(
            Event.event_type == "recommend_click",
            Event.recommend_group_id.in_(list(imp_map)),
            Event.occurred_at >= start,
            Event.occurred_at <= end,
        )
        .group_by(Event.recommend_group_id)
    ).all()
    hit = 0
    for gid, clk_at in clicks:
        imp_at = imp_map.get(gid)
        if imp_at and clk_at and (clk_at - imp_at) <= timedelta(minutes=CTR_WINDOW_MINUTES):
            hit += 1
    return len(imp_map), hit


def _completion(db: Session, start: datetime, end: datetime) -> dict[str, Any]:
    """完成率分子分母：按单元来源拆分（唱吧/酒馆/答辩/入学测试）。"""
    units: dict[str, dict[str, int]] = {}

    def session_unit(kind: str, label: str) -> None:
        base = (
            select(func.count())
            .select_from(PracticeSession)
            .where(
                PracticeSession.kind == kind,
                PracticeSession.started_at >= start,
                PracticeSession.started_at <= end,
            )
        )
        total = db.execute(base).scalar() or 0
        done = (
            db.execute(base.where(PracticeSession.status == SessionStatus.COMPLETED)).scalar() or 0
        )
        units[label] = {"total": int(total), "done": int(done)}

    session_unit(SessionKinds.SING, "sing")
    session_unit(SessionKinds.DEFENSE, "defense")

    camp_total = (
        db.execute(
            select(func.count())
            .select_from(TrpgCampaign)
            .where(TrpgCampaign.created_at >= start, TrpgCampaign.created_at <= end)
        ).scalar()
        or 0
    )
    camp_done = (
        db.execute(
            select(func.count(func.distinct(TrpgMessage.campaign_id)))
            .select_from(TrpgMessage)
            .join(TrpgCampaign, TrpgCampaign.id == TrpgMessage.campaign_id)
            .where(
                TrpgMessage.role == "user",
                TrpgCampaign.created_at >= start,
                TrpgCampaign.created_at <= end,
            )
        ).scalar()
        or 0
    )
    units["trpg"] = {"total": int(camp_total), "done": int(min(camp_done, camp_total))}

    pl_total = (
        db.execute(
            select(func.count())
            .select_from(Placement)
            .where(Placement.created_at >= start, Placement.created_at <= end)
        ).scalar()
        or 0
    )
    pl_done = (
        db.execute(
            select(func.count())
            .select_from(Placement)
            .where(
                Placement.created_at >= start,
                Placement.created_at <= end,
                Placement.completed_at.is_not(None),
            )
        ).scalar()
        or 0
    )
    units["placement"] = {"total": int(pl_total), "done": int(pl_done)}

    total = sum(u["total"] for u in units.values())
    done = sum(u["done"] for u in units.values())
    return {"total": total, "done": done, "units": units}


def _interaction(db: Session, start: datetime, end: datetime) -> dict[str, Any]:
    """互动率：酒馆玩家/DM 消息比 + 答辩作答/分配轮（自由对话无服务端会话，不计）。"""
    user_msgs = (
        db.execute(
            select(func.count())
            .select_from(TrpgMessage)
            .where(
                TrpgMessage.role == "user",
                TrpgMessage.created_at >= start,
                TrpgMessage.created_at <= end,
            )
        ).scalar()
        or 0
    )
    dm_msgs = (
        db.execute(
            select(func.count())
            .select_from(TrpgMessage)
            .where(
                TrpgMessage.role == "assistant",
                TrpgMessage.created_at >= start,
                TrpgMessage.created_at <= end,
            )
        ).scalar()
        or 0
    )
    assigned = (
        db.execute(
            select(func.coalesce(func.sum(PracticeSession.assigned_turns), 0)).where(
                PracticeSession.kind == SessionKinds.DEFENSE,
                PracticeSession.started_at >= start,
                PracticeSession.started_at <= end,
            )
        ).scalar()
        or 0
    )
    answered = (
        db.execute(
            select(func.coalesce(func.sum(PracticeSession.user_turn_count), 0)).where(
                PracticeSession.kind == SessionKinds.DEFENSE,
                PracticeSession.started_at >= start,
                PracticeSession.started_at <= end,
            )
        ).scalar()
        or 0
    )
    return {
        "trpg": {"user": int(user_msgs), "dm": int(dm_msgs)},
        "defense": {"answered": int(answered), "assigned": int(assigned)},
    }


def _trend(db: Session, start: datetime, end: datetime) -> list[dict[str, Any]]:
    """按日趋势：page_view 数 / 会话数 / 事件数 / 参与会话数。"""
    day = func.date(Event.occurred_at)
    rows = db.execute(
        select(
            day.label("d"),
            func.count().label("events"),
            func.sum(case((Event.event_type == "page_view", 1), else_=0)).label("pv"),
            func.count(func.distinct(Event.browse_session_id)).label("sessions"),
        )
        .where(Event.occurred_at >= start, Event.occurred_at <= end)
        .group_by(day)
        .order_by(day)
    ).all()
    return [
        {
            "date": str(r.d),
            "events": int(r.events),
            "page_views": int(r.pv or 0),
            "sessions": int(r.sessions or 0),
        }
        for r in rows
    ]


def _dimensions(db: Session, start: datetime, end: datetime, limit: int = 10) -> dict[str, list]:
    """维度 TopN（page/level/age_group/channel/song）——事件量倒序。"""
    out: dict[str, list] = {}
    for name, col in (
        ("page", Event.page),
        ("level", Event.level),
        ("age_group", Event.age_group),
        ("channel", Event.channel),
        ("target_type", Event.target_type),
    ):
        rows = db.execute(
            select(col, func.count().label("n"))
            .where(Event.occurred_at >= start, Event.occurred_at <= end, col.is_not(None))
            .group_by(col)
            .order_by(func.count().desc())
            .limit(limit)
        ).all()
        out[name] = [{"key": str(k), "events": int(n)} for k, n in rows]
    song_rows = db.execute(
        select(Event.song_id, func.count().label("n"))
        .where(Event.occurred_at >= start, Event.occurred_at <= end, Event.song_id.is_not(None))
        .group_by(Event.song_id)
        .order_by(func.count().desc())
        .limit(limit)
    ).all()
    out["song"] = [{"key": str(k), "events": int(n)} for k, n in song_rows]
    return out


def overview(db: Session, *, days: int = 30) -> dict[str, Any]:
    """平台四指标 + 趋势 + 维度 TopN（docs/06 §9.1 修订口径；分子分母同存可审计）。"""
    start, end = _window(days)
    sessions_total, engaged = _engaged_sessions(db, start, end)
    imp, clicks = _ctr(db, start, end)
    completion = _completion(db, start, end)
    interaction = _interaction(db, start, end)

    trpg = interaction["trpg"]
    defense = interaction["defense"]
    inter_num = trpg["user"] + defense["answered"]
    inter_den = trpg["user"] + trpg["dm"] + defense["assigned"]

    return {
        "period": {"days": days, "start": _iso(start), "end": _iso(end)},
        "metrics": {
            "ctr": {"numerator": clicks, "denominator": imp, "rate": _rate(clicks, imp)},
            "completion_rate": {
                "numerator": completion["done"],
                "denominator": completion["total"],
                "rate": _rate(completion["done"], completion["total"]),
                "units": completion["units"],
            },
            "interaction_rate": {
                "numerator": inter_num,
                "denominator": inter_den,
                "rate": _rate(inter_num, inter_den),
                "sources": interaction,
            },
            "bounce_rate": {
                "numerator": sessions_total - engaged,
                "denominator": sessions_total,
                "rate": _rate(sessions_total - engaged, sessions_total),
                "engaged_sessions": engaged,
            },
        },
        "trend": _trend(db, start, end),
        "dimensions": _dimensions(db, start, end),
        "notes": [
            "参与会话口径（GA4/PostHog/Plausible）：时长>10s 或 含关键事件 或 ≥2 page_view",
            "自由对话为无状态转发（无服务端会话），互动率不计入该来源",
            "CTR 依赖推荐位曝光/点击埋点（docs/53 P3 起有数据）",
        ],
        "generated_at": _iso(datetime.now(UTC)),
    }


def _avg(values: list) -> float | None:
    nums = [float(v) for v in values if v is not None]
    return round(sum(nums) / len(nums), 2) if nums else None


def me(db: Session, user_id: int, *, days: int = 30) -> dict[str, Any]:
    """个人学习报表：概览 + 按日趋势 + 五维雷达（发音/流利/语法/音准/节奏）。"""
    start, end = _window(days)

    attempts = (
        db.execute(
            select(Attempt).where(
                Attempt.user_id == user_id,
                Attempt.created_at >= start,
                Attempt.created_at <= end,
            )
        )
        .scalars()
        .all()
    )
    sings = (
        db.execute(
            select(SingAttempt).where(
                SingAttempt.user_id == user_id,
                SingAttempt.created_at >= start,
                SingAttempt.created_at <= end,
            )
        )
        .scalars()
        .all()
    )
    sessions = (
        db.execute(
            select(func.count())
            .select_from(PracticeSession)
            .where(
                PracticeSession.user_id == user_id,
                PracticeSession.started_at >= start,
                PracticeSession.started_at <= end,
            )
        ).scalar()
        or 0
    )
    duration = (
        db.execute(
            select(func.coalesce(func.sum(PracticeSession.duration_s), 0)).where(
                PracticeSession.user_id == user_id,
                PracticeSession.started_at >= start,
                PracticeSession.started_at <= end,
            )
        ).scalar()
        or 0
    )

    day = func.date(Attempt.created_at)
    trend_rows = db.execute(
        select(
            day.label("d"),
            func.count().label("n"),
            func.avg(Attempt.overall_score).label("avg"),
        )
        .where(
            Attempt.user_id == user_id,
            Attempt.created_at >= start,
            Attempt.created_at <= end,
        )
        .group_by(day)
        .order_by(day)
    ).all()
    sing_day = func.date(SingAttempt.created_at)
    sing_rows = db.execute(
        select(sing_day.label("d"), func.count().label("n"))
        .where(
            SingAttempt.user_id == user_id,
            SingAttempt.created_at >= start,
            SingAttempt.created_at <= end,
        )
        .group_by(sing_day)
        .order_by(sing_day)
    ).all()
    sing_map = {str(r.d): int(r.n) for r in sing_rows}
    trend = [
        {
            "date": str(r.d),
            "attempts": int(r.n),
            "avg_overall": round(float(r.avg), 2) if r.avg is not None else None,
            "sing": sing_map.get(str(r.d), 0),
        }
        for r in trend_rows
    ]
    for d, n in sing_map.items():
        if all(t["date"] != d for t in trend):
            trend.append({"date": d, "attempts": 0, "avg_overall": None, "sing": n})
    trend.sort(key=lambda t: t["date"])

    axes = ["发音", "流利", "语法", "音准", "节奏"]
    values = [
        _avg([a.pron_score for a in attempts]),
        _avg([a.flu_score for a in attempts]),
        _avg([a.gram_score for a in attempts]),
        _avg([s.pitch_score for s in sings]),
        _avg([s.rhythm_score for s in sings]),
    ]
    by_kind: dict[str, dict[str, Any]] = {}
    for a in attempts:
        item = by_kind.setdefault(a.kind, {"count": 0, "overall": []})
        item["count"] += 1
        item["overall"].append(a.overall_score)
    if sings:
        by_kind["sing"] = {"count": len(sings), "overall": [s.overall_score for s in sings]}

    return {
        "period": {"days": days, "start": _iso(start), "end": _iso(end)},
        "summary": {
            "sessions": int(sessions),
            "attempts": len(attempts),
            "sing_attempts": len(sings),
            "practice_minutes": round(int(duration) / 60),
            "avg_overall": _avg([a.overall_score for a in attempts]),
            "best_overall": max(
                [float(a.overall_score) for a in attempts if a.overall_score is not None],
                default=None,
            ),
        },
        "trend": trend,
        "radar": {"axes": axes, "values": [v if v is not None else 0 for v in values]},
        "by_kind": [
            {"kind": k, "count": v["count"], "avg_overall": _avg(v["overall"])}
            for k, v in sorted(by_kind.items())
        ],
        "generated_at": _iso(datetime.now(UTC)),
    }


def _date_label(d: date) -> str:  # pragma: no cover - 便于未来按日标签
    return d.isoformat()
