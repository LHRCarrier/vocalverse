"""M2 回合编排器（docs/14 §3.2/§3.4：ASR→评分并行→LLM 流式→逐句 TTS→SSE）。

设计要点（拷问收敛）：
- 依赖注入：asr/score/llm/tts 均为接口注入（CI/单测走 Fake，docs/06 §6）；
- LLM 一次调用 + 尾部 [-META-]（语法/教练笔记/命中/难度/收尾；失败降级规则兜底 conclude）；
- 评分与 LLM 并行（score_delta 迟到按 turn_index 回填，不阻塞对话流）；
- 命中双态：state=ok（无致命语法错）/fix；retry/hint/demo 轮命中作废（docs/14 §2.1）；
- 会话锁：整个 turn 持有（setnx 语义），并发/重复提交 → 409；
- 音频：route 负责保存原音频并传 audio_url；本层只做回合推进与落库。
"""

from __future__ import annotations

import asyncio
import hashlib
import logging

from app.agent.domains.learner import get_rendered
from app.agent.domains.summarizer import SummarizerService, get_session_summary
from app.agent.domains.usage import log_usage
from app.agent.runtime.meta_executor import MetaExecutor, compensate_meta
from app.agent.runtime.turn_runner import TurnRunner
from app.audio.base import ASRClient, LLMClient, ScorerClient, TTSClient
from app.audio.fluency import compute_fluency_features
from app.core.config import get_settings
from app.db import get_session_factory
from app.models import (
    Attempt,
    Scenario,
    ScenarioMessage,
    ShadowMaterial,
)
from app.models import (
    Session as DbSession,
)
from app.models.base import AttemptKinds, SessionKinds
from app.practice import events as ev
from app.practice.corpus import parse_corpus
from app.practice.meta import MetaResult
from app.practice.service import (
    build_llm_context,
    complete_session,
    tts_sentences,
)
from app.practice.shadow import coach_note, shadow_scores, split_sentences
from app.practice.state import SessionState, get_state_store
from fastapi import HTTPException
from sqlalchemy import select

logger = logging.getLogger("vocalverse")

_meta_executor = MetaExecutor()


class OrchestratorError(HTTPException):
    pass


def _db():
    return get_session_factory()()


async def _tts_url_from_bytes(tts: TTSClient, text: str, voice: str, rate: str) -> str | None:
    """逐句合成并落盘，返回鉴权 URL；失败返回 None（无声字幕继续，docs/14 §3.2）。"""
    try:
        data = await tts.synthesize(text, voice=voice, rate=rate)
    except Exception as exc:  # edge-tts 断网等
        logger.warning("tts failed: %s", exc)
        return None
    return save_audio_bytes(data)


def save_audio_bytes(data: bytes) -> str:
    """写入 data/audio/{sha1}.mp3，返回 /api/v1/audio/{sha1}.mp3（惰性过期见 routes）。"""
    import os

    settings = get_settings()
    os.makedirs(settings.audio_dir, exist_ok=True)
    name = hashlib.sha1(data).hexdigest()[:32] + ".mp3"
    path = os.path.join(settings.audio_dir, name)
    if not os.path.exists(path):
        with open(path, "wb") as f:
            f.write(data)
    return f"/api/v1/audio/{name}"


# ---------------------------------------------------------------------------
# 会话回合
# ---------------------------------------------------------------------------
async def run_turn(
    session_id: int,
    user_id: int,
    audio: bytes | None,
    action: str,
    expected_turn: int | None,
    audio_url: str | None,
    asr: ASRClient,
    scorer: ScorerClient,
    llm: LLMClient,
    tts: TTSClient,
):
    """对话/辩护回合主入口（async 生成器，产 SSE 事件流）。"""
    store = get_state_store()
    state = await store.get(session_id)
    if state is None:
        raise OrchestratorError(status_code=404, detail="session not found or expired")
    if state.state not in ("awaiting_user", "listening", "opening"):
        raise OrchestratorError(status_code=409, detail=f"session state={state.state}")
    if expected_turn is not None and expected_turn != state.current_turn:
        raise OrchestratorError(status_code=409, detail="stale turn (expected_turn mismatch)")

    nonce = await store.acquire_lock(session_id)
    if nonce is None:
        raise OrchestratorError(status_code=409, detail="session busy (lock held)")

    try:
        if state.kind == SessionKinds.DEFENSE:
            async for event in _defense_turn(
                state, action, audio, audio_url, asr, scorer, llm, tts
            ):
                yield event
        elif state.kind == SessionKinds.SHADOW:
            async for event in _shadow_turn(state, action, audio, audio_url, asr, scorer, llm, tts):
                yield event
        else:
            async for event in _dialog_turn(state, action, audio, audio_url, asr, scorer, llm, tts):
                yield event
    finally:
        await store.release_lock(session_id, nonce)


