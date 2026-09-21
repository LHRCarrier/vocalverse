"""场景卡（开局模板）域逻辑：校验归一 / 用户卡 CRUD / 平台卡管理 / LLM 生成 / 开局应用。

设计（docs/52 §12）：
- **来源**：平台固定卡（``owner_user_id`` NULL，管理端草稿→上架→所有用户可选）与用户私有卡
  （按关键词 LLM 生成，仅本人可见）；
- **模板**：``{pc_name, pc:{hp,location,inventory}, facts:[{key,value,modality,speaker}],
  tasks:[title], clues:[{title,content,scene}]}`` —— 应用前逐项经服务器白名单校验
  （LLM 输出不可信，白名单 key 与长度全部在服务端收口）；
- **开局**：建 campaign → 应用模板（system 写者，不置 userTouched）→ 落开场系统卡 +
  开场叙述消息（前言由卡自带，不再花 LLM）→ 之后回合照旧。
"""

from __future__ import annotations

import logging
import random
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select

from app.db import get_session_factory
from app.models.base import (
    TRPG_LANGS,
    TrpgCardSources,
    TrpgCardStatuses,
    TrpgFactModalities,
    TrpgLangs,
)
from app.models.trpg import TrpgScenarioCard
from app.trpg.constants import DOMAIN_PROPERTIES
from app.trpg.facts import FactOp, parse_key
from app.trpg.state import (
    add_message,
    create_campaign,
    create_clue,
    create_task,
    list_tasks,
    set_scene,
    upsert_facts,
)

logger = logging.getLogger("vocalverse")

#: 模板上限（LLM 输出预算；超出截断/丢弃——宽容归一，绝不因个别字段失败整卡）
MAX_TASKS = 6
MAX_CLUES = 6
MAX_TEMPLATE_FACTS = 8
MAX_TAGS = 6

#: 平台卡「随机生成」主题池（管理端点「随机生成」不带关键词时轮换，避免千篇一律）
RANDOM_THEMES = (
    "雨夜小镇与失踪的钟表匠",
    "沙漠商队与埋在地下的城门",
    "蒸汽都市的下水道与失窃图纸",
    "雪山哨站的补给危机",
    "深林古庙的守夜人",
    "远洋商船上的幽灵船员",
    "边境驿站的午夜来客",
    "废弃矿坑深处的回声",
)


