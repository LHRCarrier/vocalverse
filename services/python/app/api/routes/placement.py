"""入学测试路由（docs/06 §9.2；C1：考试域两维对齐统一尺度；
阶段 B：run 状态机 + QA 标签 + 幂等 finalize；阶段 C：复测=重考（eligible/冷却）。

- 评分口径（C1 / local/26 §2 / local/24 v4 §2.1）：
  ``S = 0.6·A + 0.4·F``；``A = mean(read 题 pron_score)``；
  ``F = 0.7·mean(flu) + 0.3·mean(completeness)`` —— 语法（LLM）**不进 S**，仅作诊断。
- ``kind='qa'`` 题**只 ASR 不 ISE**（不耗 ISE 桶；A2）；read/qa 均补调 LLM 语法（A1）；
  QA 另给相关度标签（B2），一次 LLM 调用同时出手法 + relevance（控次数，local/16）。
- **run 状态机（B1）**：``score_item`` 惰性创建/续用该用户的 ``in_progress`` run（placements 行；
  不复用 sessions，docs/10 §6 B-2）；``(user_id) WHERE status='in_progress'``
  部分唯一索引兜底并发 → 40910。
- **finalize 幂等（B3）**：run 已 completed 时直接返回已结算结果；
  attempts 经 ``placement_id`` 作消费标记，不可被其他 placement 复用。
- grammar/LLM 缺失 → ``gram_score=None``（fail-open，禁伪造 0）；completeness 缺失 → F 仅用 flu
  （local/20 「integrity 缺失置 None 跳过，禁止 0.0 混入」）。
- 档位回写 user_profiles 由 Java 负责（Java 唯一写者）；本服务落 placements 事实 +
  内部 REST 委托 Java（字段名/幂等修复见阶段 D / C2）。
"""

from __future__ import annotations

import logging
import math
from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.audio.audio_quality import has_min_words
from app.audio.base import get_asr_client, get_scorer_client
from app.audio.fluency import compute_fluency_features
from app.audio.upload import validate_audio_bytes
from app.core.auth import get_current_user_id
from app.core.config import get_settings
from app.core.ratelimit import consume
from app.core.response import BizError, ok
from app.db import get_session_factory
from app.models import Attempt, Placement, PlacementQuestion
from app.models.base import AttemptKinds, Levels, PlacementQuestionKind
from app.placement.grammar import judge_grammar, judge_qa_answer
from app.placement.scoring import compute_accuracy, compute_fluency, compute_s, level_for

logger = logging.getLogger("vocalverse")

router = APIRouter(prefix="/api/v1/placement", tags=["placement"])


def _latest_completed(db, user_id: int) -> Placement | None:
    """该用户最近一次 completed 定档（复测基线/复测资格判定用）。"""
    return db.execute(
        select(Placement)
        .where(Placement.user_id == user_id, Placement.status == "completed")
        .order_by(Placement.completed_at.desc())
    ).scalar_one_or_none()


def _latest_real_completed(db, user_id: int, settings) -> Placement | None:
    """最近一次**真实**（非 skip 跳过） completed 定档 —— 冷却 gate 判定用（C5：skip 不计冷却）。"""
    rows = db.execute(
        select(Placement)
        .where(Placement.user_id == user_id, Placement.status == "completed")
        .order_by(Placement.completed_at.desc())
    ).scalars()
    for p in rows:
        details = p.details if isinstance(p.details, dict) else {}
        if not details.get("skipped"):
            return p
    return None


def _cooldown_remaining_days(latest: Placement | None, settings) -> int:
    """距复测冷却剩余天数（C3t：距上次 completed 定档；0 = 已可复测）。"""
    if latest is None or latest.completed_at is None:
        return 0
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    completed_at = latest.completed_at
    if completed_at.tzinfo is None:
        completed_at = completed_at.replace(tzinfo=UTC)
    elapsed_days = (now - completed_at).total_seconds() / 86400.0
    return max(0, math.ceil(settings.placement_retest_cooldown_days - elapsed_days))