# ---------------------------------------------------------------------------
# 预置场景对话
# ---------------------------------------------------------------------------
async def _dialog_turn(state, action, audio, audio_url, asr, scorer, llm, tts):
    settings = get_settings()
    db = _db()
    try:
        session = db.get(DbSession, state.session_id)
        scenario = db.execute(
            select(Scenario).where(Scenario.id == (session.scenario_id or 0))
        ).scalar_one_or_none()
        if scenario is None:
            raise OrchestratorError(status_code=404, detail="scenario not found")

        corpus = parse_corpus(scenario.target_corpus)
        turn_index = state.current_turn + 1

        # 1) ASR（rescue 轮跳过）
        transcript = ""
        asr_meta: dict = {}
        fluency: dict = {}
        if action in ("normal", "retry") and audio:
            try:
                res = await asr.transcribe(audio)
                transcript = res.text.strip()
                # 流利度时间戳特征（docs/06 §9.3 辅助口径：wpm/停顿；数据源 = 词级时间戳）
                fluency = compute_fluency_features(res.words or [], float(res.duration or 0.0))
                asr_meta = {
                    "asr_seconds": round(len(audio) / 16000, 1),
                    "wpm": fluency["wpm"],
                    "pause_count": fluency["pause_count"],
                }
            except Exception as exc:
                logger.warning("asr failed: %s", exc)
                yield ev.StreamError(code="asr_failed", recoverable=True)
                transcript = ""
        if not transcript:
            action = "retry" if transcript == "" and action == "normal" else action

        # 1.5) 用户转写回显（2026-09-08：前端聊天化，用户语音→文字气泡，先于 AI 提问发出）
        if transcript:
            yield ev.UserTranscript(turn_index=turn_index, text=transcript)

        # 2) rescue 参考句（提示/代说用）
        reference = None
        if not transcript and action in ("retry", "hint"):
            reference = corpus[0].phrase if corpus else None

        yield ev.TurnStart(turn_index=turn_index, reference_text=reference)

        # 3) 评分并行 + LLM 流式
        score_task = None
        if transcript and action in ("normal", "retry"):
            score_task = asyncio.ensure_future(_safe_score(scorer, audio or b"", transcript))
        last_errors: list = []
        if action == "abandon":
            # 用户结束：跳过本轮管线，直接收尾 → 报告（docs/14 §3.2 concluding）
            db.commit()  # 释放本 turn 事务，再进入 complete_session（嵌套 Session 共享连接安全）
            summary = await _conclude_summary(llm, state.digest)
            report_id = complete_session(state.session_id, llm, summary)
            state.state = "completed"
            await get_state_store().put(state)
            yield ev.SessionEnd(
                summary=summary,
                report_id=report_id,
                metrics={
                    "turn_count": state.current_turn,
                    "duration_s": None,
                    "coverage": {"count": len(state.corpus_done)},
                },
            )
            return
        if action in ("demo", "hint") and not audio:
            # 用户主动点示范/提示：无音频轻回合——落库 + 推进轮次（否则前端 turn_end+1 与服务端
            # current_turn 不同步 → 下轮 stale_turn 409，2026-09-01 实机修复）；不发覆盖度/评分
            seq_user = state.next_seq
            state.next_seq += 1
            db.add(
                ScenarioMessage(
                    session_id=state.session_id,
                    seq=seq_user,
                    role="user",
                    origin="respond",
                    action=action,
                    content=f"[{action}]",
                    meta={"action": action, "trigger_by": "user"},
                )
            )
            state.current_turn = turn_index
            state.last_action = action
            db.commit()
            await get_state_store().put(state)
            yield ev.TurnEnd(turn_index=turn_index, score_status="unavailable")
            return

        messages = build_llm_context(
            state,
            scenario.system_prompt,
            scenario.target_corpus or "",
            state.assembled.get("difficulty") or scenario.difficulty,
            transcript,
            action,
            state.corpus_done,
            concluded_by_turn=(state.current_turn + 1 >= (session.assigned_turns or 8)),
            learner_profile=get_rendered(int(session.user_id)),
            rolling_summary=get_session_summary(state.session_id) or "",
        )
        # LLM 流式：交 TurnRunner（docs/26 runtime/turn-runner：边界拆分 + META 泄漏门）；
        # 失败降级不重试（流式不可回放；POC-2 判定 <90% 成功率时切换「两调用」方案，docs/18 §6）
        runner = TurnRunner(llm)
        caught = False
        try:
            async for delta in runner.run(messages):
                yield ev.TextDelta(text=delta)
        except Exception as exc:
            caught = True
            logger.warning("llm failed: %s", exc)
            yield ev.StreamError(code="llm_failed", recoverable=True)
        if caught:
            full_text = _fallback_reply(transcript)
            meta = MetaResult(reply=full_text, meta=None, ok=False)
        else:
            res = runner.result
            assert res is not None
            full_text = res.reply_text
            meta = res.meta
            if res.leaked:
                logger.warning("META leak degraded: reply without meta (user=%s)", session.user_id)
            if res.usage:
                log_usage(
                    "turn",
                    res.usage,
                    meta={"session_id": int(state.session_id), "turn": turn_index},
                )
        if meta is None:
            meta = MetaResult(reply=full_text, meta=None, ok=False)
        if not meta.ok:
            # META 缺失补偿（docs/26 §9.4）：流式未守契约 → 后置一次低温度提取调用；
            # 仍失败 → 既有降级（rule conclude 兜底，不伪造元数据）
            meta = await compensate_meta(
                llm,
                reply_text=full_text,
                transcript=transcript,
                action=action,
                concluded_by_turn=(state.current_turn + 1 >= (session.assigned_turns or 8)),
            )
        reply = meta.reply or full_text
        if not reply:
            reply = _fallback_reply(transcript)

        # 4) 命中（MetaExecutor：规则权威 + LLM 兜底；retry/hint/demo 作废——docs/26 §⑤）
        hits = _meta_executor.apply_hits(transcript, corpus, meta, action, last_errors)

        # 5) 逐句 TTS（并发；失败静默降级字幕）
        audio_urls: list[str] = []
        for line in tts_sentences(reply):
            url = await _tts_url_from_bytes(tts, line, settings.tts_voice, settings.tts_rate)
            if url:
                audio_urls.append(url)
                yield ev.AudioChunk(url=url)

        # 6) 后置元数据 + 迟到的评分徽章
        grammar = _meta_executor.effective_grammar(meta, last_errors)
        yield ev.MetaBlock(
            grammar=grammar,
            coach_note=(meta.coach_note or None),
            corpus_hits=hits,
            difficulty_delta=meta.difficulty_delta,
            conclude=meta.conclude,
            content=meta.content,  # ③ 语义子分（LLM 判定；防御见 meta.py properties）
            vocab=meta.vocab,
        )
        score_status = "unavailable"
        if score_task is not None:
            try:
                score = await score_task
                if score is not None and score.overall is not None:
                    yield ev.ScoreDelta(
                        turn_index=turn_index,
                        pronunciation=float(score.pronunciation),
                        fluency=float(score.fluency),
                        grammar=float(score.grammar) if score.grammar is not None else None,
                    )
                    score_status = "ok"
            except Exception:
                score_status = "unavailable"
        else:
            score_status = "unavailable"

        # 7) 落库（user 消息 + attempt + assistant 消息）
        seq_user = state.next_seq
        state.next_seq += 1
        db.add(
            ScenarioMessage(
                session_id=state.session_id,
                seq=seq_user,
                role="user",
                origin="proactive" if action == "normal" else "respond",
                action=action if action in ("demo", "correction", "retry", "hint") else None,
                content=transcript or f"[{action}]",
                audio_url=audio_url,
                meta={"corpus_hits": hits, **asr_meta, "action": action},
            )
        )
        if transcript and action in ("normal", "retry") and score_task is not None:
            try:
                score = score_task.result()
            except Exception:
                score = None
            db.add(
                Attempt(
                    user_id=session.user_id,
                    session_id=state.session_id,
                    scenario_message_id=seq_user and _find_msg_id(db, state.session_id, seq_user),
                    kind=AttemptKinds.DIALOG_SPEECH,
                    audio_url=audio_url,
                    transcript=transcript,
                    pron_score=_dec(score.pronunciation if score else None),
                    flu_score=_dec(score.fluency if score else None),
                    gram_score=_dec(grammar and grammar.get("score")),
                    overall_score=_dec(score.overall if score else None),
                    # 语速辅助指标（docs/07 Q30）+ 流利度时间戳特征（docs/06 §9.3）
                    wpm=_dec(fluency["wpm"]) if fluency else None,
                    details={
                        "word_level": (score.word_level if score else []),
                        "fluency": fluency,
                    },
                    error={} if score is not None else {"reason": "score_unavailable"},
                )
            )
        seq_assistant = state.next_seq
        state.next_seq += 1
        db.add(
            ScenarioMessage(
                session_id=state.session_id,
                seq=seq_assistant,
                role="assistant",
                content=reply,
                audio_url=(audio_urls[0] if audio_urls else None),
                meta={
                    "grammar": grammar,
                    "coach_note": meta.coach_note,
                    "corpus_hits": hits,
                    "difficulty_delta": meta.difficulty_delta,
                    "content": meta.content,  # ③ 语义子分（报告聚合源，见 service）
                    "vocab": meta.vocab,
                    "prompt_version": 2,  # v2=稳定前缀+学习者画像注入（docs/26）
                },
            )
        )

        # 8) 状态推进
        state.current_turn = turn_index
        state.last_action = action
        state.digest = (state.digest + [f"U: {transcript[:80]} | A: {reply[:60]}"] + [])[-3:]
        for h in hits:
            if h["phrase"] not in state.corpus_done:
                state.corpus_done.append(h["phrase"])
        low_quality = not transcript or not _meta_executor.grammar_ok(meta, last_errors)
        state.failed_streak = state.failed_streak + 1 if low_quality else 0
        if state.failed_streak >= 2 and action != "retry":
            state.failed_streak = 0  # L2 AI 代说由 LLM 侧换角度完成；此处记账
        db.commit()

        # 摘要双轨（docs/26 §10.3①）：回合落库后异步增量压缩（失败标记 → 下次自动重试）
        asyncio.create_task(SummarizerService(llm).maybe_summarize(state.session_id))

        yield ev.TurnEnd(turn_index=turn_index, score_status=score_status)

        # 9) 收尾判定（MetaExecutor：meta.conclude 或轮次上限或用户放弃）
        limit = session.assigned_turns or 8
        if _meta_executor.should_conclude(meta, turn_index, limit, action):
            summary = await _conclude_summary(llm, state.digest, session_id=int(state.session_id))
            report_id = complete_session(state.session_id, llm, summary)
            state.state = "completed"
            await get_state_store().put(state)
            yield ev.SessionEnd(
                summary=summary,
                report_id=report_id,
                metrics={
                    "turn_count": state.current_turn,
                    "duration_s": None,
                    "coverage": {"count": len(state.corpus_done)},
                },
            )
            return
        state.state = "awaiting_user"
        await get_state_store().put(state)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 答辩会话（极简版：题库顺序 + 等级阶梯）
