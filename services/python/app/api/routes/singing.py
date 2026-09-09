"""唱歌 C 端路由（M3 唱歌 P0 D7：三端点 + 复用 POST /sessions）。

- ``POST /api/v1/sessions/{id}/audio``：整首音频上传（multipart）→ 建评分任务；
- ``GET /api/v1/sing/attempts/{id}/status``：任务状态轮询（queued→processing→done|failed）；
- ``GET /api/v1/sing/attempts/{id}``：评分结果（done 后取；逐句 + 综合 + alignment）。

鉴权/限流（docs/21 §2.1 op 22~24）：Bearer（Security 级依赖，见 core.auth）；
sing 桶 5/h + ise 桶（发音抽样）在 service 层 consume；错误码 40905/41302/40002 先登记后用。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile

from app.core.auth import get_current_user_id
from app.core.response import ok
from app.sing.service import get_attempt_result, get_attempt_status, submit_song_audio

router = APIRouter(prefix="/api/v1", tags=["singing"])


@router.post("/sessions/{session_id}/audio")
async def upload_song_audio(
    session_id: int,
    audio: UploadFile = File(...),
    user_id: int = Depends(get_current_user_id),
):
    """整首跟唱音频上传 → 异步评分任务（20MB/180s；校验后扣桶，失败不扣）。"""
    data = await audio.read()
    result = await submit_song_audio(user_id, session_id, data)
    return ok(result)


@router.get("/sing/attempts/{attempt_id}/status")
async def attempt_status(
    attempt_id: int,
    user_id: int = Depends(get_current_user_id),
):
    return ok(await get_attempt_status(attempt_id, user_id))


@router.get("/sing/attempts/{attempt_id}")
async def attempt_result(
    attempt_id: int,
    user_id: int = Depends(get_current_user_id),
):
    return ok(await get_attempt_result(attempt_id, user_id))