def _get_or_create_run(db, user_id: int, revision: int) -> Placement:
    """B1：取该用户 in_progress 的考试 run（复用）；无则创建；并发冲突 → 40910。

    返回值绑定在当前 session。``exam_revision`` 在创建时从首题写入（C11）。
    创建一个新 run 前做 **复测冷却 gate（42902）**：已有 completed 定档且距其 < 冷却期内，
    视为频繁重考 → 拒绝（防刷分）。首次测试（无 completed）不受限。
    """
    run = db.execute(
        select(Placement).where(Placement.user_id == user_id, Placement.status == "in_progress")
    ).scalar_one_or_none()
    if run is not None:
        return run
    # C3t 复测冷却 gate（42902）：新建 run 且已有真实 completed 定档在冷却期内 → 拒绝
    latest = _latest_real_completed(db, user_id, get_settings())
    if latest is not None:
        remaining = _cooldown_remaining_days(latest, get_settings())
        if remaining > 0:
            raise BizError(
                http_status=429,
                code=42902,
                message=f"retest in cooldown, remaining {remaining}d",
            )
    run = Placement(user_id=user_id, status="in_progress", exam_revision=revision)
    db.add(run)
    try:
        db.commit()
    except IntegrityError:
        # 部分唯一索引 (user_id) WHERE status='in_progress' 兜底并发：另一个请求刚创建成功
        db.rollback()
        run = db.execute(
            select(Placement).where(Placement.user_id == user_id, Placement.status == "in_progress")
        ).scalar_one_or_none()
        if run is None:
            raise BizError(http_status=409, code=40910, message="placement run conflict") from None
    else:
        db.refresh(run)
    return run


@router.get("/questions")
async def questions(user_id: int = Depends(get_current_user_id)):
    db = get_session_factory()()
    try:
        rows = db.execute(
            select(PlacementQuestion)
            .where(PlacementQuestion.status == "published")
            .order_by(PlacementQuestion.exam_revision, PlacementQuestion.item_index)
        ).scalars()
        return ok(
            [
                {
                    "id": q.id,
                    "kind": q.kind,
                    "prompt": q.prompt,
                    "reference_answer": q.reference_answer,
                }
                for q in rows
            ]
        )
    finally:
        db.close()


@router.get("/status")
async def placement_status(user_id: int = Depends(get_current_user_id)):
    """复测资格预检（C3t / C-5 精简版）：当前档位 + 是否可复测 + 冷却剩余天数。"""
    settings = get_settings()
    db = get_session_factory()()
    try:
        completed = list(
            db.execute(
                select(Placement)
                .where(Placement.user_id == user_id, Placement.status == "completed")
                .order_by(Placement.completed_at.desc())
            ).scalars()
        )
        latest = completed[0] if completed else None
        cooldown = _cooldown_remaining_days(latest, settings)
        return ok(
            {
                "has_completed": bool(completed),
                "completed_count": len(completed),
                "current_level": latest.level if latest else None,
                "last_completed_at": (
                    latest.completed_at.isoformat() if latest and latest.completed_at else None
                ),
                "can_retest": bool(latest is not None and cooldown == 0),
                "cooldown_remaining_days": cooldown,
            }
        )
    finally:
        db.close()


@router.post("/retest")
async def retest(user_id: int = Depends(get_current_user_id)):
    """开始复测（C3t）：eligible 40302（无已完基线）+ 冷却 42902（_get_or_create_run 内），
    通过后创建/续用 run 并返回题型快照。首次测试不经此端点（走 score_item 惰性建 run）。"""
    db = get_session_factory()()
    try:
        latest = _latest_completed(db, user_id)
        if latest is None:
            raise BizError(
                http_status=403, code=40302, message="retest requires prior completed placement"
            )
        revision = latest.exam_revision or 1
        # 若当前发布了更高版本题库，复测用最新发布版本（与前端将见题目一致）
        pub_rev = db.execute(
            select(PlacementQuestion.exam_revision)
            .where(PlacementQuestion.status == "published")
            .order_by(PlacementQuestion.exam_revision.desc())
            .limit(1)
        ).scalar_one_or_none()
        revision = pub_rev or revision
        run = _get_or_create_run(db, user_id, revision)  # 冷却 gate 在此触发（42902）
        questions = db.execute(
            select(PlacementQuestion)
            .where(PlacementQuestion.status == "published")
            .order_by(PlacementQuestion.exam_revision, PlacementQuestion.item_index)
        ).scalars()
        return ok(
            {
                "placement_id": run.id,
                "exam_revision": revision,
                "questions": [
                    {
                        "id": q.id,
                        "kind": q.kind,
                        "prompt": q.prompt,
                        "reference_answer": q.reference_answer,
                    }
                    for q in questions
                ],
                "can_start": True,
            }
        )
    finally:
        db.close()