# ---------------------------------------------------------------------------
async def _defense_turn(state, action, audio, audio_url, asr, scorer, llm, tts):
    db = _db()
    try:
        session = db.get(DbSession, state.session_id)
        from app.models import DefenseProfile

        profile = db.get(DefenseProfile, session.profile_id or 0)
        bank = (profile.knowledge_bank or {}) if profile else {}
        questions = bank.get("questions") or []
        order = bank.get("suggested_order") or [q["id"] for q in questions]

        # ---- 服务题目（start=第一题；next=作答后由等级阶梯选出的 pending 题） ----
        if action in ("start", "next"):
            q = None
            if state.pending is not None:
                q = state.pending
            elif action == "start" and questions:
                qid = order[0] if order else questions[0].get("id")
                q = next((x for x in questions if x.get("id") == qid), questions[0])
            if q is None:
                raise OrchestratorError(status_code=404, detail="no questions in bank")
            state.pending = None
            state.question_id = q.get("id")
            if state.tier_index == 0:
                state.tier_index = int(q.get("tier") or 1)
            _push_question(state, q, db)
            db.commit()
            await get_state_store().put(state)
            yield ev.TurnStart(turn_index=state.current_turn + 1, question=q.get("question"))
            yield ev.TurnEnd(turn_index=state.current_turn + 1, score_status="ok")
            return

        # ---- 作答回合 ----
        turn_index = state.current_turn + 1
        yield ev.TurnStart(turn_index=turn_index)
        transcript = ""
        if audio:
            try:
                transcript = (await asr.transcribe(audio)).text.strip()
            except Exception:
                transcript = ""
        current_q = next((x for x in questions if x.get("id") == state.question_id), None)
        key_points = (current_q or {}).get("key_points") or []
        hits = _keypoint_hits(transcript, key_points)
        level = _answer_level(hits, key_points, transcript)
        lang = None
        if transcript:
            try:
                lang = await scorer.score(audio or b"", transcript)
            except Exception:
                lang = None

        seq_user = state.next_seq
        state.next_seq += 1
        db.add(
            ScenarioMessage(
                session_id=state.session_id,
                seq=seq_user,
                role="user",
                origin="respond",
                content=transcript,
                audio_url=audio_url,
                meta={"level": level, "hits": hits, "question_id": state.question_id},
            )
        )
        state.current_turn = turn_index
        if state.question_id is not None:
            state.answered.append(state.question_id)

        done = (
            len(state.answered) >= (session.assigned_turns or 6) or turn_index >= 8 or not questions
        )
        next_q, next_tier = _next_question(state, questions, order, level, done)
        state.pending = next_q
        if next_q is not None:
            state.tier_index = next_tier
        db.commit()

        yield ev.MetaBlock(
            grammar={"score": round((lang.grammar or 0), 0)} if lang and lang.grammar else None,
            coach_note=_coach_for_level(level, hits, key_points),
            corpus_hits=[],
            difficulty_delta=0,
            conclude=done,
            level=level,
            hits={"hits": hits, "total": len(key_points)},
        )
        yield ev.TurnEnd(turn_index=turn_index, score_status="ok" if lang else "unavailable")
        if done:
            summary = f"答辩练习完成，共 {len(state.answered)} 题。"
            report_id = complete_session(state.session_id, llm, summary)
            state.state = "completed"
            await get_state_store().put(state)
            yield ev.SessionEnd(
                summary=summary,
                report_id=report_id,
                metrics={"answered": len(state.answered), "duration_s": None},
            )
            return
        state.state = "awaiting_user"
        await get_state_store().put(state)
    finally:
        db.close()


