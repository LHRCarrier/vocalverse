"""Agent Lab —— LLM 框架测试台（test-only，团队测试用，可整体删除）。

设计约束（组长要求 2026-09-03）：
- **不影响其它代码**：`include_in_schema=False`（不进 OpenAPI 契约快照 → CI 对账零影响）、
  无表/无迁移、不碰 practice/audio 既有路由；默认关闭（`agent_lab_enabled=False`，
  未开启时路由不注册 → 404）；
- **删除无影响**（删除清单见本文件末尾注释）；有真实 LLM 调用（DeepSeek），
  仅在本地/团队环境开启（APP_AGENT_LAB_ENABLED=true），**生产必须保持关闭**。

能力：
- POST /api/v1/agent-lab/turn    单轮实验：ContextBuilder → 真流式 → META 补偿 → MetaExecutor
- POST /api/v1/agent-lab/turns   连跑 N 轮（滚动 digest/hits，复现 llm_framework_smoke）
- GET  /api/v1/agent-lab/learner 学习者画像查看（只读）
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.response import Envelope, ok
from app.practice.corpus import parse_corpus
from app.practice.state import SessionState

router = APIRouter(
    prefix="/api/v1/agent-lab", tags=["agent-lab"], include_in_schema=False
)  # include_in_schema=False：不进 OpenAPI 契约快照（docs/26 §8 测试台约束）


class AgentTurnRequest(BaseModel):
    scenario_prompt: str = "You are Maya, a friendly and patient barista at a cozy small cafe."
    corpus_text: str = (
        "I'd like a coffee, please.|请给我来杯咖啡\n"
        "Could I have a cappuccino?|来杯卡布奇诺\n"
        "How much is it?|多少钱\n"
        "Can I drink it here?|可以在这喝吗\n"
        "Thanks, that's all.|谢谢，就这些"
    )
    difficulty: int = Field(default=2, ge=1, le=4)
    user_text: str = "hi, I would like a coffee please"
    action: str = Field(default="normal", pattern="^(normal|retry|hint|demo)$")
    learner_profile: str = ""
    history: list[str] = Field(default_factory=list)  # 滚动摘要行（可空）
    concluded_by_turn: bool = False


class AgentTurnsRequest(AgentTurnRequest):
    turns: list[str] = Field(default_factory=list)  # 覆盖单轮 user_text；连跑用例


def _make_llm():
    """测试台专用 LLM 客户端（settings 读 Key；测试可 monkeypatch）。"""
    from app.audio.llm import DeepSeekLLMClient

    s = get_settings()
    return DeepSeekLLMClient(
        api_key=s.deepseek_api_key,
        base_url=s.deepseek_base_url,
        model=s.deepseek_model,
    )


@dataclass
class _TurnOutcome:
    turn: int
    user_text: str
    reply: str
    meta_ok: bool
    compensated: bool
    leaked: bool
    coach_note: str | None
    grammar: dict | None
    corpus_hits: list[dict]
    difficulty_delta: int
    conclude: bool
    ms: int


async def _run_turn(
    req: AgentTurnRequest,
    state: SessionState,
    user_text: str,
    turn_index: int,
    llm,
) -> _TurnOutcome:
    """一回合：build_context → TurnRunner →（缺 META 时）补偿 → MetaExecutor 命中。"""
    from app.agent.runtime.context_builder import build_context
    from app.agent.runtime.meta_executor import MetaExecutor, compensate_meta
    from app.agent.runtime.turn_runner import TurnRunner

    messages = build_context(
        state,
        req.scenario_prompt,
        req.corpus_text,
        req.difficulty,
        user_text,
        req.action,
        state.corpus_done,
        req.concluded_by_turn,
        learner_profile=req.learner_profile,
    )
    t0 = time.perf_counter()
    runner = TurnRunner(llm)
    async for _ in runner.run(messages):
        pass
    assert runner.result is not None
    res = runner.result
    meta = res.meta
    compensated = False
    if not meta.ok:
        meta = await compensate_meta(
            llm,
            reply_text=res.reply_text,
            transcript=user_text,
            action=req.action,
            concluded_by_turn=req.concluded_by_turn,
        )
        compensated = True
    hits = MetaExecutor().apply_hits(user_text, parse_corpus(req.corpus_text), meta, req.action, [])
    ms = int((time.perf_counter() - t0) * 1000)
    return _TurnOutcome(
        turn=turn_index,
        user_text=user_text,
        reply=res.reply_text,
        meta_ok=meta.ok,
        compensated=compensated,
        leaked=res.leaked,
        coach_note=meta.coach_note,
        grammar=meta.grammar,
        corpus_hits=hits,
        difficulty_delta=meta.difficulty_delta,
        conclude=meta.conclude,
        ms=ms,
    )


@router.post("/turn")
async def turn(req: AgentTurnRequest) -> Envelope[dict]:
    """单轮实验（真 LLM；Key 缺失时 DeepSeek 客户端照常抛错→由前端显示）。"""
    state = SessionState(session_id=0, kind="dialog")
    state.digest = list(req.history)
    out = await _run_turn(req, state, req.user_text, 1, _make_llm())
    return ok(
        {
            "system": build_context_for_display(req, state),
            "result": out.__dict__,
        }
    )


@router.post("/turns")
async def turns(req: AgentTurnsRequest) -> Envelope[dict]:
    """连跑：按 turns 列表滚动（每轮更新 digest/corpus_done，复现框架冒烟）。"""
    state = SessionState(session_id=0, kind="dialog")
    state.digest = list(req.history)
    llm = _make_llm()
    results: list[dict] = []
    for i, user_text in enumerate(req.turns or [req.user_text], start=1):
        out = await _run_turn(req, state, user_text, i, llm)
        results.append(out.__dict__)
        state.digest.append(f"U: {user_text[:60]} | A: {out.reply[:60]}")
        for h in out.corpus_hits:
            phrase = h.get("phrase") if isinstance(h, dict) else None
            if phrase and phrase not in state.corpus_done:
                state.corpus_done.append(str(phrase))
        if out.conclude:
            break
    meta_ok = sum(1 for r in results if r["meta_ok"])
    return ok(
        {
            "results": results,
            "stats": {
                "turns": len(results),
                "meta_ok": meta_ok,
                "meta_rate": round(meta_ok / len(results) * 100, 1) if results else 0,
                "compensated": sum(1 for r in results if r["compensated"]),
                "concluded": bool(results and results[-1]["conclude"]),
            },
        }
    )


def build_context_for_display(req: AgentTurnRequest, state: SessionState) -> dict:
    """把组装结果原样返回（前端查看 system/user 原文，验证「system 全静态」）。"""
    from app.agent.runtime.context_builder import build_context

    msgs = build_context(
        state,
        req.scenario_prompt,
        req.corpus_text,
        req.difficulty,
        req.user_text,
        req.action,
        state.corpus_done,
        req.concluded_by_turn,
        learner_profile=req.learner_profile,
    )
    return {"system": msgs[0]["content"], "user": msgs[1]["content"]}


@router.get("/learner")
async def learner(user_id: int = Query(default=1)) -> Envelope[dict]:
    """学习者画像只读查看（build_profile + render；开关状态一并返回）。"""
    from app.agent.domains.learner import build_profile, render
    from app.db import get_session_factory

    s = get_settings()
    db = get_session_factory()()
    try:
        profile = build_profile(db, int(user_id))
        data = {
            "user_id": int(user_id),
            "enabled": s.learner_injection_enabled,
            "rendered": render(profile),
            "weak_phrases": profile.weak_phrases,
            "weak_words": profile.weak_words,
            "est_level": profile.est_level,
        }
    finally:
        db.close()
    return ok(data)


"""
删除清单（Agent Lab 整删无影响）：
1. 删 `apps/web/src/views/preview/AgentLabPreview.vue` + `views/preview/registry.ts` 该行
   + `router/preview.ts` 该路由（dev-only 子树，生产构建零体积）；
2. 删本文件 + `main.py` 的 `agent_lab` import 与 `include_router` 两行（约 3 行）；
3. 删 `app/core/config.py` 的 `agent_lab_enabled` 一行；
4. 收尾：全量 pytest / pnpm typecheck / lint；契约快照零 diff（include_in_schema=False）。
"""