@router.post("/skip")
async def skip(user_id: int = Depends(get_current_user_id)):
    """C5 跳过入学测试：创建 provisional completed placement（level=L2，details.skipped=True），
    使 ``POST /sessions`` 的 40303 门禁通过、可直接进入练习；skip **不计**复测冷却（可立即实测）。
    若已有 completed 定档则幂等返回现有（不覆盖更高档）。
    """
    db = get_session_factory()()
    try:
        latest = _latest_completed(db, user_id)
        if latest is not None:
            return ok(
                {
                    "placement_id": latest.id,
                    "level": latest.level,
                    "skipped": bool(
                        isinstance(latest.details, dict) and latest.details.get("skipped")
                    ),
                }
            )
        revision = (
            db.execute(
                select(PlacementQuestion.exam_revision)
                .where(PlacementQuestion.status == "published")
                .order_by(PlacementQuestion.exam_revision.desc())
                .limit(1)
            ).scalar_one_or_none()
            or 1
        )
        p = Placement(
            user_id=user_id,
            status="completed",
            completed_at=datetime.now(UTC),
            exam_revision=revision,
            level=Levels.L2,
            details={"schema_version": "2d", "skipped": True, "provisional": True},
        )
        db.add(p)
        db.commit()
        db.refresh(p)
        await _callback_level(user_id, Levels.L2, p.completed_at)
        return ok({"placement_id": p.id, "level": Levels.L2, "skipped": True})
    finally:
        db.close()


@router.post("/items/{item_id}/audio")
async def score_item(
    item_id: int,
    audio: UploadFile = File(...),
    user_id: int = Depends(get_current_user_id),
):
    """单题录音评分。A2：qa 只 ASR（不 ISE）；read 走 ISE（pron/flu/completeness）。

    顺序（保持既有 40002/404 语义：先校验再扣额，见 test_m2_core）：
        校验音频(40002) → 题目查找(404) → 创建/续用 run(B1) → 扣 asr(+ise 仅 read) →
        ASR → ISE(仅 read) → LLM 语法(+qa 相关度 B2) → 落 Attempt（placement_id=run.id）。
    """
    settings = get_settings()
    data = validate_audio_bytes(
        await audio.read(),
        min_bytes=settings.min_upload_bytes,
        max_bytes=settings.max_upload_bytes,
    )
    db = get_session_factory()()
    try:
        q = db.get(PlacementQuestion, item_id)
        if q is None or q.status != "published":
            raise HTTPException(status_code=404, detail="question not found")

        # 先扣额（避免 429 留下孤儿 in_progress run），再创建/续用 run（B1）
        is_qa = q.kind == PlacementQuestionKind.QA
        await consume("asr", settings.asr_rate_per_hour, user_id)
        if not is_qa:
            await consume("ise", settings.ise_rate_per_hour, user_id)

        run = _get_or_create_run(db, user_id, q.exam_revision)  # B1

        asr = get_asr_client()
        asr_res = await asr.transcribe(data)
        text = asr_res.text
        # docs/19 §2：转写词数 < 5 → 无有效语音，不送 ISE 评测/不落 Attempt
        # （兜底防 whisper 对纯音/噪声幻听短词仍被 ISE 打高分）
        if not has_min_words(text):
            raise BizError(
                http_status=400, code=40002, message="transcript has insufficient speech"
            )
        # 流利度时间戳特征（docs/06 §9.3 辅助口径；与对话链路同源，origin/main 1fa86af 并入）
        fluency = compute_fluency_features(asr_res.words or [], float(asr_res.duration or 0.0))

        # read 题：ISE 评 pron/flu/completeness；qa 题：不跑 ISE（只 ASR，A2）
        score = None
        completeness = None
        if not is_qa:
            scorer = get_scorer_client()
            try:
                score = await scorer.score(data, q.prompt)
                completeness = score.completeness if score else None
            except Exception:  # noqa: BLE001 - ISE 失败 → 分数 None，不伪造（docs/10 §4.3）
                score = None

        # read/qa 均补调 LLM 语法（A1）；qa 另给相关度标签（B2，一次调用返 grammar+relevance）
        grammar = None
        relevance = None
        if is_qa:
            qa = await judge_qa_answer(text, q.prompt)
            if qa:
                grammar = qa.get("grammar")
                relevance = qa.get("relevance")
        else:
            grammar = await judge_grammar(text, q.prompt)
        attempt = Attempt(
            user_id=user_id,
            kind=AttemptKinds.PLACEMENT_ITEM,
            placement_id=run.id,  # B3 消费标记
            transcript=text,
            pron_score=_dec(score.pronunciation) if score else None,
            flu_score=_dec(score.fluency) if score else None,
            completeness=_dec(completeness) if completeness is not None else None,
            gram_score=_dec(grammar["score"])
            if grammar and grammar.get("score") is not None
            else None,
            overall_score=_dec(score.overall) if score else None,
            wpm=_dec(fluency["wpm"]) if fluency else None,
            error={} if (score is not None or is_qa) else {"reason": "score_unavailable"},
            details={
                "item_index": q.item_index,
                "exam_revision": q.exam_revision,
                "kind": q.kind,
                "prompt": q.prompt,
                "grammar": grammar,  # 诊断快照（C11 可追溯依赖 exam_revision）
                "qa": {"relevance": relevance} if is_qa else None,
                "fluency": fluency,  # wpm/停顿时间戳特征（origin/main 并入）
            },
        )
        db.add(attempt)
        db.commit()
        db.refresh(attempt)
        return ok(
            {
                "placement_id": run.id,
                "attempt_id": attempt.id,
                "transcript": text,
                "pron": float(score.pronunciation) if score else None,
                "flu": float(score.fluency) if score else None,
                "completeness": float(completeness) if completeness is not None else None,
                "gram": grammar["score"] if grammar and grammar.get("score") is not None else None,
                "relevance": relevance,
                "wpm": float(attempt.wpm) if attempt.wpm is not None else None,
            }
        )
    finally:
        db.close()