# ---------------------------------------------------------------------------
# 归一 / 校验
# ---------------------------------------------------------------------------
def _clean_str(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def normalize_card(payload: dict, *, default_lang: str = TrpgLangs.ZH) -> dict:
    """宽容归一 LLM/表单输出为卡片字段（截断 + 丢弃非法项）；仅 ``title`` 必填。

    白名单收口点：模板 facts 的 key 必须能被 :func:`parse_key` 解析且在域属性白名单内，
    非法条目直接丢弃（不报错——LLM 生成质量参差，宁少勿坏）。
    """
    data = payload if isinstance(payload, dict) else {}
    title = _clean_str(data.get("title"), 60)
    if not title:
        raise ValueError("title required")

    lang = data.get("language") if data.get("language") in TRPG_LANGS else default_lang
    tags_raw = data.get("tags") or []
    tags: list[str] = []
    if isinstance(tags_raw, list):
        for item in tags_raw:
            if len(tags) >= MAX_TAGS:
                break
            s = _clean_str(item, 12)
            if s and s not in tags:
                tags.append(s)

    template_raw = data.get("template") if isinstance(data.get("template"), dict) else {}
    template = _normalize_template(template_raw)

    return {
        "title": title,
        "summary": _clean_str(data.get("summary"), 300) or None,
        "language": lang,
        "tags": tags or None,
        "scene": _clean_str(data.get("scene"), 40) or None,
        "opening_line": _clean_str(data.get("opening_line"), 600) or None,
        "template": template,
    }


def _normalize_template(raw: dict) -> dict:
    pc_name = _clean_str(raw.get("pc_name"), 20) or "主角"
    pc_raw = raw.get("pc") if isinstance(raw.get("pc"), dict) else {}
    pc: dict[str, str] = {}
    for prop in ("hp", "location", "inventory"):
        if prop in pc_raw and pc_raw[prop] not in (None, ""):
            pc[prop] = _clean_str(pc_raw[prop], 60)

    facts: list[dict] = []
    facts_raw = raw.get("facts") or []
    if isinstance(facts_raw, list):
        for item in facts_raw[:MAX_TEMPLATE_FACTS]:
            if not isinstance(item, dict):
                continue
            key = _clean_str(item.get("key"), 80)
            value = _clean_str(item.get("value"), 200)
            parsed = parse_key(key)
            if parsed is None or parsed.entity is None or not value:
                continue
            if parsed.property not in DOMAIN_PROPERTIES.get(parsed.domain, ()):
                continue
            if parsed.domain == "scene":  # 场景单值由 scene 字段承载，模板不重复
                continue
            modality = (
                item.get("modality")
                if item.get("modality") in ("fact", "claim", "rumor")
                else TrpgFactModalities.FACT
            )
            facts.append(
                {
                    "key": key,
                    "value": value,
                    "modality": modality,
                    "speaker": _clean_str(item.get("speaker"), 60) or None,
                }
            )

    tasks: list[str] = []
    for item in (raw.get("tasks") or [])[:MAX_TASKS]:
        t = _clean_str(item, 60)
        if t:
            tasks.append(t)

    clues: list[dict] = []
    for item in (raw.get("clues") or [])[:MAX_CLUES]:
        if isinstance(item, dict):
            ctitle = _clean_str(item.get("title"), 60)
            if not ctitle:
                continue
            clues.append(
                {
                    "title": ctitle,
                    "content": _clean_str(item.get("content"), 300) or None,
                    "scene": _clean_str(item.get("scene"), 40) or None,
                }
            )

    return {"pc_name": pc_name, "pc": pc, "facts": facts, "tasks": tasks, "clues": clues}


def card_view(row: TrpgScenarioCard, *, include_template: bool = True) -> dict:
    out: dict[str, Any] = {
        "id": row.id,
        "owner_user_id": row.owner_user_id,
        "source": row.source,
        "status": row.status,
        "title": row.title,
        "summary": row.summary,
        "language": row.language,
        "tags": row.tags or [],
        "scene": row.scene,
        "opening_line": row.opening_line,
        "keywords": row.keywords,
        "generated_by": row.generated_by,
        "published_at": row.published_at.isoformat() if row.published_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
    if include_template:
        out["template"] = row.template or {}
    return out


# ---------------------------------------------------------------------------
# 读路径
# ---------------------------------------------------------------------------
def list_cards_for_user(user_id: int) -> list[dict]:
    """可用卡 = 平台已上架卡 + 我的卡（未归档）。我的卡在前（更贴近用户意图）。"""
    db = get_session_factory()()
    try:
        mine = list(
            db.execute(
                select(TrpgScenarioCard)
                .where(
                    TrpgScenarioCard.owner_user_id == user_id,
                    TrpgScenarioCard.status != TrpgCardStatuses.ARCHIVED,
                )
                .order_by(TrpgScenarioCard.id.desc())
            )
            .scalars()
            .all()
        )
        platform = list(
            db.execute(
                select(TrpgScenarioCard)
                .where(
                    TrpgScenarioCard.owner_user_id.is_(None),
                    TrpgScenarioCard.status == TrpgCardStatuses.PUBLISHED,
                )
                .order_by(TrpgScenarioCard.id.asc())
            )
            .scalars()
            .all()
        )
        return [card_view(r) for r in mine] + [card_view(r) for r in platform]
    finally:
        db.close()


def get_card(user_id: int, card_id: int) -> TrpgScenarioCard | None:
    """可取用 = 本人卡（未归档）或平台已上架卡。"""
    db = get_session_factory()()
    try:
        row = db.get(TrpgScenarioCard, card_id)
        if row is None or row.status == TrpgCardStatuses.ARCHIVED:
            return None
        if row.owner_user_id is None:
            return row if row.status == TrpgCardStatuses.PUBLISHED else None
        return row if row.owner_user_id == user_id else None
    finally:
        db.close()


def list_platform_cards(
    *, q: str | None = None, status: str | None = None, page: int = 1, page_size: int = 20
) -> tuple[list[dict], int]:
    db = get_session_factory()()
    try:
        conds = [TrpgScenarioCard.owner_user_id.is_(None)]
        if q:
            conds.append(TrpgScenarioCard.title.ilike(f"%{q}%"))
        if status:
            conds.append(TrpgScenarioCard.status == status)
        total = int(
            db.execute(
                select(func.count()).select_from(TrpgScenarioCard).where(*conds)
            ).scalar_one()
        )
        rows = list(
            db.execute(
                select(TrpgScenarioCard)
                .where(*conds)
                .order_by(TrpgScenarioCard.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            .scalars()
            .all()
        )
        return [card_view(r) for r in rows], total
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 用户卡写路径
# ---------------------------------------------------------------------------
def create_user_card(
    user_id: int,
    payload: dict,
    *,
    keywords: str | None = None,
    generated_by: str = "manual",
) -> dict:
    card = normalize_card(payload, default_lang=TrpgLangs.ZH)
    db = get_session_factory()()
    try:
        row = TrpgScenarioCard(
            owner_user_id=user_id,
            source=TrpgCardSources.USER,
            status=TrpgCardStatuses.PUBLISHED,  # 用户卡创建即可用（无审核流）
            keywords=_clean_str(keywords, 200) or None,
            generated_by=generated_by,
            **card,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return card_view(row)
    finally:
        db.close()


def update_user_card(user_id: int, card_id: int, payload: dict) -> dict | None:
    db = get_session_factory()()
    try:
        row = db.execute(
            select(TrpgScenarioCard).where(
                TrpgScenarioCard.id == card_id,
                TrpgScenarioCard.owner_user_id == user_id,
                TrpgScenarioCard.status != TrpgCardStatuses.ARCHIVED,
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        merged = {
            "title": payload.get("title", row.title),
            "summary": payload.get("summary", row.summary),
            "language": payload.get("language", row.language),
            "tags": payload.get("tags", row.tags),
            "scene": payload.get("scene", row.scene),
            "opening_line": payload.get("opening_line", row.opening_line),
            "template": payload.get("template", row.template),
        }
        card = normalize_card(merged, default_lang=row.language)
        for key, value in card.items():
            setattr(row, key, value)
        db.commit()
        db.refresh(row)
        return card_view(row)
    finally:
        db.close()


def archive_user_card(user_id: int, card_id: int) -> bool:
    db = get_session_factory()()
    try:
        row = db.execute(
            select(TrpgScenarioCard).where(
                TrpgScenarioCard.id == card_id,
                TrpgScenarioCard.owner_user_id == user_id,
            )
        ).scalar_one_or_none()
        if row is None:
            return False
        row.status = TrpgCardStatuses.ARCHIVED
        db.commit()
        return True
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 平台卡写路径（Python 控制台）
# ---------------------------------------------------------------------------
def create_platform_card(payload: dict, *, generated_by: str = "manual") -> dict:
    card = normalize_card(payload, default_lang=TrpgLangs.ZH)
    db = get_session_factory()()
    try:
        row = TrpgScenarioCard(
            owner_user_id=None,
            source=TrpgCardSources.ADMIN,
            status=TrpgCardStatuses.DRAFT,
            generated_by=generated_by,
            **card,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return card_view(row)
    finally:
        db.close()


def update_platform_card(card_id: int, payload: dict) -> dict | None:
    db = get_session_factory()()
    try:
        row = db.execute(
            select(TrpgScenarioCard).where(
                TrpgScenarioCard.id == card_id, TrpgScenarioCard.owner_user_id.is_(None)
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        merged = {
            "title": payload.get("title", row.title),
            "summary": payload.get("summary", row.summary),
            "language": payload.get("language", row.language),
            "tags": payload.get("tags", row.tags),
            "scene": payload.get("scene", row.scene),
            "opening_line": payload.get("opening_line", row.opening_line),
            "template": payload.get("template", row.template),
        }
        card = normalize_card(merged, default_lang=row.language)
        for key, value in card.items():
            setattr(row, key, value)
        db.commit()
        db.refresh(row)
        return card_view(row)
    finally:
        db.close()


def publish_platform_card(card_id: int, status: str) -> dict:
    """上/下架（published/draft/archived）；上架前做字段级校验（violations）。"""
    db = get_session_factory()()
    try:
        row = db.get(TrpgScenarioCard, card_id)
        if row is None or row.owner_user_id is not None:
            raise LookupError("card not found")
        if status not in (
            TrpgCardStatuses.DRAFT,
            TrpgCardStatuses.PUBLISHED,
            TrpgCardStatuses.ARCHIVED,
        ):
            raise ValueError("status invalid")
        if status == TrpgCardStatuses.PUBLISHED:
            violations = publish_violations(row)
            if violations:
                raise PermissionError(violations)  # 由路由转 46011（data.violations）
        row.status = status
        row.published_at = datetime.now(UTC) if status == TrpgCardStatuses.PUBLISHED else None
        db.commit()
        db.refresh(row)
        return card_view(row)
    finally:
        db.close()


def publish_violations(row: TrpgScenarioCard) -> list[dict]:
    """上架校验（46011 的 violations 形状：{field, reason, message}）。"""
    out: list[dict] = []
    if not (row.title or "").strip():
        out.append({"field": "title", "reason": "empty", "message": "卡片标题不能为空"})
    if not (row.scene or "").strip():
        out.append({"field": "scene", "reason": "empty", "message": "起始场景不能为空"})
    if not (row.opening_line or "").strip():
        out.append({"field": "opening_line", "reason": "empty", "message": "开场叙述不能为空"})
    return out


# ---------------------------------------------------------------------------
# LLM 生成
# ---------------------------------------------------------------------------
async def generate_card(llm, keywords: str, lang: str) -> dict:
    """按关键词（管理端可为空=随机主题）生成卡片草稿；**不落库**（草稿由调用方决定存否）。

    失败语义：LLM 返回无法解析 → ``ValueError``（路由转 47003）。
    """
    from app.trpg.prompts import build_card_prompt

    theme = keywords.strip() or random.choice(RANDOM_THEMES)  # noqa: S311 - 演示用主题轮换
    prompt = build_card_prompt(theme, lang)
    raw = await llm.chat([{"role": "user", "content": prompt}], temperature=0.9, max_tokens=900)
    payload = _extract_json(raw)
    if payload is None:
        raise ValueError("LLM 输出不是合法 JSON")
    try:
        card = normalize_card(payload, default_lang=lang)
    except ValueError as exc:
        raise ValueError(f"生成结果不可用：{exc}") from exc
    # 语言兜底：模型偶尔忽略语言指令 → 以请求语言为准（卡片语言与 DM 输出一致）
    card["language"] = lang if lang in TRPG_LANGS else card["language"]
    return card


def _extract_json(raw: str) -> dict | None:
    import json
    import re

    text = (raw or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
    except (ValueError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


# ---------------------------------------------------------------------------
# 开局：卡片 → campaign
# ---------------------------------------------------------------------------
def start_campaign_from_card(user_id: int, card: TrpgScenarioCard) -> int:
    """建 campaign + 应用模板 + 落开场卡与开场叙述；返回 campaign_id。"""
    campaign = create_campaign(user_id, card.title)
    campaign_id = campaign.id
    template = card.template or {}
    _apply_template(campaign_id, template)
    scene = (card.scene or "").strip()
    if scene:
        set_scene(campaign_id, scene)

    active_tasks = [t["title"] for t in list_tasks(campaign_id) if t["status"] == "active"]
    add_message(
        campaign_id,
        "assistant",
        "",
        kind="system",
        payload={
            "trpg_sys": "open",
            "campaign_name": card.title,
            "scene": scene or None,
            "tasks": active_tasks,
        },
        meta={"trpg_sys": "open"},
    )
    if (card.opening_line or "").strip():
        add_message(campaign_id, "assistant", card.opening_line.strip())
    # 让"最近活跃"排到最前（用户开新局后列表顺序符合直觉）
    from app.trpg.state import touch_campaign

    touch_campaign(campaign_id)
    return campaign_id


def _apply_template(campaign_id: int, template: dict) -> None:
    pc_name = _clean_str(template.get("pc_name"), 20) or "主角"
    ops: list[FactOp] = []
    for prop, value in (template.get("pc") or {}).items():
        key = f"pc.{pc_name}.{prop}"
        ops.append(FactOp(op="create", key=key, value=str(value), writer="system"))
    for item in template.get("facts") or []:
        if not isinstance(item, dict) or not item.get("key"):
            continue
        ops.append(
            FactOp(
                op="create",
                key=str(item["key"]),
                value=str(item.get("value") or ""),
                modality=item.get("modality") or "fact",
                speaker=item.get("speaker"),
                writer="system",
            )
        )
    if ops:
        upsert_facts(campaign_id, ops)
    for title in template.get("tasks") or []:
        if isinstance(title, str) and title.strip():
            create_task(campaign_id, title.strip(), None)
    for clue in template.get("clues") or []:
        if isinstance(clue, dict) and clue.get("title"):
            create_clue(
                campaign_id,
                str(clue["title"]),
                clue.get("content"),
                clue.get("scene"),
            )


# ---------------------------------------------------------------------------
# 偏好（跨设备）
# ---------------------------------------------------------------------------
def get_prefs(user_id: int) -> dict:
    from app.models.trpg import TrpgUserPref

    db = get_session_factory()()
    try:
        row = db.execute(
            select(TrpgUserPref).where(TrpgUserPref.user_id == user_id)
        ).scalar_one_or_none()
        if row is None:
            return {
                "lang": TrpgLangs.ZH,
                "voice_enabled": True,
                "voice_name": None,
                "persisted": False,
            }
        return {
            "lang": row.lang,
            "voice_enabled": bool(row.voice_enabled),
            "voice_name": row.voice_name,
            "persisted": True,
        }
    finally:
        db.close()


def update_prefs(user_id: int, patch: dict) -> dict:
    from app.models.trpg import TrpgUserPref

    lang = patch.get("lang")
    if lang is not None and lang not in TRPG_LANGS:
        raise ValueError("lang invalid")
    db = get_session_factory()()
    try:
        row = db.execute(
            select(TrpgUserPref).where(TrpgUserPref.user_id == user_id)
        ).scalar_one_or_none()
        if row is None:
            row = TrpgUserPref(user_id=user_id)
            db.add(row)
        if lang is not None:
            row.lang = lang
        if patch.get("voice_enabled") is not None:
            row.voice_enabled = bool(patch["voice_enabled"])
        if "voice_name" in patch:
            name = _clean_str(patch.get("voice_name"), 40)
            row.voice_name = name or None
        db.commit()
        db.refresh(row)
        return {
            "lang": row.lang,
            "voice_enabled": bool(row.voice_enabled),
            "voice_name": row.voice_name,
            "persisted": True,
        }
    finally:
        db.close()


__all__ = [
    "RANDOM_THEMES",
    "archive_user_card",
    "card_view",
    "create_platform_card",
    "create_user_card",
    "generate_card",
    "get_card",
    "get_prefs",
    "list_cards_for_user",
    "list_platform_cards",
    "normalize_card",
    "publish_platform_card",
    "publish_violations",
    "start_campaign_from_card",
    "update_platform_card",
    "update_prefs",
    "update_user_card",
]
