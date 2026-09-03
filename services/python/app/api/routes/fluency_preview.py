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


@router.post("/analyze")
async def analyze(
    audio: UploadFile = File(...),
    reference: str = Form(default=""),
) -> Envelope[dict]:
    """音频 → 词级时间戳 → 流利度特征 →（参考文本非空时）发音评分。

    无状态测试端点：只守上界（min_bytes=0 与 /asr 同口径）；不扣限流、不落库。
    测试环境（APP_TESTING=true）走 FakeASR/FakeScorer，CI 零真实 Key。
    """
    data = validate_audio_bytes(
        await audio.read(), min_bytes=0, max_bytes=get_settings().max_upload_bytes
    )
    asr_res = await get_asr_client().transcribe(data)
    features = compute_fluency_features(asr_res.words or [], float(asr_res.duration or 0.0))

    score = None
    if reference.strip():
        try:
            s = await get_scorer_client().score(data, reference)
            score = {
                "overall": float(s.overall),
                "pronunciation": float(s.pronunciation),
                "fluency": float(s.fluency),
                "grammar": float(s.grammar) if s.grammar is not None else None,
            }
        except Exception:  # 评分失败不强求（测试台以特征为主）
            score = None

    return ok(
        {
            "text": asr_res.text,
            "language": asr_res.language,
            "words": asr_res.words,
            "duration_s": float(asr_res.duration or 0.0),
            "features": features,
            "score": score,
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