class FinalizeIn(BaseModel):
    attempts: list[int]


@router.post("/finalize")
async def finalize(body: FinalizeIn, user_id: int = Depends(get_current_user_id)):
    """两维综合分 S → 水平档（C1）。完成该用户的 in_progress run（B3 幂等）。

    - 校验：attempt 归该用户且已评分 read 题 ≥ ``placement_min_read_items``（C5，默认 1），否则
      42203；
    - 幂等：run 已 completed → 直接返回已结算结果（不再重算/重复落库）；
    - code 42201（无 attempt）/40401（run 不存在）；S 公式/阈值由配置单源计算（A5），禁用硬编码。
    """
    cfg = get_settings()
    db = get_session_factory()()
    try:
        rows = db.execute(
            select(Attempt).where(Attempt.id.in_(body.attempts), Attempt.user_id == user_id)
        ).scalars()
        attempts = list(rows)
        if not attempts:
            raise BizError(http_status=422, code=42201, message="no attempts")

        run_ids = {a.placement_id for a in attempts if a.placement_id is not None}
        if not run_ids:
            raise BizError(http_status=422, code=42201, message="attempts not linked to a run")
        if len(run_ids) > 1:
            raise BizError(http_status=422, code=42201, message="attempts span multiple runs")

        run = db.get(Placement, next(iter(run_ids)))
        if run is None:
            raise BizError(http_status=404, code=40401, message="placement run not found")

        # B3 幂等：已结算的 run 直接返回缓存结果，不重复落库
        if run.status == "completed":
            return ok(
                {
                    "placement_id": run.id,
                    "level": run.level,
                    "total_score": float(run.overall_score)
                    if run.overall_score is not None
                    else None,
                    "pron": float(run.pron_score) if run.pron_score is not None else None,
                    "flu": float(run.flu_score) if run.flu_score is not None else None,
                    "gram": float(run.gram_score) if run.gram_score is not None else None,
                }
            )

        # 权威：用该 run 的全部 attempts 计算（非只取 request 带来的子集）
        run_attempts = list(
            db.execute(
                select(Attempt).where(Attempt.placement_id == run.id, Attempt.user_id == user_id)
            ).scalars()
        )
        read_attempts = [a for a in run_attempts if a.pron_score is not None]
        if len(read_attempts) < cfg.placement_min_read_items:
            raise BizError(
                http_status=422,
                code=42203,
                message=f"need at least {cfg.placement_min_read_items} scored read item(s)",
            )

        a = compute_accuracy([a.pron_score for a in read_attempts])
        f = compute_fluency(
            [a.flu_score for a in read_attempts],
            [a.completeness for a in read_attempts],
            cfg,
        )
        if a is None or f is None:
            # 防御：两维公式缺任一维度则无法判定档位（不应发生，见 min_read 守卫）
            raise BizError(http_status=422, code=42203, message="insufficient scoreable dimensions")
        s = compute_s(a, f, cfg)
        level = level_for(s, cfg)

        # 语法诊断（不进 S）：取有 gram_score 的项均值，无则 None
        gram_vals = [float(at.gram_score) for at in run_attempts if at.gram_score is not None]
        gram_mean = sum(gram_vals) / len(gram_vals) if gram_vals else None

        run.status = "completed"
        completed_at = datetime.now(UTC)
        run.completed_at = completed_at
        run.level = level
        run.overall_score = round(_dec(s), 2)
        run.pron_score = round(_dec(a), 2)
        run.flu_score = round(_dec(f), 2)
        run.gram_score = round(_dec(gram_mean), 2) if gram_mean is not None else None
        run.details = {
            "attempt_ids": [at.id for at in run_attempts],
            "accuracy": round(a, 2),
            "fluency": round(f, 2),
            "schema_version": "2d",
            "items": [
                {
                    "attempt_id": at.id,
                    "kind": at.details.get("kind") if isinstance(at.details, dict) else None,
                    "prompt": at.details.get("prompt") if isinstance(at.details, dict) else None,
                    "transcript": at.transcript,
                    "gram_score": float(at.gram_score) if at.gram_score is not None else None,
                    "relevance": (
                        (at.details.get("qa") or {}).get("relevance")
                        if isinstance(at.details, dict)
                        else None
                    ),
                }
                for at in run_attempts
            ],
        }
        db.commit()
        # Java 回写 user_profiles（service-token 内部 REST；D2/C2 修复见 _callback_level）
        await _callback_level(user_id, level, completed_at)
        return ok(
            {
                "placement_id": run.id,
                "level": level,
                "total_score": round(s, 2),
                "pron": round(a, 2),
                "flu": round(f, 2),
                "gram": round(gram_mean, 2) if gram_mean is not None else None,
            }
        )
    finally:
        db.close()


