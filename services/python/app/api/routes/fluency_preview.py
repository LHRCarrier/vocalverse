"""流利度时间戳特征测试台（test-only，团队联调用，可整体删除）。

设计约束（与 Agent Lab 同规格，2026-09-03 组长要求）：
- **不影响其它代码**：`include_in_schema=False`（不进 OpenAPI 契约快照 → CI 对账零影响）、
  无表/无迁移、不碰 practice/audio 既有路由；默认关闭（`fluency_preview_enabled=False`，
  未开启时路由不注册 → 404）；
- **删除无影响**（删除清单见本文件末尾注释）；有真实 ASR/ISE 调用（whisper + 讯飞），
  仅在本地/团队环境开启（APP_FLUENCY_PREVIEW_ENABLED=true），**生产必须保持关闭**。

能力：
- POST /api/v1/fluency-preview/analyze  上传音频（+ 可选参考文本）→ 真 ASR（词级时间戳）
  → 流利度时间戳特征 →（可选）真 ISE 评分 → 返回与 attempts/report 同结构的演示载荷，
  供前端测试页复现「特征 → 报告呈现」的联调效果。
"""

from __future__ import annotations

from fastapi import APIRouter, File, Form, UploadFile

from app.audio.base import get_asr_client, get_scorer_client
from app.audio.fluency import compute_fluency_features
from app.audio.upload import validate_audio_bytes
from app.core.config import get_settings
from app.core.response import Envelope, ok

router = APIRouter(
    prefix="/api/v1/fluency-preview", tags=["fluency-preview"], include_in_schema=False
)  # include_in_schema=False：不进 OpenAPI 契约快照（同 agent-lab 测试台约束）

# ISE 句子级评测的参考文本长度上限（口语单句/短段；整篇歌词会触发降级而非盲等）
MAX_ISE_REF_CHARS = 300


@router.post("/analyze")
async def analyze(
    audio: UploadFile = File(...),
    reference: str = Form(default=""),
    use_transcript_ref: bool = Form(default=False),
) -> Envelope[dict]:
    """音频 → 词级时间戳 → 流利度特征 →（有参考时）发音评分。

    参考文本优先级：手动 `reference` → `use_transcript_ref=true` 时用 ASR 转写
    （「转写对转写」，与生产对话链路同口径，orchestrator._dialog_turn）→ 无参考不评分。
    返回 `score_ref`（manual/transcript/None）与 `score_error`（降级原因）供页面标注。

    口语口径守卫（docs/06 §9.3）：ISE 是句子级口语评测——音频 >60s（说话句上限）或
    参考 >MAX_ISE_REF_CHARS 字符时**不再盲等 ISE**，直接降级并给出原因；
    唱歌长音频（如整曲 3-4 分钟）走 M3 音准/节奏链路（sing_attempts），本台不适用。

    无状态测试端点：只守上界（min_bytes=0 与 /asr 同口径）；不扣限流、不落库。
    测试环境（APP_TESTING=true）走 FakeASR/FakeScorer，CI 零真实 Key。
    """
    settings = get_settings()
    data = validate_audio_bytes(
        await audio.read(), min_bytes=0, max_bytes=settings.max_upload_bytes
    )
    asr_res = await get_asr_client().transcribe(data)
    features = compute_fluency_features(asr_res.words or [], float(asr_res.duration or 0.0))

    score = None
    score_ref: str | None = None
    score_error: str | None = None
    ref_text = (
        reference.strip() if reference.strip() else (asr_res.text if use_transcript_ref else "")
    )
    if ref_text:
        score_ref = "manual" if reference.strip() else "transcript"
        duration = float(asr_res.duration or 0.0)
        if duration > settings.max_speech_seconds:
            score_error = (
                f"audio_too_long({round(duration)}s > 口语上限 {settings.max_speech_seconds}s；"
                "唱歌走 M3 音准/节奏链路)"
            )
        elif len(ref_text) > MAX_ISE_REF_CHARS:
            score_error = (
                f"reference_too_long({len(ref_text)} > {MAX_ISE_REF_CHARS} 字符；"
                "整篇歌词不适合句子级评测)"
            )
        else:
            try:
                s = await get_scorer_client().score(data, ref_text)
                score = {
                    "overall": float(s.overall),
                    "pronunciation": float(s.pronunciation),
                    "fluency": float(s.fluency),
                    "grammar": float(s.grammar) if s.grammar is not None else None,
                }
            except Exception as exc:  # 评分失败不强求（测试台以特征为主）
                score_error = f"ise_failed({type(exc).__name__})"

    return ok(
        {
            "text": asr_res.text,
            "language": asr_res.language,
            "words": asr_res.words,
            "duration_s": float(asr_res.duration or 0.0),
            "features": features,
            "score": score,
            "score_ref": score_ref,
            "score_error": score_error,
            # 与完整对话回合落进 attempts/report 的同构演示载荷（口径 docs/06 §9.3）
            "attempt_demo": {
                "transcript": asr_res.text,
                "wpm": features["wpm"],
                "fluency_features": features,
            },
        }
    )


"""
删除清单（流利度特征测试台整删无影响）：
1. 删 `apps/web/src/views/preview/FluencyPreview.vue` + `views/preview/registry.ts` 该行
   + `router/preview.ts` 该路由（dev-only 子树，生产构建零体积）；
2. 删本文件 + `main.py` 的 `fluency_preview` import 与 `include_router` 两行（约 3 行）；
3. 删 `app/core/config.py` 的 `fluency_preview_enabled` 一行；
4. 收尾：全量 pytest / pnpm typecheck / lint；契约快照零 diff（include_in_schema=False）。
"""

__all__ = ["router"]
