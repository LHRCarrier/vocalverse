"""控制台 · 酒馆场景卡（Python 段：``/api/v1/console/trpg/cards/**``；docs/52 §12.1）。

- 平台固定卡（``owner_user_id`` NULL）由管理端维护：手工新建/编辑 + 「随机生成」草稿 → 上架；
- 权限码 ``content:scenario:read|write|publish``（Java 目录登记，JWT perms 携带）；
- 上架校验失败 → 46011 + ``data.violations[]``（与 library.py 同形状）；
- 生成调用 LLM（真实 Key 缺失时由 Fake 兜底，测试环境零外部依赖）。
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Body, Depends, Path, Query
from pydantic import BaseModel

from app.audio.base import get_llm_client
from app.console.api.deps import ConsoleAdmin, ConsoleBizError, console_guard
from app.core.response import Envelope, ok
from app.db import get_session_factory

router = APIRouter(prefix="/api/v1/console/trpg/cards", tags=["console-trpg"])

#: 上架合法状态（与 ck_trpg_scenario_cards_status 一致）
CARD_STATUSES = ("draft", "published", "archived")


class CardUpsert(BaseModel):
    title: str
    summary: str | None = None
    language: str | None = None
    tags: list[str] | None = None
    scene: str | None = None
    opening_line: str | None = None
    template: dict | None = None


class PublishBody(BaseModel):
    status: str


class GenerateBody(BaseModel):
    keywords: str | None = None
    lang: str | None = None


async def _db_call(fn):
    def _run():
        db = get_session_factory()()
        try:
            return fn(db)
        finally:
            db.close()

    return await asyncio.to_thread(_run)


@router.get("", response_model=Envelope[dict])
async def list_cards(
    q: str | None = Query(default=None),
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    admin: ConsoleAdmin = Depends(console_guard(perm="content:scenario:read")),
) -> Envelope:
    """平台卡列表（只列 owner NULL；用户私有卡不属管理端内容）。"""
    del admin
    from app.trpg.cards import list_platform_cards

    items, total = await asyncio.to_thread(
        list_platform_cards, q=q, status=status, page=page, page_size=page_size
    )
    return ok(
        {
            "items": items,
            "page": page,
            "page_size": page_size,
            "total": total,
            "has_more": page * page_size < total,
        }
    )


@router.post("", response_model=Envelope[dict])
async def create_card(
    body: CardUpsert,
    admin: ConsoleAdmin = Depends(console_guard(perm="content:scenario:write")),
) -> Envelope:
    """新建平台卡（草稿态；编辑好再上架）。"""
    del admin
    from app.trpg.cards import create_platform_card

    try:
        card = await asyncio.to_thread(create_platform_card, body.model_dump())
    except ValueError as exc:
        raise ConsoleBizError(422, 46007, str(exc)) from exc
    return ok(card)


@router.put("/{card_id}", response_model=Envelope[dict])
async def update_card(
    card_id: int = Path(...),
    body: CardUpsert = Body(...),
    admin: ConsoleAdmin = Depends(console_guard(perm="content:scenario:write")),
) -> Envelope:
    del admin
    from app.trpg.cards import update_platform_card

    try:
        card = await asyncio.to_thread(update_platform_card, card_id, body.model_dump())
    except ValueError as exc:
        raise ConsoleBizError(422, 46007, str(exc)) from exc
    if card is None:
        raise ConsoleBizError(404, 46009, "card not found")
    return ok(card)


@router.post("/{card_id}/publish", response_model=Envelope[dict])
async def publish_card(
    card_id: int = Path(...),
    body: PublishBody = Body(...),
    admin: ConsoleAdmin = Depends(console_guard(perm="content:scenario:publish")),
) -> Envelope:
    """上/下架（draft|published|archived）；上架校验失败 → 46011 + violations。"""
    del admin
    if body.status not in CARD_STATUSES:
        raise ConsoleBizError(422, 46007, f"status 非法（{'|'.join(CARD_STATUSES)}）")
    from app.trpg.cards import publish_platform_card

    try:
        card = await asyncio.to_thread(publish_platform_card, card_id, body.status)
    except LookupError as exc:
        raise ConsoleBizError(404, 46009, "card not found") from exc
    except ValueError as exc:
        raise ConsoleBizError(422, 46007, str(exc)) from exc
    except PermissionError as exc:
        violations: Any = exc.args[0] if exc.args else []
        raise ConsoleBizError(422, 46011, "上架校验失败", {"violations": violations}) from exc
    return ok(card)


@router.post("/generate", response_model=Envelope[dict])
async def generate_card(
    body: GenerateBody,
    admin: ConsoleAdmin = Depends(console_guard(perm="content:scenario:write")),
) -> Envelope:
    """随机生成卡片草稿（keywords 空 = 主题池轮换）；**不落库**，人工编辑后保存/上架。"""
    # 限流：控制台账号级（APP_CONSOLE_RATE_PER_MIN）+ RBAC 已覆盖；不再复用学习者 llm 桶
    # （桶键为 str(user_id)，管理员 id 与用户 id 同空间会互相挤占）
    from app.trpg.cards import generate_card as generate

    try:
        card = await generate(
            get_llm_client(),
            (body.keywords or "").strip()[:200],
            body.lang if body.lang in ("zh", "en") else "zh",
        )
    except ValueError as exc:
        raise ConsoleBizError(422, 47003, f"生成失败：{exc}") from exc
    except Exception as exc:  # noqa: BLE001 - LLM/上游异常统一 500（控制台可重试）
        raise ConsoleBizError(500, 50001, f"生成失败：{exc}") from exc
    return ok(card)