def _refresh_expired(obj) -> None:
    """幂等分支读已 commit 对象属性前的防卫（触发 reload，确保非过期/已删除不炸）。"""
    # SQLAlchemy 在 commit 后默认过期属性；访问属性会重新 select。此处显式触达一次即可。
    _ = obj.id


def _level_callback_payload(user_id: int, level: str, level_at: datetime) -> dict:
    """内部 REST ``POST /internal/level`` 请求体（C2 修复：键名必须 ``userId``，Java 侧约定）。

    契约真源（docs/21 §5 / local/34 D-2）：``{userId, level, source, levelAt}``；
    ``levelAt`` 供 Java 幂等 PUT 比较（较新才落，C9）。
    """
    return {
        "userId": user_id,
        "level": level,
        "source": "placement",
        "levelAt": level_at.isoformat(),
    }


async def _callback_level(user_id: int, level: str, level_at: datetime | None = None) -> None:
    """委托 Java 更新 user_profiles.cefr_level（Java 唯一写者；内部 service-token）。

    修复（docs/19 P0-6 / C2 / local/34 D-2/D-3）：
    - payload 键用 ``userId``（Java 约定，原 ``user_id`` 致 400 被吞）；
    - 带 ``source='placement'`` + ``levelAt``（幂等 PUT 依据：较新才落，C9）；
    - ``raise_for_status()`` + 失败**记日志告警**（不再静默吞掉），但仍不阻塞入学测试。
    """
    settings = get_settings()
    level_at = level_at or (datetime.now(UTC))
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.post(
                f"{settings.java_base_url}/internal/level",
                json=_level_callback_payload(user_id, level, level_at),
                headers={"Authorization": f"Bearer {settings.service_token}"},
            )
            resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001 - 内部回调失败不阻塞入学测试（placements 作校对源）
        logger.error("placement level callback to Java failed: %s", exc)
        return


def _dec(v):
    from decimal import Decimal

    if v is None:
        return None
    return Decimal(str(round(float(v), 2)))