def _push_question(state, q, db) -> None:
    """题目落库（is_question + basis 提问依据快照；音频由前端 TTS 播题）。"""
    text = q.get("question")
    assert text
    seq = state.next_seq
    state.next_seq += 1
    db.add(
        ScenarioMessage(
            session_id=state.session_id,
            seq=seq,
            role="assistant",
            content=text,
            meta={"is_question": True, "basis": q.get("basis"), "tier": q.get("tier")},
        )
    )


def _keypoint_hits(transcript: str, key_points: list[str]) -> list[str]:
    if not transcript:
        return []
    norm = " ".join(transcript.lower().split())
    hits = [kp for kp in key_points if kp.lower() in norm]
    return hits


def _answer_level(hits: list[str], key_points: list[str], transcript: str) -> str:
    if not transcript:
        return "red"
    if len(hits) >= 2 and len(key_points) >= 2:
        return "green"
    if len(hits) >= 1:
        return "yellow"
    return "red"


def _next_question(
    state: SessionState, questions: list[dict], order: list[str], level: str, done: bool
) -> tuple[dict | None, int]:
    """规则阶梯（docs/14 §4.3 简版）：绿→升层/同层追问；黄→同层换题；红→降层/换角度。"""
    if done:
        return None, state.tier_index
    by_id = {q.get("id"): q for q in questions}
    # 按层过滤未答题目
    remaining = [qid for qid in order if qid not in (state.answered or []) and qid in by_id]
    if not remaining:
        return None, state.tier_index
    # 分层池
    tier_pool = {
        1: [qid for qid in remaining if by_id[qid].get("tier") == 1],
        2: [qid for qid in remaining if by_id[qid].get("tier") == 2],
        3: [qid for qid in remaining if by_id[qid].get("tier") == 3],
    }
    cur = state.tier_index
    if level == "green":
        target = cur + 1 if tier_pool.get(cur + 1) else cur
    elif level == "yellow":
        target = cur
    else:
        target = cur - 1 if cur - 1 >= 1 and tier_pool.get(cur - 1) else cur
    pool = tier_pool.get(target) or [qid for qid in remaining]
    qid = pool.pop(0) if pool else remaining[0]
    return by_id[qid], target


