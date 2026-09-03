"""探针 v3：动态块迁移到 user 尾部 vs 留在 system（docs/26 POC 复盘——找修复姿势）。

D = 静态+动态（system 内）· 流式          —— 已知 0%（冒烟复现）
E = 系统全静态 + user 尾部 [context] 动态块 · 流式 —— 候选修复
D1 = 静态 + 难度/轮次/摘要（无语料行）· 流式  —— 定位凶手（语料行 or 其余）

用法（需 Key）：uv run python scripts/poc/llm_meta_ab.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import httpx

BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
RUNS = 8

STATIC = (
    "You are Maya, a friendly barista role-playing in a cafe. "
    "Answer in 2 short English sentences (max 3). "
    "If the conversation reached the limit or user ends, set conclude=true. "
    "Output contract: reply as plain English text ONLY, then finish with a single line:\n"
    "[-META-]{}\n"
    "META JSON fields: grammar:{score:0-100,errors:[{word,fix}]}, coach_note(≤15 words), "
    "corpus_hits:[{phrase,state:'ok'|'fix'}], difficulty_delta:-1|0|1, conclude(bool)."
)
DYNAMIC = (
    "\n── DYNAMIC BEGIN ──\n"
    "Target language level: difficulty 2\n"
    "Naturally steer the topic toward these target expressions WITHOUT reading them aloud: "
    "I'd like a coffee, please.|请给我来杯咖啡\n"
    "Already used expressions — rephrase instead: (none)\n"
    "Turn limit reached: False\n"
    "Recent turns:\n(conversation start)"
)
DYNAMIC_NO_CORPUS = (
    "\n── DYNAMIC BEGIN ──\n"
    "Target language level: difficulty 2\n"
    "Already used expressions — rephrase instead: (none)\n"
    "Turn limit reached: False\n"
    "Recent turns:\n(conversation start)"
)
USER_TAIL = (
    "{speech}\n"
    "action: normal\n"
    "word_errors: 0\n"
    "[context]\n"
    "Target language level: difficulty 2. Naturally steer the topic toward these target "
    "expressions WITHOUT reading them aloud: {corpus}. "
    "Already used expressions — rephrase instead: (none). Turn limit reached: False."
)


def load_key() -> str:
    for path in (
        Path(__file__).resolve().parents[2] / ".env",
        Path(__file__).resolve().parents[2] / "services" / "python" / ".env",
    ):
        if path.exists():
            try:
                from dotenv import load_dotenv

                load_dotenv(path)
            except Exception:
                pass
    return os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("APP_DEEPSEEK_API_KEY", "")


def _ok(text: str) -> bool:
    idx = text.rfind("[-META-]")
    if idx < 0:
        return False
    try:
        json.loads(text[idx + len("[-META-]"):].strip())
        return True
    except json.JSONDecodeError:
        return False


async def stream(client: httpx.AsyncClient, messages: list[dict]) -> bool:
    buf: list[str] = []
    async with client.stream(
        "POST",
        f"{BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {os.environ['DEEPSEEK_API_KEY']}",
                 "Content-Type": "application/json"},
        json={"model": MODEL, "temperature": 0.6, "max_tokens": 256, "stream": True,
              "messages": messages},
    ) as resp:
        if resp.status_code != 200:
            await resp.aread()
            return False
        async for line in resp.aiter_lines():
            if not line.startswith("data:"):
                continue
            body = line[5:].strip()
            if body == "[DONE]":
                break
            try:
                delta = json.loads(body)["choices"][0].get("delta", {}).get("content")
            except (json.JSONDecodeError, KeyError, IndexError):
                continue
            if delta:
                buf.append(delta)
    return _ok("".join(buf))


async def main() -> None:
    key = load_key()
    if not key:
        print("无 Key，跳过")
        return
    os.environ["DEEPSEEK_API_KEY"] = key
    arms = [
        ("E2 动态在 user 尾 + 语料仅英文（候选修复）",
         [{"role": "system", "content": STATIC},
          {"role": "user", "content": USER_TAIL.format(
              speech="hi, I'd like a coffee, please.",
              corpus="I'd like a coffee, please; Could I have a cappuccino?; How much is it?")}]),
        ("E3 动态在 system（同 E2 语料：仅英文）",
         [{"role": "system", "content": STATIC + DYNAMIC_NO_CORPUS.replace(
             "Target language level: difficulty 2",
             "Target language level: difficulty 2\\n"
             "Naturally steer the topic toward these target expressions WITHOUT reading "
             "them aloud: I'd like a coffee, please; Could I have a cappuccino?; How much is it?")},
          {"role": "user", "content": "hi, I'd like a coffee, please."}]),
    ]
    async with httpx.AsyncClient(timeout=60) as client:
        for label, messages in arms:
            ok = 0
            for _ in range(RUNS):
                ok += 1 if await stream(client, messages) else 0
            print(f"[{label}] {ok}/{RUNS} = {ok / RUNS * 100:.0f}%")


if __name__ == "__main__":
    import asyncio as _asyncio

    _asyncio.run(main())
