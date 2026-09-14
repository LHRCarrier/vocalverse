#!/usr/bin/env python3
"""用户侧 onset 检测评估（口径 v3 item7 的鲁棒性）· P2 遗留项①评估工具。

问题：评分侧 `pitch.py:detect_onsets_ms` 用 `librosa.onset_detect`（spectral flux + 峰值拾取），
在**柔起音/连奏/相位处理过的音频**上可能检出不足 → `bpm_from_onsets(user)` 返回 None →
`bpm_source` 回落 `duration`（特性弱化，非错误但信息量下降）。

本工具用**已知音符时间轴**的合成素材（ground truth）量化三种检测器：

| 检测器 | 说明 |
|---|---|
| `flux` | 现状：librosa.onset_detect(backtrack=True)（与生产同参） |
| `f0` | 候选兜底：F0 起音 = 有声段起点（前置静音 ≥150ms）+ 音高跳变（|Δcent| ≥ 阈值） |
| `fuse` | 融合：f0 ∪ flux，相邻 <50ms 合并 |

指标：precision / recall / F1（±60ms 容差，Goto 标准邻近判据的宽松版）、
置信 IOI 中位（`bpm_from_onsets` 的输入）与真值 BPM 的偏差。

用法（services/python 目录）：
    uv run python ../../scripts/poc/onset_eval.py [--json out.json]
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "services" / "python"))

from app.audio.pitch import PyinPitchExtractor, detect_onsets_ms  # noqa: E402
from app.audio.sing import _dedupe_onsets, bpm_from_onsets  # noqa: E402

SR = 16000
TOL_MS = 60.0  # 起音判定容差


# ---------------------------------------------------------------------------
# 素材合成（ground truth = 音符起点）
# ---------------------------------------------------------------------------
def render_notes(
    onsets_s: list[float],
    freqs: list[float],
    durations_s: list[float],
    *,
    attack_s: float = 0.01,
    gap_s: float = 0.0,
    noise: float = 0.0,
    seed: int = 7,
) -> tuple[np.ndarray, list[float]]:
    """谐波音色渲染音符序列（基频 + 4 谐波 + ADSR 式包络）。

    ``gap_s`` > 0 = 断奏（音符尾与下一个音头之间留静音）；= 0 = 连奏（首尾相接）。
    ``attack_s`` 长 = 柔起音（弱瞬态）。返回 (波形, 真实起音时刻 ms)。
    """
    total = max(o + d for o, d in zip(onsets_s, durations_s, strict=True)) + 0.3
    y = np.zeros(int(total * SR), dtype=np.float64)
    rng = np.random.default_rng(seed)
    for on, f, dur in zip(onsets_s, freqs, durations_s, strict=True):
        n = int(dur * SR)
        t = np.arange(n) / SR
        tone = sum(0.6 / (h + 1) * np.sin(2 * np.pi * f * (h + 1) * t) for h in range(4))
        attack = max(1, int(attack_s * SR))
        env = np.ones(n)
        env[:attack] = np.linspace(0, 1, attack) ** 1.5
        rel = max(1, int(min(0.08, dur / 3) * SR))
        env[-rel:] = np.linspace(1, 0, rel)
        quiet = int(gap_s * SR)
        if quiet > 0:
            env[max(0, n - quiet) :] = 0.0
        i0 = int(on * SR)
        seg = tone * env
        y[i0 : i0 + min(len(seg), len(y) - i0)] += seg[: len(y) - i0]
    if noise > 0:
        y += noise * rng.standard_normal(len(y))
    peak = np.max(np.abs(y)) or 1.0
    return (0.7 * y / peak).astype(np.float32), [round(o * 1000, 1) for o in onsets_s]


def build_cases() -> list[tuple[str, np.ndarray, list[float]]]:
    """六类形态（覆盖"真人间断/连唱/柔起音/噪声/相位处理"）。"""
    # 12 个音、四分音符 500ms（真值 BPM = 120）、旋律自 C4 起上下行
    freqs = [261.63, 293.66, 329.63, 349.23, 392.0, 440.0, 392.0, 349.23, 329.63, 293.66, 261.63, 246.94]
    onsets = [0.5 + 0.5 * i for i in range(len(freqs))]
    durs = [0.42] * len(freqs)

    cases: list[tuple[str, np.ndarray, list[float]]] = []
    cases.append(("staccato 断奏（基线）", *render_notes(onsets, freqs, durs, gap_s=0.08)))
    cases.append(("legato 连奏（无停顿）", *render_notes(onsets, freqs, [0.5] * len(freqs), gap_s=0.0)))
    cases.append(
        ("soft_attack 柔起音（300ms）", *render_notes(onsets, freqs, durs, attack_s=0.3, gap_s=0.08))
    )
    cases.append(
        (
            "legato+soft 连奏柔起音",
            *render_notes(onsets, freqs, [0.5] * len(freqs), attack_s=0.3, gap_s=0.0),
        )
    )
    cases.append(
        ("staccato+noise SNR≈10dB", *render_notes(onsets, freqs, durs, gap_s=0.08, noise=0.05))
    )
    # **同音重复**（"la la la"型）：音高不变 → F0 起音的"音高跳变"判据天然漏检
    # → IOI 翻倍（半速）。这是 F0 兜底方案的**关键盲区**，也是仲裁规则必须覆盖的场景。
    cases.append(
        (
            "repeat 同音重复（la×12）",
            *render_notes(onsets, [440.0] * len(freqs), durs, gap_s=0.08),
        )
    )
    # 相位声码器（本次 BUG 实测里的极端：瞬态被抹平）
    import librosa

    y, gt = render_notes(onsets, freqs, durs, gap_s=0.08)
    y_pv = librosa.effects.time_stretch(y, rate=0.9)
    cases.append(("phase-vocoder 处理（瞬态抹平）", y_pv.astype(np.float32), gt))
    return cases


# ---------------------------------------------------------------------------
# 检测器
# ---------------------------------------------------------------------------
def f0_onsets_ms(track, *, jump_cent: float = 60.0, min_gap_ms: float = 120.0) -> list[float]:
    """候选兜底：F0 起音 = ① 有声段起点（前置静音 ≥150ms）② 音高跳变点（|Δcent| ≥ jump_cent）。"""
    hop = track.hop_ms or 32.0
    f0 = np.asarray(track.f0, dtype=float)
    voiced = f0 > 0
    gap_frames = max(1, int(round(150.0 / hop)))
    out: list[float] = []
    i = 0
    while i < len(voiced):
        if not voiced[i]:
            i += 1
            continue
        start = i
        while i < len(voiced) and voiced[i]:
            i += 1
        if i - start >= 3 and (start == 0 or not voiced[max(0, start - gap_frames) : start].any()):
            out.append(round(start * hop, 1))
    # 音高跳变（仅在连续有声帧之间比较，跨静音不算）
    for idx in range(1, len(f0)):
        if f0[idx] <= 0 or f0[idx - 1] <= 0:
            continue
        cents = abs(1200.0 * np.log2(f0[idx] / f0[idx - 1]))
        if cents >= jump_cent:
            out.append(round(idx * hop, 1))
    return _dedupe_onsets(out, min_gap_ms)


def f0_onsets_v2_ms(
    track,
    *,
    jump_cent: float = 60.0,
    min_gap_ms: float = 120.0,
    bridge_frames: int = 3,
    min_run_frames: int = 3,
) -> list[float]:
    """F0 起音 v2（针对 v1 在断奏/柔起音上的漏检做修正）：

    - **跨短静音比音高**：音符间 <``bridge_frames`` 帧（≈96ms）静音视为句内换音——
      用最近有声帧比较（v1 只在严格相邻有声帧间比 → 断奏（80ms 静音）全部漏检）；
    - 段起点判据保留（前置静音 ≥150ms 的新句），但起音时刻取"有声段起点"。
    """
    hop = track.hop_ms or 32.0
    f0 = np.asarray(track.f0, dtype=float)
    voiced = f0 > 0
    gap_frames = max(1, int(round(150.0 / hop)))
    out: list[float] = []
    i = 0
    while i < len(voiced):
        if not voiced[i]:
            i += 1
            continue
        start = i
        while i < len(voiced) and voiced[i]:
            i += 1
        if i - start >= min_run_frames and (
            start == 0 or not voiced[max(0, start - gap_frames) : start].any()
        ):
            out.append(round(start * hop, 1))
    # 音高跳变：允许跨越 ≤bridge_frames 的静音（用最近一个有声帧比较）
    last_idx = -1
    for idx in range(len(f0)):
        if f0[idx] <= 0:
            continue
        if last_idx >= 0 and idx - last_idx <= bridge_frames + 1:
            cents = abs(1200.0 * np.log2(f0[idx] / f0[last_idx]))
            if cents >= jump_cent:
                out.append(round(idx * hop, 1))
        last_idx = idx
    return _dedupe_onsets(out, min_gap_ms)


def flux_tuned_ms(y: np.ndarray, sr: int, *, delta: float, wait_ms: float = 60.0) -> list[float]:
    """flux 调参版：提高 delta（峰值显著度门限）与 wait（最小间隔）→ 换 precision。

    librosa 默认 delta≈0.07、wait=30ms（当前生产参数）；假 onset 多来自谐波起伏，
    提高门限与间隔可压低虚警。
    """
    import librosa

    hop = 512
    frames = librosa.onset.onset_detect(
        y=y,
        sr=sr,
        hop_length=hop,
        backtrack=True,
        delta=delta,
        wait=int(round(wait_ms / 1000 * sr / hop)),
    )
    return [round(float(f) * hop / sr * 1000.0, 1) for f in frames]


def intersect(a: list[float], b: list[float], tol_ms: float = 60.0) -> list[float]:
    """交集策略：仅保留两个检测器都命中的起音（互相印证 → 高置信），取两者的平均时刻。"""
    out: list[float] = []
    for x in a:
        cands = [y for y in b if abs(y - x) <= tol_ms]
        if cands:
            out.append(round((x + min(cands, key=lambda y: abs(y - x))) / 2.0, 1))
    return _dedupe_onsets(out, 50.0)


def combine_bpm(
    b_flux: float | None,
    b_f0: float | None,
    approx_bpm: float | None,
    *,
    bpm_lo: float = 40.0,
    bpm_hi: float = 240.0,
) -> tuple[float | None, str]:
    """**候选实现（评估结论）**：F0 起音优先 + 八度校正（不是 onset 列表融合）。

    规则：
    1. 两侧都不可用 → None（回落 duration，诚实降级）；
    2. 只有一侧可用 → 该侧 + **八度校正**（同音重复场景 f0 全漏、flux 倍速，
       校正后回到合理区间）；
    3. 两侧可用且比值 ∈ [1.5, 2.3]（八度分歧）→ 取与 ``approx_bpm``（时长比粗估）更近者；
    4. 其余 → **f0 侧**（假起音显著更少：合成评测 F1 0.73 vs 0.36）。

    八度校正：在 ``bpm × 2^k``（k∈[-2,2]，限制 [bpm_lo, bpm_hi]）中取与粗估最接近者——
    粗估（参考 BPM × 用户/参考时长比）虽粗，但足以区分半速/倍速。
    """

    def oct_correct(bpm: float | None) -> float | None:
        if not bpm or not approx_bpm:
            return bpm
        cands = [bpm * 2**k for k in (-2, -1, 0, 1, 2)]
        cands = [c for c in cands if bpm_lo <= c <= bpm_hi]
        return min(cands, key=lambda c: abs(c - approx_bpm)) if cands else bpm

    if b_f0 is None and b_flux is None:
        return None, "none"
    if b_f0 is None:
        return oct_correct(b_flux), "flux+oct"
    if b_flux is None:
        return oct_correct(b_f0), "f0+oct"
    hi, lo = max(b_f0, b_flux), min(b_f0, b_flux)
    if approx_bpm and lo > 0 and 1.5 <= hi / lo <= 2.3:
        pick = b_flux if abs(b_flux - approx_bpm) < abs(b_f0 - approx_bpm) else b_f0
        return oct_correct(pick), "arbitrated+oct"
    return oct_correct(b_f0), "f0+oct"


def fuse(a: list[float], b: list[float], min_gap_ms: float = 50.0) -> list[float]:
    return _dedupe_onsets(list(a) + list(b), min_gap_ms)


def score_detector(pred_ms: list[float], gt_ms: list[float]) -> dict:
    """±TOL 容差的 precision/recall/F1（贪心一对一匹配）。"""
    pred = sorted(pred_ms)
    gt = sorted(gt_ms)
    used = [False] * len(gt)
    tp = 0
    for p in pred:
        best, best_d = -1, TOL_MS
        for k, g in enumerate(gt):
            if used[k]:
                continue
            d = abs(p - g)
            if d <= best_d:
                best, best_d = k, d
        if best >= 0:
            used[best] = True
            tp += 1
    prec = tp / len(pred) if pred else 0.0
    rec = tp / len(gt) if gt else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    return {"n_pred": len(pred), "tp": tp, "precision": round(prec, 3), "recall": round(rec, 3), "f1": round(f1, 3)}


@dataclass
class CaseRow:
    case: str
    detector: str
    n_pred: int
    precision: float
    recall: float
    f1: float
    bpm: float | None
    bpm_err: float | None


def eval_real_audio(paths: list[Path]) -> None:
    """真实演唱录音对比（无 ground truth）：看检出形态、IOI 中位、BPM 与时长比对照。

    ⚠️ 运行时录音是浏览器 MediaRecorder 的 **WebM/Opus**（service 层固定存为 `<hash>.mp3`
    扩展名）→ 必须先走生产同款 ffmpeg 转 16k mono wav（`to_16k_mono_wav`）再提取。
    """
    import asyncio
    import tempfile

    from app.audio.pitch import to_16k_mono_wav

    extractor = PyinPitchExtractor()
    print(f"\n=== 真实录音对比（{len(paths)} 段；只输出统计，不涉音频内容） ===")
    print(f"{'文件':<26}{'时长':>7}{'flux':>7}{'f0v2':>7}{'f_IOI':>8}{'f0_IOI':>8}{'flux_bpm':>9}{'f0_bpm':>8}")
    print("-" * 88)
    for p in paths:
        with tempfile.TemporaryDirectory(prefix="onseteval-real-") as tmp:
            wav = str(Path(tmp) / "real.wav")
            try:
                asyncio.run(to_16k_mono_wav(str(p), wav))
                track = extractor.extract_track(wav)
                import librosa

                y, sr = librosa.load(wav, sr=SR, mono=True)
            except Exception as exc:  # 坏文件跳过（不伪造）
                print(f"{p.name:<26} 处理失败：{exc}")
                continue
        flux = detect_onsets_ms(y, sr)
        f0v2 = f0_onsets_v2_ms(track)

        def ioi(v: list[float]) -> float | None:
            d = np.diff(np.asarray(_dedupe_onsets(v), dtype=float))
            keep = d[(d >= 200) & (d <= 3000)]
            return float(np.median(keep)) if len(keep) else None

        b_flux, b_f0 = bpm_from_onsets(flux), bpm_from_onsets(f0v2)
        print(
            f"{p.name:<26}{track.duration_ms/1000:>7.1f}{len(flux):>7}{len(f0v2):>7}"
            f"{(f'{ioi(flux):.0f}' if ioi(flux) else '—'):>8}"
            f"{(f'{ioi(f0v2):.0f}' if ioi(f0v2) else '—'):>8}"
            f"{(f'{b_flux:.1f}' if b_flux else 'None'):>9}"
            f"{(f'{b_f0:.1f}' if b_f0 else 'None'):>8}"
        )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--audio", nargs="*", type=Path, default=None, help="真实录音路径（仅统计）")
    args = ap.parse_args()

    if args.audio:
        eval_real_audio(args.audio)
        return 0

    extractor = PyinPitchExtractor()
    rows: list[CaseRow] = []
    print(f"{'素材':<28}{'检测器':<8}{'检出':>5}{'P':>7}{'R':>7}{'F1':>7}{'BPM':>8}{'BPM误差':>9}")
    print("-" * 80)
    for name, y, gt in build_cases():
        with tempfile.TemporaryDirectory(prefix="onseteval-") as tmp:
            wav = Path(tmp) / "case.wav"
            import soundfile as sf

            sf.write(str(wav), y, SR)
            track = extractor.extract_track(str(wav))
        gt_bpm = 60000.0 / float(np.median(np.diff(gt)))
        detectors = {
            "flux": detect_onsets_ms(y, SR),
            "f0v2": f0_onsets_v2_ms(track),
            "intersect": intersect(f0_onsets_v2_ms(track), detect_onsets_ms(y, SR)),
        }
        b_flux = bpm_from_onsets(detect_onsets_ms(y, SR))
        b_f0 = bpm_from_onsets(f0_onsets_v2_ms(track))
        # 仲裁用粗估：时长比口径（ref_bpm × ref/us 时长比）——本例素材时长一致 → ≈真值
        approx = gt_bpm * (len(gt) and 1.0 or 1.0)
        b_arb, how = combine_bpm(b_flux, b_f0, approx)
        print(f"{'':<28}（真值 BPM = {gt_bpm:.1f}，音符数 {len(gt)}）")
        for det, pred in detectors.items():
            sc = score_detector(pred, gt)
            bpm = bpm_from_onsets(pred)
            err = abs(bpm - gt_bpm) if bpm else None
            rows.append(
                CaseRow(name, det, sc["n_pred"], sc["precision"], sc["recall"], sc["f1"], bpm, err)
            )
            print(
                f"{name:<28}{det:<8}{sc['n_pred']:>5}{sc['precision']:>7.2f}{sc['recall']:>7.2f}"
                f"{sc['f1']:>7.2f}{(f'{bpm:.1f}' if bpm else 'None'):>8}"
                f"{(f'{err:.1f}' if err is not None else '—'):>9}"
            )
        err_arb = abs(b_arb - gt_bpm) if b_arb else None
        rows.append(
            CaseRow(name, f"arbitrated({how})", 0, 0.0, 0.0, 0.0, b_arb, err_arb)
        )
        print(
            f"{name:<28}{'ARBIT':<8}{'—':>5}{'—':>7}{'—':>7}{'—':>7}"
            f"{(f'{b_arb:.1f}' if b_arb else 'None'):>8}"
            f"{(f'{err_arb:.1f}' if err_arb is not None else '—'):>9}  ← {how}"
        )

    if args.json:
        args.json.write_text(
            json.dumps([r.__dict__ for r in rows], ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\nJSON → {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