def _coach_for_level(level: str, hits: list[str], key_points: list[str]) -> str:
    if level == "green":
        return "Great answer! Strong points." if len(hits) >= 1 else "Good. Try adding more detail."
    if level == "yellow":
        return "Good direction. Try to include one more key point first."
    return "Tip: lead with your conclusion, then support it."


# ---------------------------------------------------------------------------
# 影子跟读（DoD ④：ISE 主场；start=出句+示范 → normal=跟读评分，逐句推进）
# ---------------------------------------------------------------------------
async def _shadow_turn(state, action, audio, audio_url, asr, scorer, llm, tts):
    """影子跟读回合。score 三维（发音/语速匹配/停顿密度）见 app/practice/shadow.py。

    - start（无音频）：出句 + 示范 TTS（AudioChunk），不推进轮次；
    - normal（带音频）：ASR + ISE(题卡原文) + 流利度特征 → 三维分 → 落库 → 推进；
      最后一句系结 → complete_session（报告）。LLM 不参与（规则教练笔记，无 META）。
    """
    settings = get_settings()
    db = _db()
    try:
        session = db.get(DbSession, state.session_id)
        material = db.get(ShadowMaterial, session.shadow_material_id or 0)
        sentences = split_sentences(material.text_content) if material else []
        if material is None or material.status != "published" or not sentences:
            yield ev.StreamError(code="shadow_material_unavailable", recoverable=False)
            return
        idx = min(state.current_turn, len(sentences) - 1)
        sentence = sentences[idx]
        turn_index = state.current_turn + 1

        if action == "start":
            yield ev.TurnStart(turn_index=turn_index, reference_text=sentence)
            demo_url = await _tts_url_from_bytes(
                tts, sentence, settings.tts_voice, settings.tts_rate
            )
            if demo_url:
                yield ev.AudioChunk(url=demo_url)
            yield ev.TurnEnd(turn_index=turn_index, score_status="pending")
            await get_state_store().put(state)
            return

        if not audio:
            raise OrchestratorError(status_code=422, detail="audio required for shadow record")

        yield ev.TurnStart(turn_index=turn_index, reference_text=sentence)

        # ASR + 流利度特征（② reuse；失败降级——分数不伪造，落 error 快照）
        transcript = ""
        fluency: dict = {}
        try:
            res = await asr.transcribe(audio)
            transcript = res.text.strip()
            fluency = compute_fluency_features(res.words or [], float(res.duration or 0.0))
        except Exception as exc:
            logger.warning("shadow asr failed: %s", exc)
        score = None
        if transcript:
            score = await _safe_score(scorer, audio, sentence)  # ISE（reference=题卡原文）

        sc = shadow_scores(
            float(score.pronunciation) if score else None,
            fluency.get("wpm") or None,
            material.wpm,
            fluency.get("pause_ratio") or None,
        )
        coach = coach_note(sc) or (
            None if transcript else "Couldn't catch that — try again a bit louder, please."
        )
        rhythm = None
        rhythm_vals = [v for v in (sc.speed_match, sc.pause_score) if v is not None]
        if rhythm_vals:
            rhythm = round(sum(rhythm_vals) / len(rhythm_vals), 1)

        conclude = idx + 1 >= len(sentences)
        yield ev.MetaBlock(
            grammar=None,
            coach_note=coach,
            corpus_hits=[],
            difficulty_delta=0,
            conclude=conclude,
        )
        score_status = "ok" if sc.overall is not None else "unavailable"
        if sc.pron is not None:
            yield ev.ScoreDelta(
                turn_index=turn_index, pronunciation=round(float(sc.pron), 1), fluency=rhythm
            )

        # 落库（user 消息 + attempt + coach 消息）
        seq_user = state.next_seq
        state.next_seq += 1
        db.add(
            ScenarioMessage(
                session_id=state.session_id,
                seq=seq_user,
                role="user",
                origin="respond",
                content=transcript or "[shadow]",
                audio_url=audio_url,
                meta={
                    "kind": "shadow",
                    "sentence_index": idx,
                    "sentence": sentence,
                    "wpm": fluency.get("wpm"),
                    "pause_count": fluency.get("pause_count"),
                },
            )
        )
        db.add(
            Attempt(
                user_id=session.user_id,
                session_id=state.session_id,
                scenario_message_id=_find_msg_id(db, state.session_id, seq_user),
                kind=AttemptKinds.SHADOW_SPEECH,
                audio_url=audio_url,
                transcript=transcript or None,
                pron_score=_dec(sc.pron) if sc.pron is not None else None,
                flu_score=_dec(rhythm),
                overall_score=_dec(sc.overall) if sc.overall is not None else None,
                wpm=_dec(fluency["wpm"]) if fluency else None,
                details={
                    "fluency": fluency,
                    "shadow": sc.as_dict(),
                    "sentence": sentence,
                    "word_level": (score.word_level if score else []),
                },
                error={}
                if sc.overall is not None
                else {"reason": "asr_failed" if not transcript else "score_unavailable"},
            )
        )
        seq_assistant = state.next_seq
        state.next_seq += 1
        db.add(
            ScenarioMessage(
                session_id=state.session_id,
                seq=seq_assistant,
                role="assistant",
                content=coach or sentence,
                meta={"kind": "shadow", "coach_note": coach, "prompt_version": 2},
            )
        )
        state.current_turn += 1
        state.last_action = action
        db.commit()
        yield ev.TurnEnd(turn_index=turn_index, score_status=score_status)

        if conclude:
            summary = f"影子跟读完成，共 {len(sentences)} 句。"
            report_id = complete_session(state.session_id, llm, summary)
            state.state = "completed"
            await get_state_store().put(state)
            yield ev.SessionEnd(
                summary=summary,
                report_id=report_id,
                metrics={"sentences": len(sentences), "duration_s": None},
            )
            return
        state.state = "awaiting_user"
        await get_state_store().put(state)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------
