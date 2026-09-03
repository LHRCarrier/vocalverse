"""LLM 框架实跑冒烟（docs/26 §8⑦）：ContextBuilder + 真 DeepSeek 流式 + TurnRunner + MetaExecutor。

5 回合模拟场景对话（不用 DB/音频/服务），验证：
- 前缀稳定策略下的真实流式响应（META 解析成功率）
- 画像注入行不影响 META 协议
- MetaExecutor 命中合并与收尾判定在真实输出上工作

用法（仓库根/services/python，需 env 有 Key；无 Key 则离线自检后退出）：
    uv run python scripts/poc/llm_framework_smoke.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# 让脚本可从任意 cwd 导入 app 包（services/python 为工程根）
_SERVICE_DIR = Path(__file__).resolve().parents[2] / "services" / "python"
if str(_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICE_DIR))

import httpx

BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

SCENARIO_PROMPT = (
    "You are Maya, a friendly and patient barista at a cozy small cafe. "
    "You love chatting with customers and gently helping them practice English. "
    "Smile and be encouraging, but stay in character."
)
CORPUS_TEXT = (
    "I'd like a coffee, please.|请给我来杯咖啡\n"
    "Could I have a cappuccino?|来杯卡布奇诺\n"
    "How much is it?|多少钱\n"
    "Can I drink it here?|可以在这喝吗\n"
    "Thanks, that's all.|谢谢，就这些"
)
TURNS = [
    "hi, I would like a coffee please",
    "I'd like a coffee, please. And what type do you have?",
    "How much is it? Can I have a cappuccino?",
    "Can I drink it here?",
    "ok thanks that's all, bye",
]
LEARNER = (
    "Learner profile (internal): weak phrases: Could I have a cappuccino?; "
    "frequent word errors: cappuccino. Gently address these, do not overcorrect."
)


def load_key() -> str:
    try:
        from dotenv import load_dotenv

        for path in (
            Path(__file__).resolve().parents[2] / ".env",
            Path(__file__).resolve().parents[2] / "services" / "python" / ".env",
        ):
            if path.exists():
                load_dotenv(path)
    except Exception:
        pass
    return os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("APP_DEEPSEEK_API_KEY", "")


async def main() -> int:
    key = load_key()
    if not key:
        print("未设置 DEEPSEEK_API_KEY —— 跳过 LLM 框架实跑冒烟")
        return 0

    from app.agent.domains.learner import get_rendered  # noqa: F401  (仅确认导入链)
    from app.agent.runtime.context_builder import build_context
    from app.agent.runtime.meta_executor import MetaExecutor, compensate_meta
    from app.agent.runtime.turn_runner import TurnRunner
    from app.audio.llm import DeepSeekLLMClient
    from app.practice.corpus import parse_corpus
    from app.practice.state import SessionState

    llm = DeepSeekLLMClient(api_key=key, base_url=BASE_URL, model=MODEL)
    ex = MetaExecutor()
    corpus = parse_corpus(CORPUS_TEXT)
    state = SessionState(session_id=1, kind="dialog")
    state.digest = []
    meta_ok = 0
    compensated = 0
    concluded = False

    for i, user_text in enumerate(TURNS, start=1):
        messages = build_context(
            state,
            SCENARIO_PROMPT,
            CORPUS_TEXT,
            difficulty=2,
            user_text=user_text,
            action="normal",
            hits_so_far=state.corpus_done,
            concluded_by_turn=(i >= 5),
            learner_profile=LEARNER if i >= 2 else "",  # 第 2 轮起带画像行
        )
        runner = TurnRunner(llm)
        try:
            async for _delta in runner.run(messages):
                pass
        except httpx.HTTPStatusError as exc:
            print(f"  turn[{i}] HTTP 错误: {exc.response.status_code}")
            continue
        res = runner.result
        assert res is not None
        # 与 orchestrator 同链：流式未守契约 → 补偿调用（docs/26 §9.4）
        meta = res.meta
        if not meta.ok:
            meta = await compensate_meta(
                llm, reply_text=res.reply_text, transcript=user_text,
                action="normal", concluded_by_turn=(i >= 5),
            )
            compensated += 1
        hits = ex.apply_hits(user_text, corpus, meta, "normal", [])
        hits_text = "; ".join(f"{h['phrase'][:24]}({h['state']})" for h in hits) or "-"
        status = "OK" if meta.ok else "MISS"
        if meta.ok:
            meta_ok += 1
        print(
            f"  turn[{i}] META={status}{'+补偿' if status == 'OK' and compensated >= 0 and res.meta.ok is False else ''} "
            f"leaked={res.leaked} reply={res.reply_text[:60]!r} "
            f"hits=[{hits_text}] conclude={meta.conclude}"
        )
        state.digest.append(f"U: {user_text[:60]} | A: {res.reply_text[:60]}")
        for h in hits:
            if h["phrase"] not in state.corpus_done:
                state.corpus_done.append(h["phrase"])
        if i >= 5 or meta.conclude:
            concluded = True
            print(f"  -- 会话于第 {i} 轮收尾（conclude={meta.conclude}）")
            break

    rate = meta_ok / i * 100
    print(f"\n-- 统计: META 解析 {meta_ok}/{i} = {rate:.0f}%（补偿调用 {compensated} 次）")
    print("== 判定 ==")
    if rate >= 80:
        print("PASS → LLM 框架（ContextBuilder+TurnRunner+补偿+MetaExecutor）真实链路成立")
        return 0
    print("FAIL → META 解析率低：检查 prompt 模板；需评估两调用全量回退（docs/18 §6）")
    return 1


if __name__ == "__main__":
    import asyncio as _asyncio

    sys.exit(_asyncio.run(main()))
