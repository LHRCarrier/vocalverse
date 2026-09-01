"""POC-3：faster-whisper small int8 CPU RTF 基准试验（docs/18 §1 P3 = ASR 基准试验）。

目的：实测 15s / 60s 音频 RTF（real-time factor），写入 docs/06 §8 延迟表。
判据：RTF ≤0.6 → 演示话术「3~5s」；0.6~0.8 → 「5~8s」；>0.8 → 换 tiny 或演示限 15s 短句。

用法（仓库根，需要模型可下载 + 本机 ffmpeg）：
    uv run --no-project -p 3.12 --with faster-whisper --with soundfile --with numpy --with torch --index-strategy unsafe-best-match \
        python scripts/poc/whisper_rtf.py --audio my_speech15s.wav my_speech60s.wav [--model small --runs 3]
    # 无真实录音时可用 --demo 生成合成语音样例（精度仅供流程验证）
"""

from __future__ import annotations

import argparse
import statistics
import time

import numpy as np

_DEMO_RATE = 16_000


def _make_demo_wav(path: str, seconds: float) -> None:
    """生成一个「伪语音」wav（正弦+噪声叠加），仅供流程/RTF 粗测，不代表真实 RTF。"""
    import soundfile as sf

    t = np.linspace(0, seconds, int(_DEMO_RATE * seconds), endpoint=False)
    # 模拟音节节奏：4Hz 幅度调制 + 基频 150Hz + 谐波
    tone = 0.5 * np.sin(2 * np.pi * 150 * t) + 0.2 * np.sin(2 * np.pi * 300 * t)
    envelope = 0.4 + 0.6 * (np.sin(2 * np.pi * 4 * t) > 0).astype(float)
    wav = (tone * envelope * 0.4 + np.random.default_rng(0).normal(0, 0.01, len(t))).astype(np.float32)
    sf.write(path, wav, _DEMO_RATE)
    print(f"  [demo] 生成 {path} ({seconds}s)")


def run_one(model, audio: np.ndarray, fs: int) -> float:
    """一次转写，返回 RTF。"""
    t0 = time.perf_counter()
    segments, info = model.transcribe(audio, language="en", beam_size=5)
    text = "".join(s.text for s in segments)
    el = time.perf_counter() - t0
    rtf = el / (audio.shape[0] / fs)
    return rtf, el, len(text)


def main() -> None:
    parser = argparse.ArgumentParser(description="whisper small int8 RTF 基准")
    parser.add_argument("--audio", nargs="+", default=[], help="输入音频（wav 16k 或 mp3；ffmpeg 自动转）")
    parser.add_argument("--model", default="small")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--demo", action="store_true", help="生成合成样例并测（仅流程验证）")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--compute-type", default="int8")
    args = parser.parse_args()

    files = list(args.audio)
    if args.demo:
        _make_demo_wav("scripts/poc/tmp_demo_15s.wav", 15.0)
        _make_demo_wav("scripts/poc/tmp_demo_60s.wav", 60.0)
        files += ["scripts/poc/tmp_demo_15s.wav", "scripts/poc/tmp_demo_60s.wav"]
    if not files:
        parser.error("需要 --audio 或 --demo")

    from faster_whisper import WhisperModel  # 延迟导入（重依赖）

    print(f"加载模型 {args.model} ({args.compute_type}) ...")
    t0 = time.perf_counter()
    model = WhisperModel(args.model, device=args.device, compute_type=args.compute_type)
    print(f"  加载 {time.perf_counter() - t0:.1f}s（首批含下载；后续用 HF 缓存挂卷）")

    results: list[tuple[str, float, float, int]] = []
    for f in files:
        rtf_sample: list[float] = []
        for i in range(args.runs):
            rtf, el, chars = run_one(model, f)
            rtf_sample.append(rtf)
            print(f"  {f} run[{i}] rtf={rtf:.3f} ({el:.2f}s, {chars} chars)")
        # 统一 fs 假设：真实音频多文件时以各自时长计（此处 rtf 已按各自时长归一）
        results.append((f, statistics.mean(rtf_sample), max(rtf_sample), len(f)))
        print(f"  {f} → mean_rtf={statistics.mean(rtf_sample):.3f} max={max(rtf_sample):.3f}")

    worst = max(r[1] for r in results)
    print(f"\n== 判定（最差 mean_rtf={worst:.3f}）==")
    if worst <= 0.6:
        print("PASS → 演示话术「录音后 3~5s 反馈」，写入 docs/06 §8")
    elif worst <= 0.8:
        print("PASS(降级) → 演示话术「5~8s」，写入 docs/06 §8")
    else:
        print("FAIL → 换 tiny 或演示限 ≤15s 短句；写入 docs/06 §8")


if __name__ == "__main__":
    main()
