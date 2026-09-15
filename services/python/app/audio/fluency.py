"""流利度时间戳特征（docs/06 §9.3 辅助口径；数据源：ASR 词级时间戳）。

口径（docs/07 Q30 拍板：「讯飞流利度」是权威流利度项，本模块只出**辅助**特征，
不另起一套流利度；报告额外给出语速 words/min 作辅助）：

- **wpm（语速）** = 词数 / (有效说话段时长/60)。有效说话段 = 首词 start → 末词 end，
  排除录音首尾静默（用户按录音键到开口的延迟不算语速惩罚）；
- **articulation_rate（纯发音速率）** = 词数 / ((有效说话段 − 停顿总时长)/60)；
- **停顿** = 相邻两词的间隙 ≥ PAUSE_THRESHOLD_S（0.5s）。仅统计有效说话段内
  的**跨词间隙**：首词前/末词后的静默不计（录音边沿噪声，不是口语停顿）；
- **pause_ratio（停顿占比）** = 停顿总时长 / 有效说话段时长；
- **long_pause（长停顿）** ≥ LONG_PAUSE_THRESHOLD_S（1.0s）。

输入 words：`[{word, start, end, ...}]`（whisper word_timestamps，秒）；
duration_s：音频总时长（秒；0/未知时取末词 end）。
输出恒定结构（缺输入/坏数据一律 0，不抛异常）——前端/测试台按此键集渲染。
"""

from __future__ import annotations

from typing import Any

# 停顿阈值（推荐停顿中间值：0.5s 语音间隙在口语流利度研究中常被定为「非流利停顿」下界；
# whisper 词级时间戳精度 ±0.1s 量级，0.3s 以下阈值会混入时间戳噪声）
PAUSE_THRESHOLD_S = 0.5
# 长停顿阈值（≥1s 是听感上明显的卡壳/忘词停顿）
LONG_PAUSE_THRESHOLD_S = 1.0

_FIELDS = (
    "word_count",
    "speech_s",
    "total_s",
    "wpm",
    "articulation_rate",
    "pause_count",
    "long_pause_count",
    "pause_total_s",
    "mean_pause_s",
    "max_pause_s",
    "pause_ratio",
)


def _empty() -> dict[str, float | int]:
    return {k: 0 for k in _FIELDS}


def _num(v: Any) -> float | None:
    """容忍 None/非数值/负数的时间戳条目 → None（该词跳过特征统计）。"""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f >= 0 else None


def compute_fluency_features(words: list[dict[str, Any]], duration_s: float = 0.0) -> dict:
    """词级时间戳 → 流利度时间戳特征（纯函数；恒定键集，永不抛异常）。

    :param words: [{word, start, end, ...}]；start/end 为秒
    :param duration_s: 音频总时长（秒）；<=0 时以末词 end 兜底
    """
    spans: list[tuple[float, float]] = []
    for w in words or []:
        start = _num(w.get("start"))
        end = _num(w.get("end"))
        if start is None or end is None or end <= start:
            continue
        spans.append((start, end))

    if not spans:
        return _empty()

    spans.sort(key=lambda p: p[0])
    first = spans[0][0]
    last = max(e for _, e in spans)
    # 说话段定义需要 ≥2 词（词间距离才构成跨度）；单词/无有效时间戳 → speech_s=0 → wpm=0
    speech_s = max(0.0, last - first) if len(spans) >= 2 else 0.0
    total_s = duration_s if duration_s and duration_s > 0 else last

    out = _empty()
    out["word_count"] = len(spans)
    out["speech_s"] = round(speech_s, 2)
    out["total_s"] = round(total_s, 2)

    if speech_s <= 0:
        return out

    # 跨词间隙（仅有效说话段内；间隙 = 下一词 start − 上一词 end）
    gaps = [
        b - a
        for (_, a), (b, _) in zip(spans, spans[1:], strict=False)
        if b - a >= PAUSE_THRESHOLD_S
    ]
    pause_total = sum(gaps) if gaps else 0.0
    out["pause_count"] = len(gaps)
    out["long_pause_count"] = sum(1 for g in gaps if g >= LONG_PAUSE_THRESHOLD_S)
    out["pause_total_s"] = round(pause_total, 2)
    out["mean_pause_s"] = round(pause_total / len(gaps), 2) if gaps else 0
    out["max_pause_s"] = round(max(gaps), 2) if gaps else 0
    out["pause_ratio"] = round(pause_total / speech_s, 4) if speech_s > 0 else 0

    out["wpm"] = round(len(spans) / (speech_s / 60.0), 2)
    articulation_s = speech_s - pause_total
    out["articulation_rate"] = (
        round(len(spans) / (articulation_s / 60.0), 2) if articulation_s > 0 else 0
    )
    return out


__all__ = ["compute_fluency_features", "PAUSE_THRESHOLD_S", "LONG_PAUSE_THRESHOLD_S"]
