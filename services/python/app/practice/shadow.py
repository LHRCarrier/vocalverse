"""影子跟读域（docs/06 §9.3；DoD ④，2026-09-04 定）。

评分三维（docs/19 P0-5 方案 A 的语音侧可实现子集；重音落点/连读识别留待
M3 前端韵律引擎（docs/24 ①），本版登记为 P2 不伪造）：

- **pron（发音）** = ISE accuracy_score（权威，docs/07 Q30 同源）；
- **speed_match（语速匹配度）** = 用户 wpm vs 素材原声 wpm（`shadow_materials.wpm`；
  素材缺 wpm → 该维 None，不展示不造分）：偏差 |user−ref|/ref ≤10%→95+、≤20%→85+、
  ≤35%→70+、≤50%→55+、其余 40（分段阈值，风格对齐 local/28 难度阈值表）；
- **pause_score（停顿密度）** = 用户 `pause_ratio`（停顿总时长/说话段，fluency.py）：
  越少越好：≤5%→95+、≤10%→85+、≤20%→70+、≤35%→55+、其余 40-；
- **overall** = 0.4·pron + 0.3·speed + 0.3·pause，缺失维度按剩余权重归一（圆整 0-100）。

素材跟读文本 `text_content` 按行分句（`\n`），空行剔除；单行 = 整体一段。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

W_PRON = 0.4
W_SPEED = 0.3
W_PAUSE = 0.3


@dataclass
class ShadowScoring:
    """一次跟读评分的结构化结果（attempts.details.shadow 同构）。"""

    pron: float | None = None
    speed_match: float | None = None
    pause_score: float | None = None
    overall: float | None = None
    user_wpm: float | None = None
    ref_wpm: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "pron": self.pron,
            "speed_match": self.speed_match,
            "pause_score": self.pause_score,
            "overall": self.overall,
            "user_wpm": self.user_wpm,
            "ref_wpm": self.ref_wpm,
        }


def split_sentences(text_content: str | None) -> list[str]:
    """跟读文本分句（按行；空行/空白剔除；空文本 → []）。"""
    if not text_content:
        return []
    return [line.strip() for line in text_content.splitlines() if line.strip()]


def speed_match_score(user_wpm: float, ref_wpm: float) -> float | None:
    """语速匹配度：偏差比例分段（0.4 权重；原始 wpm 无效 → None）。

    diff = |user − ref| / ref：≤0.10→95+、≤0.20→85+、≤0.35→70+、≤0.50→55+、其余 40。
    """
    if user_wpm is None or ref_wpm is None or ref_wpm <= 0 or user_wpm <= 0:
        return None
    diff = abs(user_wpm - ref_wpm) / ref_wpm
    if diff <= 0.10:
        return 95.0
    if diff <= 0.20:
        return 85.0
    if diff <= 0.35:
        return 70.0
    if diff <= 0.50:
        return 55.0
    return 40.0


def pause_density_score(pause_ratio: float) -> float | None:
    """停顿密度分：pause_ratio 越低越好（0.3 权重）。"""
    if pause_ratio is None:
        return None
    if pause_ratio <= 0.05:
        return 95.0
    if pause_ratio <= 0.10:
        return 85.0
    if pause_ratio <= 0.20:
        return 70.0
    if pause_ratio <= 0.35:
        return 55.0
    return 40.0


def shadow_scores(
    pron: float | None, user_wpm: float | None, ref_wpm: int | None, pause_ratio: float | None
) -> ShadowScoring:
    """三维 → 汇总（整体 = 0.4/0.3/0.3 加权；缺失维度按剩余权重归一；全缺 → overall None）。"""
    speed = speed_match_score(user_wpm, ref_wpm) if (user_wpm is not None and ref_wpm) else None
    pause = pause_density_score(pause_ratio)
    parts: list[tuple[float, float]] = []
    if pron is not None:
        parts.append((W_PRON, float(pron)))
    if speed is not None:
        parts.append((W_SPEED, float(speed)))
    if pause is not None:
        parts.append((W_PAUSE, float(pause)))
    overall = round(sum(w * v for w, v in parts) / sum(w for w, _ in parts)) if parts else None
    return ShadowScoring(
        pron=float(pron) if pron is not None else None,
        speed_match=speed,
        pause_score=pause,
        overall=overall,
        user_wpm=user_wpm,
        ref_wpm=ref_wpm,
    )


def coach_note(sc: ShadowScoring) -> str | None:
    """教练笔记（规则版；与对话 MetaExecutor 的 coach 语义一致——同轮一致性）。"""
    if sc.overall is None:
        return None
    if sc.overall >= 90:
        return "Great shadowing! You matched the pace and rhythm well."
    if sc.overall >= 75:
        return "Nice! Try to follow the speaker's pace a little more closely."
    if sc.overall >= 60:
        hint = []
        if sc.speed_match is not None and sc.speed_match < 75:
            hint.append("pace")
        if sc.pause_score is not None and sc.pause_score < 75:
            hint.append("pausing")
        return f"Keep practicing — work on your {(' and '.join(hint)) or 'intonation'}."
    return "Slow down and shadow phrase by phrase. Repeat after the model audio."


__all__ = [
    "ShadowScoring",
    "split_sentences",
    "speed_match_score",
    "pause_density_score",
    "shadow_scores",
    "coach_note",
    "W_PRON",
    "W_SPEED",
    "W_PAUSE",
]
