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

import os
from pathlib import Path

import httpx

BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

# 静态块（模拟 ContextBuilder 的 DYNAMIC_MARKER 之前部分）
SYSTEM_STATIC = (
    "You are a friendly cafe barista role-playing in a language learning app. "
    "Answer in 2 short English sentences (max 3). "
    "If the conversation reached the limit or user ends, set conclude=true. "
    "Output contract: reply as plain English text ONLY, then finish with a single line: "
    "[-META-]{}"
)


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

    # 判据（官方 kv_cache 指南）：缓存按「完整匹配缓存前缀单元」命中；落盘为异步过程，
    # 连续快速请求（<落盘延迟）之间不命中属预期 → 采用「预热 → 等待落盘 → 相同前缀验证」。
    warm = {
        "role": "user",
        "content": "warm-up: hi, I'd like a latte, please.",
    }
    verify_same = {
        "role": "user",
        "content": "warm-up: hi, I'd like a latte, please.",  # 与预热完全一致（例一：A+B 完整匹配）
    }
    verify_variant = {"role": "user", "content": "turn 2: and a croissant, thanks"}

    async def call(messages, tag: str) -> tuple[int | None, int | None]:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": MODEL,
                    "temperature": 0.6,
                    "max_tokens": 32,
                    "messages": messages,
                },
            )
        if resp.status_code != 200:
            print(f"  [{tag}] HTTP {resp.status_code}: {resp.text[:200]}")
            return None, None
        usage = (resp.json().get("usage") or {})
        hit = usage.get("prompt_cache_hit_tokens")
        miss = usage.get("prompt_cache_miss_tokens")
        if hit is None or miss is None:
            print(
                f"  [{tag}] usage 字段缺失: {usage} —— 请确认模型/端点支持缓存字段"
            )
            return None, None
        print(f"  [{tag}] hit={hit} miss={miss}")
        return int(hit), int(miss)

    system_static = (
        SYSTEM_STATIC
        + "\n── DYNAMIC BEGIN ── (poc placeholder)"
    )

    print("[1] 预热请求（落盘 A+B 单元）")
    await call([{"role": "system", "content": system_static}, warm], "warm-up")

    print("[2] 等待缓存落盘（300s……后台执行，勿中断）")
    import time

    time.sleep(300)

    print("[3] 相同前缀验证（A+B 完全一致 → 应命中）")
    h_same, m_same = await call(
        [{"role": "system", "content": system_static}, verify_same], "verify-same"
    )

    print("[4] 动态尾验证（A+B 共享前缀 + 新尾；公共前缀 A+B 已落盘 → 应命中 A+B 段）")
    h_var, m_var = await call(
        [{"role": "system", "content": system_static}, verify_variant], "verify-variant"
    )

    print("== 判定 ==")
    if (h_same or 0) > 0:
        print("PASS → 前缀缓存机制成立（相同前缀落盘后可命中）")
    elif (h_var or 0) > 0:
        print("PARTIAL → 完整前缀尚未命中但共享前缀命中（公共前缀检测生效）")
    else:
        print(
            "NO-CACHE → 前/前缀均未命中：核查静态块是否真的逐字稳定 / 模型与端点是否支持缓存 / "
            "是否受 5 分钟落盘延迟之外的因素影响"
        )


if __name__ == "__main__":
    import asyncio as _asyncio

    _asyncio.run(main())
