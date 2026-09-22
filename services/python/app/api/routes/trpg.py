"""酒馆（TRPG 跑团）路由：剧本 CRUD / 主持台面板 / 场景卡 / 偏好 / SSE 回合（docs/52 §4、§12）。

拓扑：前端直连 Python（SSE 热路径）；JWT 由 Java 签发、本服务验签；剧本为用户私有，
所有端点先校验归属（越权按资源不存在处理，不泄露存在性）。

错误码（docs/api/error-codes.md 47001/47002）：
- 47001（422）：酒馆入参非法（名称/事实 key/场景名/骰子/任务线索字段/缺输入）；
- 47002（503）：酒馆 AI 未配置（APP_DEEPSEEK_API_KEY 为空，fail-fast 不假流）。
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.audio.base import get_llm_client
from app.audio.upload import validate_audio_bytes
from app.console.trace.recorder import trace
from app.core.auth import get_current_user_id
from app.core.config import get_settings
from app.core.ratelimit import bucket_limits, consume_all
from app.core.response import BizError, ok
from app.practice import events as practice_events
from app.trpg import cards as card_domain
from app.trpg import events as ev
from app.trpg import state as st
from app.trpg.dice import format_dice_text, parse_dice
from app.trpg.service import stream_turn
from app.trpg.tools import set_scene

router = APIRouter(prefix="/api/v1/trpg", tags=["trpg"])
logger = logging.getLogger("vocalverse")

#: 单次拉取的对话消息上限（前端历史渲染；超出靠事件/事实表，不做无限回溯）
MESSAGE_LIMIT = 200


class CampaignCreate(BaseModel):
    name: str | None = None


class FactEdit(BaseModel):
    key: str
    value: str


class FactKey(BaseModel):
    key: str


class FactRestore(FactEdit):
    pass


class TaskCreate(BaseModel):
    title: str
    scene: str | None = None


class TaskStatus(BaseModel):
    status: str


class ClueCreate(BaseModel):
    title: str
    content: str | None = None
    scene: str | None = None


class ClueRecover(BaseModel):
    recovered: bool


class SceneBody(BaseModel):
    scene: str


class CardUpsert(BaseModel):
    """用户私有卡写入（title 必填；其余可选，服务端宽容归一）。"""

    title: str
    summary: str | None = None
    language: str | None = None
    tags: list[str] | None = None
    scene: str | None = None
    opening_line: str | None = None
    template: dict | None = None


class CardGenerate(BaseModel):
    """按关键词生成卡片草稿（keywords 2-200 字；lang=DM 输出语言兼卡片语言）。"""

    keywords: str
    lang: str | None = None


class TranslateBody(BaseModel):
    """DM 消息翻译（X 式「翻译」按钮）：text ≤2000 字；target 缺省按内容自动判方向。"""

    text: str
    target: str | None = None


class PrefsUpdate(BaseModel):
    lang: str | None = None
    voice_enabled: bool | None = None
    voice_name: str | None = None


class RollBody(BaseModel):
    dice: str
    modifier: int | None = None
    vs: int | None = None
    dc: int | None = None
    effects: list[dict] | None = None


def _require_campaign(campaign_id: int, user_id: int):
    campaign = st.get_campaign_owned(campaign_id, user_id)
    if campaign is None:
        raise BizError(http_status=404, code=40401, message="campaign not found")
    return campaign


@router.get("/campaigns")
async def list_campaigns(user_id: int = Depends(get_current_user_id)):
    """我的剧本列表（按最近活跃倒序）。"""
    rows = await asyncio.to_thread(st.list_campaigns, user_id)
    return ok(
        [
            {
                "id": r.id,
                "name": r.name,
                "last_active_at": r.last_active_at.isoformat() if r.last_active_at else None,
                "create_time": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    )


@router.post("/campaigns")
async def create_campaign(body: CampaignCreate, user_id: int = Depends(get_current_user_id)):
    """新建剧本（名称可空 → 未命名剧本）。"""
    name = (body.name or "").strip()
    if len(name) > 60:
        raise BizError(http_status=422, code=47001, message="剧本名最长 60 字")
    row = await asyncio.to_thread(st.create_campaign, user_id, name)
    return ok({"id": row.id, "name": row.name})


@router.get("/campaigns/{campaign_id}")
async def get_campaign_state(
    campaign_id: int,
    messages: int = MESSAGE_LIMIT,
    user_id: int = Depends(get_current_user_id),
):
    """全量状态（一次拉全：事实/任务/线索/实体/事件/快照/校验 + 最近消息）。"""
    campaign = _require_campaign(campaign_id, user_id)
    state = await asyncio.to_thread(st.campaign_state, campaign_id)
    history = await asyncio.to_thread(st.list_messages, campaign_id, max(1, min(messages, 500)))
    return ok(
        {
            "campaign": {
                "id": campaign.id,
                "name": campaign.name,
                "narrative_summary": campaign.narrative_summary,
            },
            "messages": history,
            **state,
        }
    )


@router.delete("/campaigns/{campaign_id}/messages")
async def clear_messages(campaign_id: int, user_id: int = Depends(get_current_user_id)):
    """清空对话流水（重开本剧本；事实/任务/线索保留）——前端「重新开始」用。"""
    _require_campaign(campaign_id, user_id)
    removed = await asyncio.to_thread(st.clear_messages, campaign_id)
    return ok({"removed": removed})


@router.post("/campaigns/{campaign_id}/turns")
async def post_turn(
    campaign_id: int,
    text: str | None = Form(default=None),
    audio: UploadFile | None = File(default=None),
    lang: str | None = Form(default=None),
    user_id: int = Depends(get_current_user_id),
):
    """回合主入口：multipart（text / audio 至少其一）→ SSE 事件流（docs/52 §4.2）。

    ``lang``：可选覆盖 DM 输出语言（zh|en）；缺省用用户偏好（服务端跨设备保存）。
    """
    campaign = _require_campaign(campaign_id, user_id)
    settings = get_settings()
    if not settings.testing and not settings.deepseek_api_key:
        raise BizError(
            http_status=503,
            code=47002,
            message="酒馆 AI 未配置（APP_DEEPSEEK_API_KEY 为空）",
        )
    typed = (text or "").strip()
    data = await audio.read() if audio is not None else None
    if data is not None:
        data = validate_audio_bytes(
            data,
            min_bytes=settings.min_upload_bytes,
            max_bytes=settings.max_upload_bytes,
        )
        # 时长上限：酒馆语音输入上限独立配置（trpg_max_seconds），超限前置拒绝不扣额度
        with tempfile.NamedTemporaryFile(suffix=".in", delete=False) as tmp:
            tmp.write(data)
            probe_src = tmp.name
        try:
            from app.audio.ffmpeg_utils import probe_duration_seconds

            duration = await probe_duration_seconds(probe_src)
        finally:
            Path(probe_src).unlink(missing_ok=True)
        if duration is not None and duration > settings.trpg_max_seconds:
            raise BizError(
                http_status=422,
                code=47001,
                message=f"语音过长：{duration:.0f}s（上限 {settings.trpg_max_seconds}s）",
            )
    if not typed and data is None:
        raise BizError(http_status=422, code=47001, message="text or audio is required")
    if lang is not None and lang not in ("zh", "en"):
        raise BizError(http_status=422, code=47001, message="lang 需为 zh|en")
    prefs = await asyncio.to_thread(card_domain.get_prefs, user_id)
    effective_lang = lang or str(prefs["lang"])

    # 分桶限流：预检（归属/输入/时长）通过后再扣；audio 轮 ASR + LLM 一起扣（P1-13 口径）
    limits = bucket_limits()
    buckets = [("llm", limits["llm"])]
    if data is not None:
        buckets.insert(0, ("asr", limits["asr"]))
    await consume_all(buckets, user_id)

    async def event_stream():
        try:
            core = stream_turn(
                campaign,
                typed or None,
                data,
                llm=get_llm_client(),
                lang=effective_lang,
                voice_enabled=bool(prefs["voice_enabled"]),
                voice_name=prefs.get("voice_name"),
            )
            # docs/50 §7.2：整回合一个 trace（含 LLM 流式与工具扇出；失败留痕）
            with trace(kind="trpg", user_id=user_id):
                async for event in practice_events.heartbeat_stream(
                    core, settings.sse_heartbeat_seconds, serialize=practice_events.sse_payload
                ):
                    yield event
        except Exception as exc:  # noqa: BLE001 - 流内错误交给前端（节奏优先）
            logger.exception("trpg turn failed: %s", exc)
            yield practice_events.sse_payload(ev.StreamError(code="internal", recoverable=True))

    headers = {"X-Accel-Buffering": "no", "Cache-Control": "no-cache"}
    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=headers)


# ---------------------------------------------------------------------------
# 主持台面板（用户权威路径；前端抽屉消费）
# ---------------------------------------------------------------------------
@router.post("/campaigns/{campaign_id}/facts/edit")
async def edit_fact(campaign_id: int, body: FactEdit, user_id: int = Depends(get_current_user_id)):
    _require_campaign(campaign_id, user_id)
    if not body.key.strip() or len(body.value) > 200:
        raise BizError(http_status=422, code=47001, message="key/value 非法")
    done = await asyncio.to_thread(st.edit_fact, campaign_id, body.key.strip(), body.value.strip())
    return ok({"ok": done})


@router.post("/campaigns/{campaign_id}/facts/delete")
async def delete_fact(campaign_id: int, body: FactKey, user_id: int = Depends(get_current_user_id)):
    _require_campaign(campaign_id, user_id)
    done = await asyncio.to_thread(st.delete_fact, campaign_id, body.key.strip())
    return ok({"ok": done})


@router.post("/campaigns/{campaign_id}/facts/restore")
async def restore_fact(
    campaign_id: int, body: FactRestore, user_id: int = Depends(get_current_user_id)
):
    _require_campaign(campaign_id, user_id)
    done = await asyncio.to_thread(
        st.restore_fact, campaign_id, body.key.strip(), body.value.strip()
    )
    return ok({"ok": done})


@router.post("/campaigns/{campaign_id}/tasks")
async def create_task(
    campaign_id: int, body: TaskCreate, user_id: int = Depends(get_current_user_id)
):
    _require_campaign(campaign_id, user_id)
    done = await asyncio.to_thread(st.create_task, campaign_id, body.title, body.scene)
    if not done:
        raise BizError(http_status=422, code=47001, message="任务标题不能为空")
    return ok({"ok": True})


@router.post("/campaigns/{campaign_id}/tasks/{task_id}/status")
async def set_task_status(
    campaign_id: int,
    task_id: int,
    body: TaskStatus,
    user_id: int = Depends(get_current_user_id),
):
    _require_campaign(campaign_id, user_id)
    done = await asyncio.to_thread(st.set_task_status, campaign_id, task_id, body.status)
    if not done:
        raise BizError(http_status=422, code=47001, message="任务不存在或状态非法")
    return ok({"ok": True})


@router.post("/campaigns/{campaign_id}/clues")
async def create_clue(
    campaign_id: int, body: ClueCreate, user_id: int = Depends(get_current_user_id)
):
    _require_campaign(campaign_id, user_id)
    done = await asyncio.to_thread(
        st.create_clue, campaign_id, body.title, body.content, body.scene
    )
    if not done:
        raise BizError(http_status=422, code=47001, message="线索标题不能为空")
    return ok({"ok": True})


@router.post("/campaigns/{campaign_id}/clues/{clue_id}/recover")
async def set_clue_recover(
    campaign_id: int,
    clue_id: int,
    body: ClueRecover,
    user_id: int = Depends(get_current_user_id),
):
    _require_campaign(campaign_id, user_id)
    done = await asyncio.to_thread(st.set_clue_recovered, campaign_id, clue_id, body.recovered)
    if not done:
        raise BizError(http_status=404, code=40401, message="clue not found")
    return ok({"ok": True})


@router.post("/campaigns/{campaign_id}/scene")
async def set_campaign_scene(
    campaign_id: int, body: SceneBody, user_id: int = Depends(get_current_user_id)
):
    _require_campaign(campaign_id, user_id)
    scene = body.scene.strip()[:40]
    if not scene:
        raise BizError(http_status=422, code=47001, message="场景名不能为空")
    await asyncio.to_thread(set_scene, campaign_id, scene)
    return ok({"ok": True})


@router.post("/campaigns/{campaign_id}/roll")
async def roll_dice(campaign_id: int, body: RollBody, user_id: int = Depends(get_current_user_id)):
    """桌骰：系统判定并落表（与 DM 的 roll_dice 工具同一条写路径）。"""
    _require_campaign(campaign_id, user_id)
    result = parse_dice(body.model_dump())
    if result is None:
        raise BizError(http_status=422, code=47001, message="骰子参数非法")
    from app.trpg.state import apply_dice_delta

    summary = await asyncio.to_thread(apply_dice_delta, campaign_id, result)
    state = await asyncio.to_thread(st.campaign_state, campaign_id)
    return ok({"text": format_dice_text(result), "summary": summary, "state": state})


@router.post("/campaigns/{campaign_id}/narrative/refresh")
async def refresh_narrative(campaign_id: int, user_id: int = Depends(get_current_user_id)):
    """重新渲染叙事摘要（P2-45 状态模板渲染；零 LLM 成本）。"""
    _require_campaign(campaign_id, user_id)
    summary = await asyncio.to_thread(st.render_narrative_summary, campaign_id)
    return ok({"narrative_summary": summary})


# ---------------------------------------------------------------------------
# 场景卡（开局模板：平台固定卡 + 用户私有卡；docs/52 §12）
# ---------------------------------------------------------------------------
@router.get("/cards")
async def list_cards(user_id: int = Depends(get_current_user_id)):
    """可用场景卡 = 我的卡（未归档）+ 平台已上架卡（我的在前）。"""
    items = await asyncio.to_thread(card_domain.list_cards_for_user, user_id)
    return ok({"items": items})


@router.post("/cards")
async def create_card(body: CardUpsert, user_id: int = Depends(get_current_user_id)):
    """新建用户私有卡（手工或保存生成草稿）。"""
    try:
        card = await asyncio.to_thread(
            card_domain.create_user_card,
            user_id,
            body.model_dump(),
            keywords=None,
            generated_by="manual",
        )
    except ValueError as exc:
        raise BizError(http_status=422, code=47003, message=str(exc)) from exc
    return ok(card)


@router.put("/cards/{card_id}")
async def update_card(card_id: int, body: CardUpsert, user_id: int = Depends(get_current_user_id)):
    try:
        card = await asyncio.to_thread(
            card_domain.update_user_card, user_id, card_id, body.model_dump()
        )
    except ValueError as exc:
        raise BizError(http_status=422, code=47003, message=str(exc)) from exc
    if card is None:
        raise BizError(http_status=404, code=40401, message="card not found")
    return ok(card)


@router.delete("/cards/{card_id}")
async def delete_card(card_id: int, user_id: int = Depends(get_current_user_id)):
    """归档用户私有卡（软删；不影响已开局的 campaign）。"""
    done = await asyncio.to_thread(card_domain.archive_user_card, user_id, card_id)
    if not done:
        raise BizError(http_status=404, code=40401, message="card not found")
    return ok({"ok": True})


@router.post("/cards/generate")
async def generate_card(body: CardGenerate, user_id: int = Depends(get_current_user_id)):
    """按关键词让 LLM 生成卡片草稿（**不落库**；用户确认后走 POST /cards 保存并开局）。

    限流：扣 llm 桶（与回合共享 30/时）；生成失败 → 47003（可重试/换词）。
    """
    keywords = body.keywords.strip()
    if not (1 <= len(keywords) <= 200):
        raise BizError(http_status=422, code=47003, message="关键词需 1-200 字")
    lang = body.lang if body.lang in ("zh", "en") else None
    if lang is None:
        prefs = await asyncio.to_thread(card_domain.get_prefs, user_id)
        lang = str(prefs["lang"])
    limits = bucket_limits()
    await consume_all([("llm", limits["llm"])], user_id)
    try:
        draft = await card_domain.generate_card(get_llm_client(), keywords, lang)
    except ValueError as exc:
        raise BizError(http_status=422, code=47003, message=f"生成失败：{exc}") from exc
    except Exception as exc:  # noqa: BLE001 - 上游异常统一 50001（用户可重试）
        logger.exception("trpg card generate failed: %s", exc)
        raise BizError(http_status=500, code=50001, message="生成失败，请稍后重试") from exc
    return ok(draft)


@router.post("/cards/{card_id}/start")
async def start_card(card_id: int, user_id: int = Depends(get_current_user_id)):
    """从卡片开局：建剧本 + 应用模板（场景/初始事实/任务/线索）+ 开场叙述落库。"""
    card = await asyncio.to_thread(card_domain.get_card, user_id, card_id)
    if card is None:
        raise BizError(http_status=404, code=40401, message="card not found")
    campaign_id = await asyncio.to_thread(card_domain.start_campaign_from_card, user_id, card)
    return ok({"campaign_id": campaign_id})


# ---------------------------------------------------------------------------
# 偏好（跨设备；docs/52 §12.2）
# ---------------------------------------------------------------------------
@router.get("/preferences")
async def get_preferences(user_id: int = Depends(get_current_user_id)):
    """酒馆偏好（lang/voice_enabled/voice_name）；未设置过返回默认值（persisted=false）。"""
    return ok(await asyncio.to_thread(card_domain.get_prefs, user_id))


@router.put("/preferences")
async def put_preferences(body: PrefsUpdate, user_id: int = Depends(get_current_user_id)):
    """更新偏好（部分字段；未提供的字段保持不变）。"""
    try:
        prefs = await asyncio.to_thread(
            card_domain.update_prefs, user_id, body.model_dump(exclude_unset=True)
        )
    except ValueError as exc:
        raise BizError(http_status=422, code=47001, message=str(exc)) from exc
    return ok(prefs)


@router.post("/translate")
async def translate_message(body: TranslateBody, user_id: int = Depends(get_current_user_id)):
    """把一条 DM 消息译成另一种语言（中英互切；原文不动，前端切换展示）。

    限流：扣 llm 桶（与回合共享）；失败 → 47003（可重试）。
    """
    text = body.text.strip()
    if not (1 <= len(text) <= 2000):
        raise BizError(http_status=422, code=47001, message="text 需 1-2000 字")
    if body.target is not None and body.target not in ("zh", "en"):
        raise BizError(http_status=422, code=47001, message="target 需为 zh|en")
    target = body.target or card_domain.detect_target(text)
    limits = bucket_limits()
    await consume_all([("llm", limits["llm"])], user_id)
    try:
        translated = await card_domain.translate_text(get_llm_client(), text, target)
    except ValueError as exc:
        raise BizError(http_status=422, code=47003, message=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("trpg translate failed: %s", exc)
        raise BizError(http_status=500, code=50001, message="翻译失败，请稍后重试") from exc
    return ok({"text": translated, "target": target})
