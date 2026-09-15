#!/usr/bin/env python3
"""语音链路分阶段基准脚本（va-09：答辩证据「录音后 3~5s 反馈」）。

分阶段计时（与真实 /turns 热路径同源）：upload → ffmpeg → ASR(words) → LLM ttfa →
TTS 首声 → 排播（全链路），输出每阶段 mean / p50 / p95 / RTF 与峰值内存（tracemalloc），
并按操作数预算（STAGE_BUDGETS）给出 PASS/FAIL；``--check-budget`` 超预算退出码 1
（python-ci 门禁：--fake 冒烟跑，零真实 Key/模型，不触外部服务）。

用法（真实基准，取答辩证据；在 services/python 下用项目环境执行）::

    uv run python ../../scripts/bench/pipeline_bench.py --speech --runs 3 --check-budget
    uv run python ../../scripts/bench/pipeline_bench.py --audio path/to/15s.mp3 --runs 5

CI / 冒烟（Fake 客户端，零模型零 Key；ffmpeg 阶段用 stdlib 生成的 1s 静音 wav 走真实二进制）::

    uv run python ../../scripts/bench/pipeline_bench.py --fake --runs 3 --check-budget

判定口径（docs/06 §8 延迟表 + POC-1）：RTF≤0.6 → 演示话术「3~5s 反馈」；0.6~0.8 → 「5~8s」。
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import io
import os
import shutil
import statistics
import sys
import tempfile
import time
import tracemalloc
import wave
from pathlib import Path

# 使 app.* 可导入：脚本位于 scripts/bench/，services/python 在 parents[2]/services/python
_SERVICE_DIR = Path(__file__).resolve().parents[2] / "services" / "python"
if str(_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICE_DIR))

from app.audio.ffmpeg_utils import ffmpeg_bin, run_ffmpeg  # noqa: E402
from app.audio.textproc.sentence_splitter import StreamSentenceSplitter  # noqa: E402
from app.audio.tts import mp3_duration_seconds  # noqa: E402

with contextlib.suppress(Exception):  # Windows cp936 控制台：中文输出可读（失败不影响运行）
    sys.stdout.reconfigure(encoding="utf-8")

# 每阶段操作数 / 墙钟预算（va-09：CI 门禁 + 答辩判定基准；turn 预算按 ~5s 短句口径）
STAGE_BUDGETS: dict[str, dict[str, float | int]] = {
    "upload": {"ops": 1, "max_s": 0.5},
    "ffmpeg": {"ops": 1, "max_s": 3.0},
    "asr": {"ops": 1, "max_s": 9.0, "rtf_max": 0.6},
    "llm_ttfa": {"ops": 1, "max_s": 3.0},
    "tts": {"ops": 1, "max_s": 3.0},
    "turn": {"ops": 1, "max_s": 8.0},
}

SPEECH_TEXT = "Good morning! I would like to order a large coffee, please. Thank you very much."


def _make_silence_wav(seconds: float = 1.0, rate: int = 16000) -> bytes:
    """stdlib 生成 1s 16k mono 静音 wav（CI 冒烟给 ffmpeg 阶段一个真实输入）。"""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(rate * seconds))
    return buf.getvalue()


def _has_ffmpeg() -> bool:
    try:
        return shutil.which(ffmpeg_bin()) is not None
    except Exception:
        return False


# ── 阶段实现（返回 (elapsed_s, 附加指标 dict)）──────────────────────────────────


async def stage_upload(data: bytes) -> tuple[float, dict]:
    """upload：字节接收/尺寸校验（真实路由等价动作；不落盘）。"""
    t0 = time.perf_counter()
    if not data:
        raise ValueError("empty audio")
    return time.perf_counter() - t0, {"bytes": len(data)}


async def stage_ffmpeg(src_bytes: bytes) -> tuple[float, dict, Path | None]:
    """ffmpeg：tmp 输入 → 16k mono wav（run_ffmpeg 同源护栏；无二进制则跳过）。"""
    if not _has_ffmpeg():
        return 0.0, {"skipped": "no ffmpeg binary"}, None
    tmp = _SERVICE_DIR / "data" / "audio" / "bench_tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    fd, src_path = tempfile.mkstemp(suffix=".in", dir=str(tmp))
    with os.fdopen(fd, "wb") as f:
        f.write(src_bytes)
    wav_path = src_path + ".wav"
    try:
        t0 = time.perf_counter()
        await run_ffmpeg(
            ["-y", "-i", src_path, "-ar", "16000", "-ac", "1", "-f", "wav", wav_path],
            timeout_s=15.0,
        )
        el = time.perf_counter() - t0
    finally:
        Path(src_path).unlink(missing_ok=True)
    return el, {"wav": str(wav_path)}, Path(wav_path)


async def stage_asr(client, wav_path: Path | None, audio_bytes: bytes) -> tuple[float, dict]:
    """ASR(words)：真实客户端走 transcribe_sync（纯模型推理，wav 由 ffmpeg 阶段产出）；
    Fake 客户端走 transcribe（忽略字节）。"""
    t0 = time.perf_counter()
    if hasattr(client, "transcribe_sync") and wav_path is not None:
        result = await asyncio.to_thread(client.transcribe_sync, str(wav_path), "en")
    else:
        result = await client.transcribe(audio_bytes, "en")
    el = time.perf_counter() - t0
    dur = float(result.duration or 0.0)
    return el, {"rtf": el / dur if dur > 0 else 0.0, "words": len(result.words), "dur": dur}


async def stage_llm_ttfa(client, messages: list[dict[str, str]]) -> tuple[float, dict]:
    """LLM ttfa：流式首 token 时延 + 总时延。"""
    t0 = time.perf_counter()
    first: float | None = None
    nchars = 0
    async for kind, payload in client.stream_rich(messages, temperature=0.6, max_tokens=256):
        if kind != "delta":
            continue
        if first is None:
            first = time.perf_counter() - t0
        nchars += len(payload)
    total = time.perf_counter() - t0
    return total, {"ttfa": first if first is not None else total, "chars": nchars}


async def stage_tts(client, text: str) -> tuple[float, dict]:
    """TTS 首声/单句：合成时延 + 音频时长（MP3 帧头估算）。"""
    t0 = time.perf_counter()
    data = await client.synthesize(text)
    el = time.perf_counter() - t0
    dur = mp3_duration_seconds(data) or 0.0
    return el, {"audio_s": dur, "bytes": len(data)}


async def stage_turn(
    asr, llm, tts, wav_path: Path | None, audio_bytes: bytes
) -> tuple[float, dict]:
    """排播全链路：ASR → LLM 流式（ttfa）→ 分句 → 逐句 TTS（并发）。"""
    t0 = time.perf_counter()
    if hasattr(asr, "transcribe_sync") and wav_path is not None:
        result = await asyncio.to_thread(asr.transcribe_sync, str(wav_path), "en")
    else:
        result = await asr.transcribe(audio_bytes, "en")
    asr_s = time.perf_counter() - t0

    llm_t0 = time.perf_counter()
    messages = [
        {
            "role": "system",
            "content": "You are a friendly English tutor. Reply in one or two short sentences.",
        },
        {"role": "user", "content": result.text or "I would like a coffee, please."},
    ]
    reply = ""
    first_delta: float | None = None
    splitter = StreamSentenceSplitter()
    sentences: list[str] = []
    async for kind, payload in llm.stream_rich(messages, temperature=0.6, max_tokens=256):
        if kind != "delta":
            continue
        if first_delta is None:
            first_delta = time.perf_counter() - llm_t0
        reply += payload
        sentences.extend(splitter.push(payload))
    sentences.extend(splitter.flush())
    llm_s = time.perf_counter() - llm_t0

    if not sentences:
        sentences = [reply.strip()] if reply.strip() else ["OK."]

    tts_t0 = time.perf_counter()
    audios = await asyncio.gather(*(tts.synthesize(s) for s in sentences))
    tts_s = time.perf_counter() - tts_t0
    total = time.perf_counter() - t0
    return total, {
        "asr_s": asr_s,
        "llm_s": llm_s,
        "ttfa": first_delta if first_delta is not None else llm_s,
        "tts_s": tts_s,
        "sentences": len(sentences),
        "audio_bytes": sum(len(a) for a in audios),
    }


# ── 客户端装配 ────────────────────────────────────────────────────────────────


def _build_clients(fake: bool, model: str, device: str, compute_type: str):
    if fake:
        from app.audio.stubs import FakeASRClient, FakeLLMClient, FakeTTSClient

        return FakeASRClient(), FakeLLMClient(), FakeTTSClient()
    from app.audio.asr import FasterWhisperClient
    from app.audio.llm import DeepSeekLLMClient
    from app.audio.tts import EdgeTTSClient
    from app.core.config import get_settings

    settings = get_settings()
    asr = FasterWhisperClient(model=model, device=device, compute_type=compute_type)
    llm = DeepSeekLLMClient(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_model,
    )
    tts = EdgeTTSClient(voice=settings.tts_voice, rate=settings.tts_rate)
    return asr, llm, tts


async def _load_audio(args, fake: bool) -> tuple[bytes, Path | None, str]:
    """返回 (audio_bytes, wav_path_or_None, source_desc)。"""
    if fake:
        return _make_silence_wav(1.0), None, "fake-1s-silence"
    if args.audio:
        p = Path(args.audio)
        return p.read_bytes(), None, f"audio:{p.name}"
    if args.speech:
        import edge_tts

        communicate = edge_tts.Communicate(SPEECH_TEXT, "en-US-JennyNeural")
        buf = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                buf.write(chunk["data"])
        data = buf.getvalue()
        return data, None, "speech-edge-tts"
    raise SystemExit("需要 --audio、--speech 或 --fake（真实基准请用 --speech 生成 ~5s 语音）")


def _pct(samples: list[float], p: float) -> float:
    return (
        statistics.quantiles(samples, n=100, method="inclusive")[int(p) - 1]
        if len(samples) > 1
        else (samples[0] if samples else 0.0)
    )


def _fmt(samples: list[float]) -> str:
    if not samples:
        return "—"
    mean = statistics.mean(samples)
    return f"mean={mean:.3f}s p50={_pct(samples, 50):.3f}s p95={_pct(samples, 95):.3f}s"


async def run_bench(args) -> int:
    fake = args.fake
    asr, llm, tts = _build_clients(fake, args.model, args.device, args.compute_type)
    audio_bytes, _, src = await _load_audio(args, fake)

    if not fake and args.speech is False and args.audio is None:
        raise SystemExit("真实基准需 --speech 或 --audio")

    print(
        f"[bench] 输入: {src} | runs={args.runs} | fake={fake} | "
        f"model={args.model}/{args.compute_type}"
    )
    print("[bench] 分阶段: upload → ffmpeg → ASR(words) → LLM ttfa → TTS 首声 → 排播")

    stage_samples: dict[str, list[float]] = {k: [] for k in STAGE_BUDGETS}
    stage_meta: dict[str, dict] = {k: {} for k in STAGE_BUDGETS}
    ops: dict[str, int] = {k: 0 for k in STAGE_BUDGETS}
    tracemalloc.start()

    for _ in range(args.runs):
        el, meta = await stage_upload(audio_bytes)
        stage_samples["upload"].append(el)
        ops["upload"] += 1

        el, meta, wav = await stage_ffmpeg(audio_bytes)
        if meta.get("skipped"):
            stage_samples["ffmpeg"].append(0.0)
            stage_meta["ffmpeg"] = meta
        else:
            stage_samples["ffmpeg"].append(el)
            ops["ffmpeg"] += 1

        el, meta = await stage_asr(asr, wav, audio_bytes)
        stage_samples["asr"].append(el)
        stage_meta["asr"] = meta
        ops["asr"] += 1

        messages = [
            {
                "role": "system",
                "content": "You are a friendly English tutor. Reply in one short sentence.",
            },
            {"role": "user", "content": "I would like to order a large coffee, please."},
        ]
        el, meta = await stage_llm_ttfa(llm, messages)
        stage_samples["llm_ttfa"].append(el)
        stage_meta["llm_ttfa"] = meta
        ops["llm_ttfa"] += 1

        el, meta = await stage_tts(tts, "Of course! Here is your coffee.")
        stage_samples["tts"].append(el)
        stage_meta["tts"] = meta
        ops["tts"] += 1

        el, meta = await stage_turn(asr, llm, tts, wav, audio_bytes)
        stage_samples["turn"].append(el)
        stage_meta["turn"] = meta
        ops["turn"] += 1

        if wav is not None:
            Path(wav).unlink(missing_ok=True)

    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    print("\n== 分阶段结果 ==")
    for name in STAGE_BUDGETS:
        samples = stage_samples[name]
        meta = stage_meta[name]
        line = f"{name:<10} {_fmt(samples)}  ops={ops[name]}"
        if name == "asr" and meta.get("rtf") is not None:
            line += f"  rtf={meta['rtf']:.3f} words={meta.get('words', 0)}"
        if name == "llm_ttfa" and meta.get("ttfa") is not None:
            line += f"  ttfa={meta['ttfa']:.3f}s chars={meta.get('chars', 0)}"
        if name == "tts" and meta.get("audio_s"):
            line += f"  audio={meta['audio_s']:.2f}s"
        if name == "turn" and meta:
            line += (
                f"  (asr={meta.get('asr_s', 0):.2f} llm={meta.get('llm_s', 0):.2f} "
                f"tts={meta.get('tts_s', 0):.2f} n={meta.get('sentences', 0)})"
            )
        print(line)

    print(f"\n峰值内存 (tracemalloc): {peak / 1024 / 1024:.1f} MiB")

    # 预算判定
    violations: list[str] = []
    for name, budget in STAGE_BUDGETS.items():
        samples = stage_samples[name]
        if not samples:
            continue
        mean = statistics.mean(samples)
        if mean > float(budget["max_s"]):
            violations.append(f"{name}: mean={mean:.2f}s > budget {budget['max_s']}s")
        if (
            name == "asr"
            and stage_meta["asr"].get("rtf") is not None
            and stage_meta["asr"]["rtf"] > float(budget["rtf_max"])
        ):
            violations.append(
                f"asr: rtf={stage_meta['asr']['rtf']:.3f} > {budget['rtf_max']}"
                "（演示话术需「3~5s 反馈」）"
            )

    print("\n== 预算判定 ==")
    if violations:
        for v in violations:
            print(f"  FAIL: {v}")
        print("结果: 不通过（超出操作数/时延预算）")
        return 1
    print("结果: 通过（各阶段均在预算内）")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="语音链路分阶段基准（va-09）")
    parser.add_argument("--runs", type=int, default=3, help="每阶段重复次数（默认 3）")
    parser.add_argument("--audio", default="", help="输入音频文件（mp3/wav）")
    parser.add_argument("--speech", action="store_true", help="用 edge-tts 合成 ~5s 英文语音")
    parser.add_argument("--fake", action="store_true", help="Fake 客户端（CI 冒烟，零模型零 Key）")
    parser.add_argument("--model", default="small")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--compute-type", default="int8")
    parser.add_argument("--check-budget", action="store_true", help="超预算退出码 1（CI 门禁）")
    args = parser.parse_args()
    rc = asyncio.run(run_bench(args))
    return rc if (args.check_budget or rc == 1) else 0


if __name__ == "__main__":
    sys.exit(main())
