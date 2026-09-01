"""POC-1：edge-tts 逐句合成延迟实测（docs/18 §1 P1）。

目的：判定「按句流式 TTS + 首句立即启动」方案是否成立。
判据：单句 ≤1s 且 3 句串行均摊 ≤0.85s → 方案成立；否则 → 开场/常用句预合成 + 首句预热。

用法（仓库根）：
    uv run --no-project -p 3.12 --with edge-tts python scripts/poc/edge_tts_latency.py
"""

from __future__ import annotations

import asyncio
import statistics
import time

import edge_tts

VOICE = "en-US-JennyNeural"
SENTENCES = [
    "Hi there, welcome to our cafe! What can I get for you today?",
    "I would like a medium latte with oat milk, please.",
    "Sure, that will be four dollars and fifty cents.",
]
RUNS = 10
OUT_MP3 = "scripts/poc/out_edge_tts_sample.mp3"


async def synth_one(text: str) -> tuple[float, bytes]:
    """返回 (耗时 s, 音频 bytes)。"""
    t0 = time.perf_counter()
    communicate = edge_tts.Communicate(text, VOICE)
    chunks = []
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            chunks.append(chunk["data"])
    el = time.perf_counter() - t0
    return el, b"".join(chunks)


async def main() -> None:
    print(f"voice={VOICE} runs={RUNS} warmup=1")
    # warmup（连接池/首包）
    await synth_one(SENTENCES[0])

    single: list[float] = []
    for i in range(RUNS):
        el, audio = await synth_one(SENTENCES[0])
        single.append(el)
        print(f"  single[{i}] {el:.3f}s  ({len(audio)} bytes)")
    print(
        f"-- single句: mean={statistics.mean(single):.3f}s "
        f"p50={statistics.median(single):.3f}s max={max(single):.3f}s"
    )

    serially: list[float] = []
    for i in range(RUNS):
        t0 = time.perf_counter()
        for s in SENTENCES:
            await synth_one(s)
        serially.append(time.perf_counter() - t0)
    print(
        f"-- 3句串行: mean={statistics.mean(serially):.3f}s max={max(serially):.3f}s "
        f"(每句均摊 {statistics.mean(serially) / 3:.3f}s)"
    )

    # 输出一条样例 mp3（供人工听感/后续 whisper RTF POC 复用）
    _, audio = await synth_one(" ".join(SENTENCES))
    with open(OUT_MP3, "wb") as f:
        f.write(audio)
    print(f"-- 样例已存 {OUT_MP3}")

    verdict_single = "PASS" if statistics.mean(single) <= 1.0 else "FAIL"
    verdict_serial = "PASS" if statistics.mean(serially) / 3 <= 0.85 else "FAIL"
    print(
        f"\n== 判定 ==\n单句 mean {statistics.mean(single):.3f}s → {verdict_single}"
        f"\n3 句串行均摊 {statistics.mean(serially) / 3:.3f}s → {verdict_serial}"
        "\n结论写入 docs/06 §8（按 docs/18 §1 回退规则）"
    )


if __name__ == "__main__":
    asyncio.run(main())
