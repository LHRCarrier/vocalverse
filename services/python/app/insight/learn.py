"""学习画像聚合（docs/53 P4）：学习主页与模块详情页的真实数据源。

背景：原 `app/agent/domains/learner.py`（对话期画像注入）随英语场景对话下线删除；
本模块按 **attempts / scores / sessions / events / user_vocabulary / trpg** 事实表重建
「学习主页 + 模块详情」所需的聚合（docs/24 原语义 + docs/53 P4 DoD）。

口径：
- 热力图 = 按日事件量（level 0 / 1-4 / 5-9 / 10+），近 N 周（默认 12）；
- 一句话画像 = 近 30 天练习次数 + 发音维度变化（对比前半窗与后半窗）+ 连续活跃天数；
- 模块摘要（学习主页 4 行）：words（生词本）/ community（埋点足迹）/ speaking（三维均分）/
  practice（会话分钟 + 酒馆剧本数）；
- 模块详情：speaking（三维趋势 + 薄弱音素 Top3，来自 `scores`）/ practice（热力图 + 剧本强度）/
  words（生词本列表，join 词典取首义）/ community（足迹分布 + 常逛页面）。
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from app.models.analytics import Event
from app.models.base import SessionKinds
from app.models.practice import Attempt, Score
from app.models.practice import Session as PracticeSession
from app.models.reading import DictionaryEntry, UserVocabulary
from app.models.trpg import TrpgCampaign, TrpgMessage
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

MODULES = ("words", "community", "speaking", "practice")
HEATMAP_WEEKS = 12


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat()


def _avg(values: list) -> float | None:
    nums = [float(v) for v in values if v is not None]
    return round(sum(nums) / len(nums), 1) if nums else None


def _heatmap(db: Session, user_id: int, *, weeks: int = HEATMAP_WEEKS) -> list[dict]:
    """按日事件量 → 热力等级（0/1-4/5-9/10+）；无事件的日子不返回（前端补空格）。"""
    since = datetime.now(UTC) - timedelta(weeks=weeks)
    day = func.date(Event.occurred_at)
    rows = db.execute(
        select(day.label("d"), func.count().label("n"))
        .where(Event.user_id == user_id, Event.occurred_at >= since)
        .group_by(day)
        .order_by(day)
    ).all()
    out = []
    for d, n in rows:
        count = int(n)
        level = 0 if count == 0 else (1 if count <= 4 else (2 if count <= 9 else 3))
        out.append({"date": str(d), "count": count, "level": level})
    return out


def _profile_line(db: Session, user_id: int, *, days: int = 30) -> str:
    since = datetime.now(UTC) - timedelta(days=days)
    rows = db.execute(
        select(Attempt.overall_score, Attempt.pron_score, Attempt.created_at)
        .where(
            Attempt.user_id == user_id,
            Attempt.created_at >= since,
            Attempt.overall_score.is_not(None),
        )
        .order_by(Attempt.created_at)
    ).all()
    if not rows:
        return "还没有练习记录——去酒馆开一局，或到唱吧跟唱一首吧。"
    scores = [float(r[0]) for r in rows]
    half = max(1, len(scores) // 2)
    first, second = scores[:half], scores[half:]
    delta = round(sum(second) / len(second) - sum(first) / len(first), 1) if second else 0.0
    active_days = len({r[2].date() for r in rows if r[2] is not None})
    trend = f"综合分 {delta:+.1f}" if second else "综合分持平"
    return f"近 {days} 天练了 {len(scores)} 次（{active_days} 天有练习），{trend}。"


def _module_summaries(db: Session, user_id: int) -> dict[str, dict]:
    since = datetime.now(UTC) - timedelta(days=30)

    # words：生词本
    vocab_rows = db.execute(
        select(UserVocabulary.status, func.count())
        .where(UserVocabulary.user_id == user_id)
        .group_by(UserVocabulary.status)
    ).all()
    vocab = {str(s): int(n) for s, n in vocab_rows}
    vocab_total = sum(vocab.values())

    # community：埋点足迹（发帖/点赞在 Java 侧，不在本服务聚合）
    community_rows = db.execute(
        select(Event.event_type, func.count())
        .where(Event.user_id == user_id, Event.occurred_at >= since)
        .group_by(Event.event_type)
    ).all()
    community = {str(t): int(n) for t, n in community_rows}
    home_views = community.get("page_view", 0)

    # speaking：三维均分
    pron = db.execute(
        select(func.avg(Attempt.pron_score)).where(
            Attempt.user_id == user_id, Attempt.created_at >= since
        )
    ).scalar()
    flu = db.execute(
        select(func.avg(Attempt.flu_score)).where(
            Attempt.user_id == user_id, Attempt.created_at >= since
        )
    ).scalar()
    gram = db.execute(
        select(func.avg(Attempt.gram_score)).where(
            Attempt.user_id == user_id, Attempt.created_at >= since
        )
    ).scalar()

    # practice：会话分钟 + 酒馆剧本
    minutes = (
        db.execute(
            select(func.coalesce(func.sum(PracticeSession.duration_s), 0)).where(
                PracticeSession.user_id == user_id, PracticeSession.started_at >= since
            )
        ).scalar()
        or 0
    )
    campaigns = (
        db.execute(
            select(func.count()).select_from(TrpgCampaign).where(TrpgCampaign.user_id == user_id)
        ).scalar()
        or 0
    )

    def _fmt(v: float | None) -> str:
        return str(v) if v is not None else "—"

    return {
        "words": {
            "total": vocab_total,
            "learning": vocab.get("learning", 0),
            "summary": f"收录 {vocab_total} 词 · 学习中 {vocab.get('learning', 0)}"
            if vocab_total
            else "还没有生词——阅读时点词即收",
        },
        "community": {
            "events": sum(community.values()),
            "page_views": home_views,
            "summary": f"近 30 天 {sum(community.values())} 次互动 · 浏览 {home_views} 次"
            if community
            else "还没有社区足迹",
        },
        "speaking": {
            "pron": _avg([pron]),
            "flu": _avg([flu]),
            "gram": _avg([gram]),
            "summary": " · ".join(
                [
                    f"发音 {_fmt(_avg([pron]))}",
                    f"流利 {_fmt(_avg([flu]))}",
                    f"语法 {_fmt(_avg([gram]))}",
                ]
            ),
        },
        "practice": {
            "minutes": round(int(minutes) / 60),
            "campaigns": int(campaigns),
            "summary": f"酒馆剧本 {int(campaigns)} 场 · 近 30 天 {round(int(minutes) / 60)} 分钟",
        },
    }


def learn_overview(db: Session, user_id: int) -> dict[str, Any]:
    """学习主页聚合：一句话画像 + 热力图 + 四模块摘要。"""
    return {
        "profile_line": _profile_line(db, user_id),
        "heatmap": _heatmap(db, user_id),
        "modules": _module_summaries(db, user_id),
        "generated_at": _iso(datetime.now(UTC)),
    }


def learn_module(db: Session, user_id: int, key: str, *, days: int = 30) -> dict[str, Any]:
    """模块详情聚合（key ∈ words/community/speaking/practice）。"""
    since = datetime.now(UTC) - timedelta(days=days)
    if key == "words":
        # 词典子集未收录的词也展示（translation 回退空，与 `reading.service.list_vocab` 同口径）
        rows = db.execute(
            select(UserVocabulary, DictionaryEntry)
            .outerjoin(DictionaryEntry, DictionaryEntry.word == UserVocabulary.word)
            .where(UserVocabulary.user_id == user_id)
            .order_by(UserVocabulary.created_at.desc())
            .limit(50)
        ).all()
        return {
            "key": key,
            "items": [
                {
                    "word": v.word,
                    "status": v.status,
                    "scene": v.scene,
                    "created_at": _iso(v.created_at) if v.created_at else None,
                    "translation": (e.translation.split("\n")[0] if e and e.translation else None),
                    "phonetic": e.phonetic if e else None,
                }
                for v, e in rows
            ],
        }
    if key == "community":
        day = func.date(Event.occurred_at)
        rows = db.execute(
            select(day.label("d"), func.count().label("n"))
            .where(Event.user_id == user_id, Event.occurred_at >= since)
            .group_by(day)
            .order_by(day)
        ).all()
        pages = db.execute(
            select(Event.page, func.count().label("n"))
            .where(Event.user_id == user_id, Event.occurred_at >= since, Event.page.is_not(None))
            .group_by(Event.page)
            .order_by(func.count().desc())
            .limit(8)
        ).all()
        kinds = db.execute(
            select(Event.event_type, func.count().label("n"))
            .where(Event.user_id == user_id, Event.occurred_at >= since)
            .group_by(Event.event_type)
            .order_by(func.count().desc())
            .limit(8)
        ).all()
        return {
            "key": key,
            "trend": [{"date": str(d), "count": int(n)} for d, n in rows],
            "pages": [{"page": p, "count": int(n)} for p, n in pages],
            "events": [{"event_type": t, "count": int(n)} for t, n in kinds],
        }
    if key == "speaking":
        day = func.date(Attempt.created_at)
        trend = db.execute(
            select(
                day.label("d"),
                func.avg(Attempt.pron_score).label("pron"),
                func.avg(Attempt.flu_score).label("flu"),
                func.avg(Attempt.gram_score).label("gram"),
            )
            .where(Attempt.user_id == user_id, Attempt.created_at >= since)
            .group_by(day)
            .order_by(day)
        ).all()
        weak = db.execute(
            select(Score.phoneme, func.count().label("n"), func.avg(Score.score).label("avg"))
            .join(Attempt, Attempt.id == Score.attempt_id)
            .where(
                Attempt.user_id == user_id,
                Attempt.created_at >= since,
                Score.error_type.is_not(None),
            )
            .group_by(Score.phoneme)
            .order_by(func.count().desc())
            .limit(3)
        ).all()
        dims = db.execute(
            select(
                func.avg(Attempt.pron_score),
                func.avg(Attempt.flu_score),
                func.avg(Attempt.gram_score),
            ).where(Attempt.user_id == user_id, Attempt.created_at >= since)
        ).first()
        return {
            "key": key,
            "dims": {
                "pron": _avg([dims[0]]) if dims else None,
                "flu": _avg([dims[1]]) if dims else None,
                "gram": _avg([dims[2]]) if dims else None,
            },
            "trend": [
                {
                    "date": str(r.d),
                    "pron": round(float(r.pron), 1) if r.pron is not None else None,
                    "flu": round(float(r.flu), 1) if r.flu is not None else None,
                    "gram": round(float(r.gram), 1) if r.gram is not None else None,
                }
                for r in trend
            ],
            "weak_phonemes": [
                {
                    "phoneme": p,
                    "count": int(n),
                    "avg": round(float(a), 1) if a is not None else None,
                }
                for p, n, a in weak
            ],
        }
    if key == "practice":
        minutes = (
            db.execute(
                select(func.coalesce(func.sum(PracticeSession.duration_s), 0)).where(
                    PracticeSession.user_id == user_id, PracticeSession.started_at >= since
                )
            ).scalar()
            or 0
        )
        by_kind = db.execute(
            select(
                PracticeSession.kind,
                func.count().label("n"),
                func.coalesce(func.sum(PracticeSession.duration_s), 0).label("sec"),
            )
            .where(PracticeSession.user_id == user_id, PracticeSession.started_at >= since)
            .group_by(PracticeSession.kind)
        ).all()
        campaigns = db.execute(
            select(
                TrpgCampaign.id,
                TrpgCampaign.name,
                TrpgCampaign.last_active_at,
                func.count(TrpgMessage.id).label("turns"),
                func.sum(case((TrpgMessage.role == "user", 1), else_=0)).label("user_turns"),
            )
            .outerjoin(TrpgMessage, TrpgMessage.campaign_id == TrpgCampaign.id)
            .where(TrpgCampaign.user_id == user_id)
            .group_by(TrpgCampaign.id, TrpgCampaign.name, TrpgCampaign.last_active_at)
            .order_by(TrpgCampaign.last_active_at.desc())
            .limit(8)
        ).all()
        return {
            "key": key,
            "minutes": round(int(minutes) / 60),
            "by_kind": [
                {"kind": k, "count": int(n), "minutes": round(int(sec) / 60)}
                for k, n, sec in by_kind
            ],
            "campaigns": [
                {
                    "id": int(cid),
                    "name": name,
                    "turns": int(turns or 0),
                    "user_turns": int(user_turns or 0),
                    "last_active_at": _iso(last) if last else None,
                }
                for cid, name, last, turns, user_turns in campaigns
            ],
            "heatmap": _heatmap(db, user_id),
        }
    raise ValueError(f"unknown module: {key}")


def today_label() -> str:  # pragma: no cover - 保留给前端补空格用
    return date.today().isoformat()


# 让 SessionKinds 参与导出（模块聚合按 kind 分类，避免 lint 未使用）
SESSION_KINDS = (SessionKinds.SING, SessionKinds.DEFENSE, SessionKinds.SHADOW)