async def _safe_score(scorer, audio, reference):
    try:
        return await scorer.score(audio, reference)
    except Exception:
        return None


def _fallback_reply(transcript: str) -> str:
    return (
        "I see! Could you tell me more?"
        if transcript
        else "No worries, take your time. Why don't you try my example?"
    )


async def _conclude_summary(
    llm: LLMClient, digest: list[str], session_id: int | None = None
) -> str:
    try:
        content = (
            "Summarize this short speaking practice in one friendly English sentence: "
            f"{' | '.join(digest[-4:])}"
        )
        fn = getattr(llm, "chat_with_usage", None)
        if fn is not None:
            raw, usage = await fn(
                [{"role": "user", "content": content}],
                temperature=0.4,
                max_tokens=80,
            )
            if usage:
                log_usage("conclude", usage, meta={"session_id": session_id})
        else:
            raw = await llm.chat(
                [{"role": "user", "content": content}],
                temperature=0.4,
                max_tokens=80,
            )
        return (raw or "")[:200]
    except Exception:
        return "Well done! Keep practicing."


def _dec(v) -> object:
    from decimal import Decimal

    if v is None:
        return None
    return Decimal(str(round(float(v), 2)))


def _find_msg_id(db, session_id: int, seq: int) -> int | None:
    row = db.execute(
        select(ScenarioMessage.id).where(
            ScenarioMessage.session_id == session_id, ScenarioMessage.seq == seq
        )
    ).first()
    return row[0] if row else None


