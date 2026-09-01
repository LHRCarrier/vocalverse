"""上传音频的公共校验（大小上下界）。

上界 41301 见 docs/06 §7；下界 40002 用于挡住「空/近空音频」——
前端录音停止键修好后，误触会产生 ~0ms 的 webm 容器（几百字节），
而 placement/practice 收下即推进题目或回合且**不可重来**，还会白白消耗
ASR/ISE 限流额度。故这两条链路在扣额度之前先做下界校验。

`/api/v1/asr`、`/api/v1/score` 是无状态的管线端点（不消耗可耗尽资源），
沿用 min_bytes=0 的历史行为，只共用上界实现。
"""

from __future__ import annotations

from app.core.response import BizError


def validate_audio_bytes(data: bytes | None, *, min_bytes: int, max_bytes: int) -> bytes:
    """校验音频字节数，越界抛 BizError；通过则原样返回。"""
    if data is None or len(data) < min_bytes:
        raise BizError(
            http_status=400,
            code=40002,
            message="audio empty or too short",
        )
    if len(data) > max_bytes:
        raise BizError(http_status=413, code=41301, message="audio too large")
    return data
