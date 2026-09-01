"""POC-2：DeepSeek 流式 + `[-META-]` 尾部标记块稳定性实测（docs/18 §1 P2）。

目的：判定「一次流式调用输出回复文本 + 尾部 META 标记」方案是否成立。
判据：20 次调用，META JSON 解析成功率 ≥90% 且流式文本完整 → 一次调用方案；
     否则回退两调用（流式 reply + 后置小 JSON），限流提至 60/h。

用法（仓库根，需 .env 或环境变量 DEEPSEEK_API_KEY）：
    uv run --no-project -p 3.12 --with httpx python scripts/poc/deepseek_meta.py
"""

from __future__ import annotations

import json
import os
import statistics
import sys
import time

import httpx

BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
RUNS = 20

SYSTEM = (
    "You are a friendly cafe barista role-playing in a language learning app. "
    "Answer in 2 short English sentences (max 3). "
    "Then output exactly one final line starting with [-META-] followed by a JSON object: "
    "{\"grammar\":{\"score\":0,\"errors\":[]},\"coach_note\":\"...\","
    "\"corpus_hits\":[\"I would like a latte, please\"],\"difficulty_delta\":0,\"conclude\":false}"
)

USER = "hi, I would like a latte, please."


def extract_meta(text: str) -> tuple[str | None, dict | None]:
    """从流式文本末尾提取 [-META-] 标记块；异常返回 (reply, None)。"""
    marker = "[-META-]"
    idx = text.rfind(marker)
    if idx < 0:
        return text, None
    reply = text[:idx].strip()
    raw = text[idx + len(marker):].strip()
    try:
        return reply, json.loads(raw)
    except json.JSONDecodeError:
        return reply, None


async def main() -> None:
    key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("APP_DEEPSEEK_API_KEY", "")
    if not key:
        print("未设置 DEEPSEEK_API_KEY —— 仅做离线语法自检（extract_meta）后退出")
        ok, meta = extract_meta('hello [-META-]{"conclude":false}')
        assert ok == "hello" and meta == {"conclude": False}
        print("extract_meta 自检 OK")
        return

    first_tokens: list[float] = []
    totals: list[float] = []
    meta_ok = 0
    text_ok = 0
    for i in range(RUNS):
        t0 = time.perf_counter()
        reply_buf: list[str] = []
        got_first = False
        first_at = 0.0
        async with httpx.AsyncClient(timeout=60) as client:
            async with client.stream(
                "POST",
                f"{BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={
                    "model": MODEL,
                    "stream": True,
                    "temperature": 0.6,
                    "messages": [
                        {"role": "system", "content": SYSTEM},
                        {"role": "user", "content": USER},
                    ],
                },
            ) as resp:
                if resp.status_code != 200:
                    print(f"  run[{i}] HTTP {resp.status_code}: {await resp.aread()[:300]}")
                    continue
                async for line in resp.aiter_lines():
                    if not got_first:
                        got_first = True
                        first_at = time.perf_counter() - t0
                    if line.startswith("data: "):
                        payload = line[6:]
                        if payload.strip() == "[DONE]":
                            break
                        try:
                            chunk = json.loads(payload)
                            delta = chunk["choices"][0]["delta"].get("content", "")
                            if delta:
                                reply_buf.append(delta)
                        except (json.JSONDecodeError, KeyError, IndexError):
                            pass
        first_tokens.append(first_at)
        totals.append(time.perf_counter() - t0)
        full = "".join(reply_buf)
        _, meta = extract_meta(full)
        if meta is not None:
            meta_ok += 1
        if "[-META-]" in full:
            text_ok += 1
        print(
            f"  run[{i}] first_token={first_at:.2f}s total={totals[-1]:.2f}s "
            f"chars={len(full)} meta={'OK' if meta else 'MISS'}"
        )

    if not totals:
        print("全部失败 —— 检查 key/网络")
        sys.exit(1)
    rate = meta_ok / len(totals) * 100
    print(
        f"\n-- 统计: first_token mean={statistics.mean(first_tokens):.2f}s "
        f"(n={len(first_tokens)}), total mean={statistics.mean(totals):.2f}s"
        f"\n-- META 解析成功率: {meta_ok}/{len(totals)} = {rate:.0f}%"
        f" (标记出现率 {text_ok}/{len(totals)} = {text_ok / len(totals) * 100:.0f}%)"
    )
    print("== 判定 ==")
    if rate >= 90:
        print("PASS → 一次调用方案成立（docs/18 §1）")
    else:
        print("FAIL → 回退两调用方案 + 限流 60/h 登记 docs/06 §7")


if __name__ == "__main__":
    asyncio_main = main
    # 兼容无 async main 环境
    import asyncio as _asyncio

    _asyncio.run(asyncio_main())