# ---------------------------------------------------------------------------
# 编排器接口（保持 base.py 依赖注入风格；供路由直接调用）
# ---------------------------------------------------------------------------
class PracticeOrchestrator:
    """编排器门面：组装 clients、暴露 run_turn（路由层唯一入口）。"""

    def __init__(self, asr: ASRClient, scorer: ScorerClient, llm: LLMClient, tts: TTSClient):
        self._asr = asr
        self._scorer = scorer
        self._llm = llm
        self._tts = tts

    async def run(
        self,
        session_id: int,
        user_id: int,
        audio: bytes | None,
        action: str,
        expected_turn: int | None,
        audio_url: str | None = None,
    ):
        async for event in run_turn(
            session_id,
            user_id,
            audio,
            action,
            expected_turn,
            audio_url,
            self._asr,
            self._scorer,
            self._llm,
            self._tts,
        ):
            yield event


def get_orchestrator() -> PracticeOrchestrator:
    from app.audio.base import (
        get_asr_client,
        get_llm_client,
        get_scorer_client,
        get_tts_client,
    )

    return PracticeOrchestrator(
        asr=get_asr_client(),
        scorer=get_scorer_client(),
        llm=get_llm_client(),
        tts=get_tts_client(),
    )


__all__ = [
    "PracticeOrchestrator",
    "get_orchestrator",
    "run_turn",
    "save_audio_bytes",
    "OrchestratorError",
]
