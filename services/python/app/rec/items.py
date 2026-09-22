"""内容型推荐（docs/53 P3 · docs/06 §9.5）：歌 / 书 / 酒馆场景卡跨类候选。

算法 = **内容型冷启动基线**（业界在数据稀疏下的通行做法，见 docs/53 §3 借用清单：
TF-IDF + 余弦相似度 + 侧信息匹配；arXiv 2504.02288 EASE-with-side-features 一系结论）：
不引协同过滤（demo 账号 3~5 个，CF 无数据可学）。

打分 = 0.55·水平匹配 + 0.30·内容相似（用户兴趣标签 ↔ 条目文本）+ 0.15·新鲜度；
候选 = published 歌曲 / published 书籍 / 平台固定场景卡（owner_user_id IS NULL）。
曝光埋点：每次渲染写一条 ``recommend_impression``（``recommend_group_id`` 关联点击，
CTR 口径见 docs/06 §9.1）；写方唯一性 = 只读内容表 + 只写 events（仅追加）。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.analytics import Event
from app.models.base import EventTypes
from app.models.content import Song
from app.models.reading import Book
from app.models.trpg import TrpgScenarioCard
from app.rec.service import resolve_level

logger = logging.getLogger("vocalverse")

LEVELS = ("L1", "L2", "L3", "L4")
RULE_VERSION = "items-content-v1"
_W_LEVEL, _W_CONTENT, _W_FRESH = 0.55, 0.30, 0.15
#: 品类中文名（reason 文案用）
KIND_LABEL = {"song": "歌曲", "book": "读物", "card": "场景卡"}


def _song_level(level: int | None) -> str:
    idx = max(1, min(4, int(level or 1)))
    return LEVELS[idx - 1]


def _level_score(item_level: str | None, user_level: str) -> float:
    if item_level is None:
        return 0.5
    if item_level == user_level:
        return 1.0
    delta = abs(LEVELS.index(item_level) - LEVELS.index(user_level))
    return 0.6 if delta == 1 else 0.2


def _fresh_score(created_at: datetime | None) -> float:
    if created_at is None:
        return 0.0
    created = created_at.replace(tzinfo=UTC) if created_at.tzinfo is None else created_at
    days = max(0.0, (datetime.now(UTC) - created).total_seconds() / 86400)
    return max(0.0, 1.0 - days / 180.0)


def _candidates(db: Session) -> list[dict]:
    """三类候选统一成 {kind,id,title,subtitle,level,text,created_at}。"""
    out: list[dict] = []
    for song in db.execute(select(Song).where(Song.status == "published")).scalars():
        tags = song.interest_tags or []
        tag_text = " ".join(str(t) for t in tags) if isinstance(tags, list) else ""
        out.append(
            {
                "kind": "song",
                "id": int(song.id),
                "title": song.title,
                "subtitle": song.artist or "唱吧",
                "level": _song_level(song.level),
                "text": f"{song.title} {song.artist or ''} {tag_text}",
                "created_at": song.created_at,
            }
        )
    for book in db.execute(select(Book).where(Book.status == "published")).scalars():
        out.append(
            {
                "kind": "book",
                "id": int(book.id),
                "title": book.title,
                "subtitle": book.author,
                "level": book.level,
                "text": f"{book.title} {book.author} {book.description or ''}",
                "created_at": book.created_at,
            }
        )
    for card in db.execute(
        select(TrpgScenarioCard).where(
            TrpgScenarioCard.status == "published", TrpgScenarioCard.owner_user_id.is_(None)
        )
    ).scalars():
        out.append(
            {
                "kind": "card",
                "id": int(card.id),
                "title": card.title,
                "subtitle": card.summary or "酒馆场景卡",
                "level": None,
                "text": f"{card.title} {card.summary or ''}",
                "created_at": card.created_at,
            }
        )
    return out


def _content_similarity(user_tags: set[str], items: list[dict]) -> list[float]:
    """TF-IDF(char n-gram) + 余弦：用户兴趣标签为 query，条目文本为语料。"""
    if not user_tags or not items:
        return [0.0] * len(items)
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity

        docs = [str(it["text"]) for it in items]
        vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), min_df=1)
        matrix = vec.fit_transform(docs)
        query = vec.transform([" ".join(sorted(user_tags))])
        return [float(x) for x in cosine_similarity(query, matrix)[0]]
    except Exception as exc:  # 依赖缺失/文本异常 → 降级为纯规则（不阻塞推荐）
        logger.warning("内容相似度计算失败，降级纯规则：%s", exc)
        return [0.0] * len(items)


def _user_tags(db: Session, user_id: int) -> set[str]:
    from app.models.user import UserProfile

    row = db.execute(
        select(UserProfile.interest_tags).where(UserProfile.user_id == user_id)
    ).first()
    tags = row[0] if row else None
    return {str(t) for t in tags} if isinstance(tags, list) else set()


def recommend_items(db: Session, user_id: int, *, limit: int = 3, kind: str | None = None) -> dict:
    """跨类内容推荐：返回 {items, level, rule_version, recommend_group_id} 并写曝光埋点。"""
    user_level = resolve_level(db, user_id)
    tags = _user_tags(db, user_id)
    items = [it for it in _candidates(db) if kind is None or it["kind"] == kind]
    sims = _content_similarity(tags, items)

    scored: list[dict] = []
    for it, sim in zip(items, sims, strict=True):
        score = (
            _W_LEVEL * _level_score(it["level"], user_level)
            + _W_CONTENT * sim
            + _W_FRESH * _fresh_score(it["created_at"])
        )
        reason_parts = []
        if it["level"] == user_level:
            reason_parts.append(f"匹配 {user_level}")
        elif it["level"]:
            reason_parts.append(f"{it['level']} 难度")
        if sim > 0.01:
            reason_parts.append("命中兴趣")
        scored.append(
            {
                "kind": it["kind"],
                "id": it["id"],
                "title": it["title"],
                "subtitle": it["subtitle"],
                "level": it["level"],
                "score": round(score, 4),
                "reason": " · ".join(reason_parts) or KIND_LABEL.get(it["kind"], "推荐"),
            }
        )
    scored.sort(key=lambda x: x["score"], reverse=True)
    top = scored[: max(1, limit)]

    group_id = uuid4().hex
    if top:
        db.add(
            Event(
                user_id=user_id,
                event_type=EventTypes.RECOMMEND_IMPRESSION,
                occurred_at=datetime.now(UTC),
                recommend_group_id=group_id,
                level=user_level,
                payload={
                    "content_type": "items",
                    "items": [{"kind": t["kind"], "id": t["id"]} for t in top],
                    "rule_version": RULE_VERSION,
                },
            )
        )
        db.commit()

    return {
        "items": top,
        "level": user_level,
        "rule_version": RULE_VERSION,
        "recommend_group_id": group_id,
    }
