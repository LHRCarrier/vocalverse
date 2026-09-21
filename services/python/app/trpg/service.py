"""酒馆 DM 门面（迁移自 ai4u TrpgService）：会话编排 + DM 上下文 + SSE 回合 + 系统卡。

流程（一次回合）：
1. ``trpg_ready`` → 首回合先落「开场卡」（剧本名/场景/任务）→ 玩家消息（ASR 可选）落库；
2. 首回合恢复校验（P2-34）→【待记住】补丁；
3. 组装 DM 上下文（P2-36：不注入画像/记忆；快照在动态段最末，P2-31）；
4. 工具循环流式生成（roll_dice / set_scene）；
5. DM 消息落库 → ``turn_end``；
6. 系统卡协议（P2-44）：场景变化 → 过场卡；新事件 → 判定卡（落库 + 流内下发，刷新不丢）；
7. DM 回复逐句 TTS（上限 :data:`TTS_MAX_SENTENCES`，缓存命中零成本）；
8. 叙事摘要刷新（P2-45 状态渲染）+ 事实提取（每 2 回合，后台 fire-and-forget）。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any

from app.agent.domains.usage import log_usage
from app.audio.base import LLMClient, TTSClient, get_asr_client, get_tts_client
from app.audio.duration import audio_duration_seconds
from app.audio.textproc.normalize import normalize_for_tts
from app.audio.textproc.sentence_splitter import StreamSentenceSplitter
from app.audio.tts_cache import tts_synthesize_cached
from app.console.trace.recorder import span
from app.core.config import get_settings
from app.models.trpg import TrpgCampaign
from app.practice.orchestrator import save_audio_bytes, save_tts_audio_bytes
from app.trpg import events as ev
from app.trpg import state as st
from app.trpg.constants import (
    DM_MAX_TOKENS,
    DM_TEMPERATURE,
    HISTORY_MESSAGES,
    QUESTION_MAX,
    TTS_MAX_SENTENCES,
)
from app.trpg.extractor import maybe_extract
from app.trpg.prompts import build_dm_system_prompt
from app.trpg.snapshot import (
    SnapshotClue,
    SnapshotFact,
    SnapshotInput,
    SnapshotTask,
    build_state_snapshot,
)
from app.trpg.turn import DmTurnRunner

logger = logging.getLogger("vocalverse")

#: fire-and-forget 任务引用（防 GC；进程退出即弃）
_background_tasks: set[asyncio.Task] = set()


def _spawn(coro) -> None:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def stream_turn(
    campaign: TrpgCampaign,
    user_text: str | None,
    audio_bytes: bytes | None,
    *,
    llm: LLMClient | None = None,
    tts: TTSClient | None = None,
    lang: str = "zh",
    voice_enabled: bool = True,
    voice_name: str | None = None,
) -> AsyncIterator[ev.TrpgEvent]:
    """一次酒馆回合的 SSE 事件流（路由层预检归属/限流后调用）。

    ``lang``：DM 输出语言（来自用户偏好或本回合显式传参）；``voice_enabled`` 关时不逐句 TTS
    （省配额，前端设置里的「语音开关」）；``voice_name`` 为音色预留（NULL = 服务端默认）。
    """
    campaign_id = campaign.id
    is_first = not await asyncio.to_thread(st.has_messages, campaign_id)
    yield ev.TrpgReady(campaign_id=campaign_id, campaign_name=campaign.name, is_first=is_first)

    # 开场卡（UIQ-3/8）：新剧本第一行系统消息——剧本名/场景/任务，营造「走进酒馆」的仪式感
    if is_first:
        open_payload = {
            "campaign_name": campaign.name,
            "scene": await asyncio.to_thread(st.get_scene, campaign_id),
            "tasks": [
                t["title"]
                for t in await asyncio.to_thread(st.list_tasks, campaign_id)
                if t["status"] == "active"
            ],
        }
        await _post_system_row(campaign_id, "open", open_payload)
        yield ev.SystemCard(trpg_sys="open", payload=open_payload)

    # 玩家输入：语音 → ASR（词级时间戳留存）；打字 → 直接使用
    audio_url: str | None = None
    words: list[dict[str, Any]] | None = None
    text = (user_text or "").strip()[:QUESTION_MAX]
    if audio_bytes:
        asr_result = await get_asr_client().transcribe(audio_bytes)
        text = (asr_result.text or "").strip()[:QUESTION_MAX]
        words = asr_result.words or None
        audio_url = await asyncio.to_thread(save_audio_bytes, audio_bytes)
        yield ev.UserTranscript(text=text, audio_url=audio_url, words=words)
    if not text:
        text = "(no speech)"

    user_meta: dict[str, Any] = {}
    if words:
        user_meta["words"] = words
    await asyncio.to_thread(
        st.add_message,
        campaign_id,
        "user",
        text,
        meta=user_meta or None,
        audio_url=audio_url,
    )

    # 恢复校验（P2-34）：首回合强制静态 + 语义校验 → 落差补丁
    restore_patch: str | None = None
    if is_first:
        try:
            verify_result = await asyncio.to_thread(_restore_verify, campaign_id)
            restore_patch = verify_result
        except Exception as exc:  # noqa: BLE001 - 校验失败不阻塞回合
            logger.warning("酒馆恢复校验失败：%s", exc)

    messages = await asyncio.to_thread(
        _build_dm_context, campaign_id, campaign.name, text, restore_patch, lang
    )
    events_before = await asyncio.to_thread(st.count_events, campaign_id)
    scene_before = await asyncio.to_thread(st.get_scene, campaign_id)

    llm = llm or _default_llm()
    tts = tts or get_tts_client()
    runner = DmTurnRunner(llm)
    try:
        with span("LLM", retry_index=0, stream=True, purpose="trpg_dm"):
            async for item in runner.run(
                messages, campaign_id, temperature=DM_TEMPERATURE, max_tokens=DM_MAX_TOKENS
            ):
                if item["type"] == "delta":
                    yield ev.TextDelta(text=str(item["text"]))
                elif item["type"] == "status":
                    yield ev.TrpgStatus(stage=str(item["stage"]))
    except Exception as exc:  # noqa: BLE001 - 流内错误交给前端（节奏优先）
        logger.exception("酒馆 DM 生成失败：%s", exc)
        fallback = "（DM 似乎走神了，请把你的行动再说一遍。）"
        yield ev.TextDelta(text=fallback)
        yield ev.StreamError(code="llm_failed", recoverable=True)
        runner.result = None

    result = runner.result
    content = (result.content if result is not None else "").strip()
    if not content:
        content = "（DM 没有回应，请把话再说一遍）"
    usage = result.usage if result is not None else None
    if usage:
        log_usage("trpg", usage, meta={"campaign_id": campaign_id})

    assistant_message = await asyncio.to_thread(
        st.add_message,
        campaign_id,
        "assistant",
        content,
        usage=usage,
    )
    yield ev.TurnEnd(message_id=assistant_message.id, usage=usage)

    # 系统卡协议（P2-44）：回合后对比事件/场景变化 → 过场卡 / 判定卡
    scene_now = await asyncio.to_thread(st.get_scene, campaign_id)
    if scene_now is not None and scene_now != scene_before:
        payload = {"scene": scene_now, "from": scene_before or ""}
        await _post_system_row(campaign_id, "scene", payload)
        yield ev.SystemCard(trpg_sys="scene", payload=payload)
    new_events = [
        e
        for e in await asyncio.to_thread(st.list_events, campaign_id)
        if e["round"] > events_before
    ]
    if new_events:
        payload = {"text": "\n".join(e["summary"] for e in new_events)}
        await _post_system_row(campaign_id, "dice", payload)
        yield ev.SystemCard(trpg_sys="dice", payload=payload)

    # DM 回复逐句 TTS（前端排队播放；失败逐句降级为无音频；用户关闭语音则不合成）
    if voice_enabled:
        async for chunk in _tts_chunks(tts, content, voice_name):
            yield chunk

    await asyncio.to_thread(st.touch_campaign, campaign_id)
    # 叙事摘要增量刷新（P2-45：状态渲染零 LLM 成本；修复 ai4u「只手动刷新」的欠账）
    try:
        await asyncio.to_thread(st.render_narrative_summary, campaign_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("酒馆叙事摘要刷新失败：%s", exc)
    # 事实提取（每 2 回合，后台 fire-and-forget）
    _spawn(maybe_extract(campaign_id, llm))


def _default_llm() -> LLMClient:
    from app.audio.base import get_llm_client

    return get_llm_client()


def _restore_verify(campaign_id: int) -> str | None:
    """恢复校验：静态悬空 + 落差/矛盾 → 返回【待记住】补丁。"""
    from datetime import UTC, datetime

    from app.trpg.constants import DANGLING_WINDOW_MS
    from app.trpg.verify import (
        build_missing_patch,
        detect_contradiction,
        detect_dangling,
        verify_gap,
    )

    facts = st.list_facts(campaign_id)
    tasks = st.list_tasks(campaign_id)
    clues = st.list_clues(campaign_id)
    summary = ""
    db = None
    try:
        from app.db import get_session_factory

        db = get_session_factory()()
        row = db.get(TrpgCampaign, campaign_id)
        summary = (row.narrative_summary if row is not None else "") or ""
    finally:
        if db is not None:
            db.close()
    dangling = detect_dangling(tasks, clues, datetime.now(UTC), DANGLING_WINDOW_MS)
    gap, missing = verify_gap(dangling, summary)
    contradiction = detect_contradiction(summary, facts)
    if gap or contradiction:
        logger.info(
            "酒馆恢复校验：gap=%s contradiction=%s（campaign=%s）", gap, contradiction, campaign_id
        )
    return build_missing_patch(missing) if gap else None


def _build_dm_context(
    campaign_id: int,
    campaign_name: str,
    question: str,
    restore_patch: str | None,
    lang: str = "zh",
) -> list[dict]:
    """DM 上下文：固定 system → 叙事摘要 → 快照 → 恢复补丁 → 历史 → 本回合输入。

    历史只取 kind=text 消息（修复 ai4u 系统卡空 assistant 混入 prompt 的缺陷）。
    """
    from app.db import get_session_factory

    facts = st.list_facts(campaign_id)
    tasks = st.list_tasks(campaign_id)
    clues = st.list_clues(campaign_id)
    db = get_session_factory()()
    try:
        row = db.get(TrpgCampaign, campaign_id)
        narrative_summary = ((row.narrative_summary if row is not None else "") or "").strip()
    finally:
        db.close()
    history = _recent_text_messages(campaign_id, HISTORY_MESSAGES)

    snapshot = build_state_snapshot(
        SnapshotInput(
            facts=[
                SnapshotFact(
                    key=f["key"],
                    kind=f["kind"],
                    value=f["value"],
                    modality=f["modality"],
                    speaker=f["speaker"],
                    importance=f["importance"],
                )
                for f in facts
            ],
            tasks=[SnapshotTask(title=t["title"], status=t["status"]) for t in tasks],
            clues=[
                SnapshotClue(
                    title=c["title"],
                    content=c["content"],
                    scene=c["scene"],
                    found=c["found"],
                    recovered=c["recovered"],
                    last_mentioned_at=c["last_mentioned_at"],
                )
                for c in clues
            ],
            scene=next((f["value"] for f in facts if f["key"] == "scene.current"), None),
        )
    )

    messages: list[dict] = [
        {"role": "system", "content": build_dm_system_prompt(campaign_name, restore_patch, lang)}
    ]
    if narrative_summary:
        messages.append({"role": "system", "content": f"【当前冒险状态】\n{narrative_summary}"})
    if snapshot:
        messages.append({"role": "system", "content": snapshot})
    if restore_patch:
        messages.append({"role": "system", "content": restore_patch})
    # 历史排除本回合刚落的用户消息（最后一条），避免重复
    for m in history[:-1]:
        messages.append({"role": m["role"], "content": m["content"]})
    messages.append({"role": "user", "content": question})
    return messages


def _recent_text_messages(campaign_id: int, limit: int) -> list[dict]:
    msgs = st.list_messages(campaign_id, limit=limit * 2)
    text_only = [m for m in msgs if m["kind"] == "text"]
    return text_only[-limit:]


async def _post_system_row(campaign_id: int, trpg_sys: str, payload: dict) -> None:
    """系统卡落库（kind=system + payload.trpgSys 协议；失败降级为无卡片，主消息不受影响）。"""
    try:
        await asyncio.to_thread(
            st.add_message,
            campaign_id,
            "assistant",
            "",
            kind="system",
            payload={"trpg_sys": trpg_sys, **payload},
            meta={"trpg_sys": trpg_sys},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("酒馆系统卡落库失败（%s）：%s——降级为无卡片", trpg_sys, exc)


async def _tts_chunks(
    tts: TTSClient, content: str, voice_name: str | None = None
) -> AsyncIterator[ev.AudioChunk]:
    """DM 回复逐句 TTS（并发合成、按序下发；逐句失败静默跳过，绝不阻塞回合）。"""
    settings = get_settings()
    voice = (voice_name or "").strip() or settings.tts_voice
    splitter = StreamSentenceSplitter()
    sentences = splitter.push(content) + splitter.flush()
    sentences = [s for s in sentences if any(c.isalnum() for c in s)][:TTS_MAX_SENTENCES]
    if not sentences:
        return
    tasks: dict[int, asyncio.Task] = {}
    for i, sentence in enumerate(sentences):
        tasks[i] = asyncio.create_task(_tts_one(tts, sentence, voice, settings.tts_rate))
    for i in range(len(sentences)):
        url, duration = await tasks[i]
        if url:
            yield ev.AudioChunk(url=url, duration=duration)


async def _tts_one(
    tts: TTSClient, sentence: str, voice: str, rate: str
) -> tuple[str | None, float | None]:
    try:
        text = normalize_for_tts(sentence, language="en")
        data = await tts_synthesize_cached(tts, text, voice, rate)
        if not data:
            return None, None
        return await asyncio.to_thread(save_tts_audio_bytes, data), audio_duration_seconds(data)
    except Exception as exc:  # noqa: BLE001 - 逐句失败不影响字幕/其余句
        logger.info("酒馆 TTS 单句跳过：%s", exc)
        return None, None
