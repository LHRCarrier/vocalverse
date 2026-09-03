"""Placement Lab —— 入学测试联调测试台（test-only，团队测试用，可整体删除）。

设计约束（同 agent_lab.py，组长 2026-09-03 要求）：
- **不影响其它代码**：``include_in_schema=False``（不进 OpenAPI 契约快照 → CI 对账零影响）、
  无表/无迁移、不碰 placement 既有路由/既有逻辑；默认关闭（``placement_lab_enabled=False``，
  未开启时路由不注册 → 404）；
- **删除无影响**（删除清单见本文件末尾注释）；有真实 ASR/ISE/LLM 调用（APP_TESTING 下走 Fake），
  仅在本地/团队环境开启（``APP_PLACEMENT_LAB_ENABLED=true``），**生产必须保持关闭**。

能力：
- POST /api/v1/placement-lab/run  用 Fake 客户端跑完整入学测试：
  questions→逐题评分→两维综合分→档位，并落一条 completed placement（复现真实 finalize）。
- GET  /api/v1/placement-lab/status 查看指定用户当前档位（读 placements，复测资格据此）。
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.audio.base import get_asr_client, get_scorer_client
from app.core.config import get_settings
from app.core.response import Envelope, ok
from app.db import get_session_factory
from app.models import Placement, PlacementQuestion, User
from app.models.base import PlacementQuestionKind, Roles
from app.placement.grammar import judge_grammar, judge_qa_answer
from app.placement.scoring import compute_accuracy, compute_fluency, compute_s, level_for

router = APIRouter(
    prefix="/api/v1/placement-lab", tags=["placement-lab"], include_in_schema=False
)  # include_in_schema=False：不进 OpenAPI 契约快照（docs/13 §8 测试台约束）


def _dec(v):
    from decimal import Decimal

    if v is None:
        return None
    return Decimal(str(round(float(v), 2)))


@router.post("/run")
async def run(user_id: int = Query(default=1)) -> Envelope[dict]:
    """用 Fake 客户端（APP_TESTING）跑完整入学测试，复现真实 finalize 的两维公式与落库。

    返回 {user_id, level, total_score, pron, flu, gram, exam_revision, items[]}；
    并在库中落一条 completed placement（供 /status 复测资格查看）。
    """
    cfg = get_settings()
    asr = get_asr_client()
    scorer = get_scorer_client()
    db = get_session_factory()()
    try:
        # 确保测试用户存在（测试台专用：最小账户）
        user = db.get(User, user_id)
        if user is None:
            user = User(
                username=f"placement_lab_{user_id}",
                password_hash="x",
                nickname="PlacementLab",
                role=Roles.USER,
            )
            db.add(user)
            db.flush()

        qs = (
            db.execute(
                select(PlacementQuestion)
                .where(PlacementQuestion.status == "published")
                .order_by(PlacementQuestion.exam_revision, PlacementQuestion.item_index)
            )
            .scalars()
            .all()
        )

        pron_vals, flu_vals, comp_vals, gram_vals, items = [], [], [], [], []
        revision = qs[0].exam_revision if qs else 1
        for q in qs:
            text = (await asr.transcribe(b"synthetic-audio")).text
            pron = flu = comp = None
            score = None
            if q.kind == PlacementQuestionKind.READ:
                try:
                    score = await scorer.score(b"synthetic-audio", q.prompt)
                    pron, flu, comp = (
                        score.pronunciation,
                        score.fluency,
                        score.completeness,
                    )
                    pron_vals.append(float(pron) if pron is not None else None)
                    flu_vals.append(float(flu) if flu is not None else None)
                    comp_vals.append(float(comp) if comp is not None else None)
                except Exception:  # noqa: BLE001 - 测试台展示用，不中断
                    score = None
            grammar = (
                await judge_qa_answer(text, q.prompt)
                if q.kind == PlacementQuestionKind.QA
                else await judge_grammar(text, q.prompt)
            )
            gram = grammar.get("score") if grammar else None
            gram_vals.append(float(gram) if gram is not None else None)
            items.append(
                {
                    "item_index": q.item_index,
                    "kind": q.kind,
                    "prompt": q.prompt,
                    "transcript": text,
                    "pron": pron,
                    "flu": flu,
                    "completeness": comp,
                    "gram": gram,
                }
            )

        # 语法仅诊断（C1，不进 S）：过滤 None 后取均值，无则 None
        gram_non = [g for g in gram_vals if g is not None]
        gram_mean = sum(gram_non) / len(gram_non) if gram_non else None

        a = compute_accuracy(pron_vals) if pron_vals else None
        f = compute_fluency(flu_vals, comp_vals, cfg) if flu_vals else None
        s = compute_s(a, f, cfg) if (a is not None and f is not None) else 0.0
        level = level_for(s, cfg)

        # 落一条 completed placement（复现真实回写口径；placements 为校对源）
        completed = datetime.now(UTC)
        placement = Placement(
            user_id=user_id,
            exam_revision=revision,
            status="completed",
            completed_at=completed,
            level=level,
            overall_score=_dec(s),
            pron_score=_dec(a) if a is not None else None,
            flu_score=_dec(f) if f is not None else None,
            gram_score=_dec(gram_mean) if gram_mean is not None else None,
            details={"schema_version": "2d", "source": "placement-lab", "items": items},
        )
        db.add(placement)
        db.commit()

        return ok(
            {
                "user_id": user_id,
                "level": level,
                "total_score": round(s, 2),
                "pron": round(a, 2) if a is not None else None,
                "flu": round(f, 2) if f is not None else None,
                "gram": round(gram_mean, 2) if gram_mean is not None else None,
                "exam_revision": revision,
                "items": items,
            }
        )
    finally:
        db.close()


@router.get("/status")
async def status(user_id: int = Query(default=1)) -> Envelope[dict]:
    """查看指定用户当前档位（读 placements 最新 completed；复测/冷却资格据此）。"""
    from app.api.routes.placement import _cooldown_remaining_days, _latest_completed

    cfg = get_settings()
    db = get_session_factory()()
    try:
        latest = _latest_completed(db, user_id)
        return ok(
            {
                "user_id": user_id,
                "current_level": latest.level if latest else None,
                "has_completed": latest is not None,
                "cooldown_remaining_days": _cooldown_remaining_days(latest, cfg),
            }
        )
    finally:
        db.close()


"""
删除清单（Placement Lab 整删无影响）：
1. 删 `apps/web/src/views/preview/PlacementPreview.vue` + `views/preview/registry.ts` 该行
   + `router/preview.ts` 该路由（dev-only 子树，生产构建零体积）；
2. 删本文件 + `main.py` 的 `placement_lab` import 与 `include_router` 两行；
3. 删 `app/core/config.py` 的 `placement_lab_enabled` 一行；
4. 收尾：全量 pytest / pnpm typecheck / lint；契约快照零 diff（include_in_schema=False）。
"""
