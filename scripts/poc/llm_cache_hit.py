"""POC：DeepSeek 前缀缓存命中率实测（docs/24 §1-A3 · docs/26 P0 ⑤）。

目的：论证「静态块逐字稳定 → 自动前缀缓存命中（prompt_cache_hit_tokens）」成立。
- 机制：DeepSeek 上下文缓存自动开启、无需参数，按请求前缀 token 匹配（官方 news0802）；
- 场景：固定 system（模拟 ContextBuilder 静态块）+ 每轮变化的 user 消息（模拟动态尾）
  × 5 次非流式调用；第 1 次必 MISS，第 2 次起统计命中占比；
- 判据：第 2 次起 prompt_cache_hit_tokens > 0 即「机制成立」；回写 docs/26 §8 与本文档。

用法（仓库根，.env 的 DEEPSEEK_API_KEY 或环境变量）：
    uv run --no-project -p 3.12 --with httpx --with python-dotenv python scripts/poc/llm_cache_hit.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx

BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
RUNS = 5

# 静态块（模拟 ContextBuilder 的 DYNAMIC_MARKER 之前部分）
SYSTEM_STATIC = (
    "You are a friendly cafe barista role-playing in a language learning app. "
    "Answer in 2 short English sentences (max 3). "
    "If the conversation reached the limit or user ends, set conclude=true. "
    "Output contract: reply as plain English text ONLY, then finish with a single line: "
    "[-META-]{}"
)

# 每轮变化的 user 消息（模拟动态尾：hit/miss 分界）
USER_TURNS = [
    "hi, I would like a latte, please.",
    "and a croissant, thanks",
    "what's the price?",
    "thanks, how long will it take?",
    "ok, can I pay by card?",
]


def load_key() -> str:
    """读 .env（仓库根或 services/python/）或环境变量（docs/24 A 官 F06：deepseek_meta.py
    不读 .env，本脚本修正；app 侧配置对应 APP_DEEPSEEK_API_KEY，见 config.py）。"""
    candidates = [
        Path(__file__).resolve().parents[2] / ".env",  # 仓库根
        Path(__file__).resolve().parents[2] / "services" / "python" / ".env",
    ]
    try:
        from dotenv import load_dotenv

        for path in candidates:
            if path.exists():
                load_dotenv(path)
    except Exception:  # python-dotenv 不可用时依赖 shell 环境
        pass
    return os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("APP_DEEPSEEK_API_KEY", "")


async def main() -> None:
    key = load_key()
    if not key:
        print("未设置 DEEPSEEK_API_KEY —— 跳过实跑（真 Key 就绪后运行本脚本并回写结果）")
        return

    hit_tokens: list[int] = []
    miss_tokens: list[int] = []
    for i in range(RUNS):
        messages = [
            {"role": "system", "content": SYSTEM_STATIC + "\n── DYNAMIC BEGIN ── (poc placeholder)"},
            {"role": "user", "content": USER_TURNS[i % len(USER_TURNS)]},
        ]
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": MODEL, "temperature": 0.6, "max_tokens": 32, "messages": messages},
            )
        if resp.status_code != 200:
            print(f"  run[{i}] HTTP {resp.status_code}: {resp.text[:200]}")
            continue
        data = resp.json()
        usage = data.get("usage") or {}
        hit = usage.get("prompt_cache_hit_tokens")
        miss = usage.get("prompt_cache_miss_tokens")
        if hit is None or miss is None:
            print(
                f"  run[{i}] usage 字段缺失（hit/miss 为 None）：{json.dumps(usage, ensure_ascii=False)[:200]}"
                " —— 请确认模型/端点支持缓存字段"
            )
            continue
        hit_tokens.append(int(hit))
        miss_tokens.append(int(miss))
        print(f"  run[{i}] hit={hit} miss={miss}（{'MISS' if i == 0 else 'HIT' if hit else 'NO-CACHE'}）")

    if not hit_tokens:
        print("无有效采样 —— 检查 key/网络/缓存字段")
        sys.exit(1)
    total_hit = sum(hit_tokens)
    total = sum(hit_tokens) + sum(miss_tokens)
    ratio = total_hit / total * 100 if total else 0.0
    print(
        f"\n-- 统计({len(hit_tokens)} 次): hit 总 {total_hit} / miss 总 {sum(miss_tokens)}"
        f" / 命中占比 {ratio:.1f}%\n"
        f"   第 2 次起命中: {[h for h in hit_tokens[1:]]}"
    )
    print("== 判定 ==")
    if any(h > 0 for h in hit_tokens[1:]):
        print("PASS → 前缀缓存机制成立（静态块逐字稳定策略有效）")
    else:
        print("NO-CACHE → 前缀未命中：核查静态块是否真的逐字稳定 / 模型与端点是否支持缓存")


if __name__ == "__main__":
    import asyncio as _asyncio

    _asyncio.run(main())
