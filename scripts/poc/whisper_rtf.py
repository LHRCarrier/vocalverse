"""POC-3：faster-whisper small int8 CPU RTF 基准试验（docs/18 §1 P3 = ASR 基准试验）。

目的：实测 15s / 60s 音频 RTF（real-time factor），写入 docs/06 §8 延迟表。
判据：RTF ≤0.6 → 演示话术「3~5s」；0.6~0.8 → 「5~8s」；>0.8 → 换 tiny 或演示限 15s 短句。

音频来源（本脚本内置两步）：
1. `--speech` 开关：用 edge-tts 合成 15s/60s 英文朗读语音（合成语音近似真人语音节奏，
   供 RTF 量级判定；纯正弦/噪声不属于语音，RTF 无意义——故不用 --demo）；
2. 或直接 `--audio a.mp3 b.wav`（faster-whisper 自带解码（PyAV），无需 ffmpeg）。

用法（仓库根）：
    uv run --no-project -p 3.12 --with faster-whisper --with edge-tts \
        python scripts/poc/whisper_rtf.py --speech [--model small --runs 3]
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import time
from pathlib import Path

import edge_tts

OUT_DIR = Path("scripts/poc")
TTS_VOICE = "en-US-JennyNeural"


async def synthesize_duration(target_s: int) -> bytes:
    """合成约 target_s 的英文朗读音频（句子拼接后按句合成）。"""
    sentences = [
        "Good morning everyone. Today I would like to talk about my research project, "
        "which focuses on using artificial intelligence to help people practice speaking "
        "English. Our system listens to your voice, scores your pronunciation, and gives "
        "you friendly feedback after every sentence. We also designed a special metric "
        "called language point coverage, which shows whether you naturally used the "
        "expressions from this lesson. In our experiments, learners who practiced with "
        "the system made noticeable progress in just two weeks. Thank you for listening, "
        "and I am happy to answer your questions.",
    ]
    chunks = []
    for _ in range(20):
        chunks.append(await edge_tts.Communicate(" ".join(sentences), TTS_VOICE).save(None))
    # 拼接直到覆盖目标时长（估算：朗读 ≈150 wpm → 15s≈37 词 / 60s≈150 词；按句累计更稳）
    parts: list[bytes] = []
    total_ms = 0.0
    for _ in range(30):
        data = next(iter(chunks)) if chunks else b""
        # 度量时长：逐句 streaming 统计平均时长
        buf = b""
        async for chunk in edge_tts.Communicate(" ".join(sentences[:2]), TTS_VOICE).stream():
            if chunk["type"] == "audio":
                buf += chunk["data"]
        parts.append(buf)
        if len(parts) % 4 == 0:
            # 粗估：每句 ~8s → 4 句 ≈32s；用句数折半镜像时长（脚本便捷估算）
            pass
        total_ms = len(parts) * 8.0
        if total_ms >= target_s:
            break
    # 简化：不精确计时，产出约 target_s（目测 1 句 ≈8s，60s ≈7~8 句）
    return b"".join(parts)


def run_one(model, path: str) -> tuple[float, float, int]:
    """一次转写（path 支持 mp3/wav；Fast-Whisper 内部解码），返回 (rtf, elapsed, chars)。"""
    import av

    duration_s = _probe_duration(path)
    t0 = time.perf_counter()
    segments, info = model.transcribe(path, language="en", beam_size=5)
    text = "".join(s.text for s in segments)
    el = time.perf_counter() - t0
    return el / duration_s, el, len(text)


def _probe_duration(path: str) -> float:
    import av

    container = av.open(path)
    stream = container.streams.audio[0]
    seconds = float(stream.duration * stream.time_base) if stream.duration else 1.0
    container.close()
    return seconds if seconds > 0 else 1.0


async def gen_speech_files() -> list[str]:
    """生成 15s 与 60s 语音 mp3（按句配平：2 句≈16s、8 句≈60s）。"""
    base = (
        "Good morning everyone. Today I would like to talk about my research project, "
        "which focuses on using artificial intelligence to help people practice speaking "
        "English. "
    )
    mid = (
        "Our system listens to your voice, scores your pronunciation, and gives you "
        "friendly feedback after every sentence. We also designed a special metric called "
        "language point coverage, which shows whether you naturally used the expressions "
        "from this lesson. "
    )
    end = (
        "In our experiments, learners who practiced with the system made noticeable "
        "progress in just two weeks. Thank you for listening, and I am happy to answer "
        "your questions. "
    )
    short = base + mid
    long_ = (base + mid + end) * 3
    out: list[str] = []
    for name, script in (("poc_speech_15s.mp3", short), ("poc_speech_60s.mp3", long_)):
        path = OUT_DIR / name
        await edge_tts.Communicate(script, TTS_VOICE).save(str(path))
        out.append(str(path))
        print(f"  [speech] 生成 {path}")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="whisper small int8 RTF 基准")
    parser.add_argument("--audio", nargs="+", default=[], help="输入音频（mp3/wav；内部解码无需 ffmpeg）")
    parser.add_argument("--speech", action="store_true", help="用 edge-tts 合成 15s/60s 语音后测试")
    parser.add_argument("--model", default="small")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--compute-type", default="int8")
    args = parser.parse_args()

    files = list(args.audio)
    if args.speech:
        files = asyncio.run(gen_speech_files())
    if not files:
        parser.error("需要 --audio 或 --speech")

    from faster_whisper import WhisperModel  # 延迟导入（重依赖，不装 torch）

    print(f"加载模型 {args.model} ({args.compute_type}) ...")
    t0 = time.perf_counter()
    model = WhisperModel(args.model, device=args.device, compute_type=args.compute_type)
    print(f"  加载 {time.perf_counter() - t0:.1f}s（首批含下载；后续用 HF 缓存挂卷）")

    results: list[tuple[str, float, float]] = []
    for f in files:
        samples: list[float] = []
        for i in range(args.runs):
            rtf, el, chars = run_one(model, f)
            samples.append(rtf)
            print(f"  {f} run[{i}] rtf={rtf:.3f} ({el:.2f}s, {chars} chars)")
        results.append((f, statistics.mean(samples), max(samples)))
        print(f"  {f} -> mean_rtf={statistics.mean(samples):.3f} max={max(samples):.3f}")

    worst = max(r[1] for r in results)
    print(f"\n== 判定（最差 mean_rtf={worst:.3f}）==")
    if worst <= 0.6:
        print("PASS -> 演示话术「录音后 3~5s 反馈」，写入 docs/06 §8")
    elif worst <= 0.8:
        print("PASS(降级) -> 演示话术「5~8s」，写入 docs/06 §8")
    else:
        print("FAIL -> 换 tiny 或演示限 <=15s 短句；写入 docs/06 §8")


if __name__ == "__main__":
    main()
