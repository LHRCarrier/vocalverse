"""上下文组装（docs/26 runtime/context-builder：ai4u context-builder 的 VocalVerse 版）。

单一入口：把「场景人设 + 角色规则 + 输出契约 + 会话级稳定字段（难度/语料/学习者画像）+
轮次级可变字段（已命中/收尾标记/滚动摘要）」组装为 [system, user] 两条消息（docs/24 §1-A1 v3）。

设计要点（三官拷问修正后定稿，docs/25）：
- **静态块 / 动态块两级**：DeepSeek 上下文缓存按请求前缀自动匹配（无参、磁盘级）——
  静态块逐字稳定 → 每次调用命中；动态块内再分「会话级稳定（difficulty/corpus/画像）」
  在前、「逐轮变化（hits/concluded/digest）」在后 → 已命中前缀最大化；
- **语义保真（A 官 F01）**：本实现相对旧 build_llm_context 是重写而非"仅调序"——
  `set conclude=true` 行为指令保留在静态块；corpus/hits 空值保留 `(none)` 兜底；
- **画像注入（docs/26 P0 ⑥）**：learner_profile 行属于会话级稳定段（图片行按用户缓存，
  跨会话内稳定），空行整行省略；
- 纯函数：不访问 db/状态存储，输入即输出（可测性 = 框架分层的第一收益）。
"""

from __future__ import annotations

from collections.abc import Sequence

DYNAMIC_MARKER = "── DYNAMIC BEGIN ──"

_STATIC_TEMPLATE = (
    "{scenario_prompt}\n"
    "You are role-playing in an English speaking practice app. "
    "Keep sentences short (≤3 sentences), simple words, natural and encouraging.\n"
    "If the conversation reached the limit or user ends, set conclude=true.\n"
    "Output contract: reply as plain English text ONLY, then finish with a single line:\n"
    "[{marker}]\n"
    "META JSON fields: grammar:{{score:0-100,errors:[{{word,fix}}]}}, coach_note(≤15 words), "
    "corpus_hits:[{{phrase,state:'ok'|'fix'}}], difficulty_delta:-1|0|1, conclude(bool)."
)


def build_context(
    state,
    scenario_prompt: str,
    corpus_text: str,
    difficulty: int,
    user_text: str,
    action: str,
    hits_so_far: Sequence[str],
    concluded_by_turn: bool,
    learner_profile: str = "",
) -> list[dict[str, str]]:
    """组装 [system, user] 消息（docs/14 §3.4 契约：system + user，一次流式调用）。

    state 仅用于读取滚动摘要（state.digest[-3:]）；其余全部显式传参（可单测、无 db 依赖）。
    """
    from app.practice.meta import MARKER

    static = _STATIC_TEMPLATE.format(scenario_prompt=scenario_prompt, marker=MARKER)

    dynamic_lines = [
        f"Target language level: difficulty {difficulty}",
        f"Naturally steer the topic toward these target expressions WITHOUT reading them aloud: "
        f"{corpus_text or '(none)'}",
    ]
    if learner_profile:
        dynamic_lines.append(learner_profile)
    dynamic_lines.append(
        "Already used expressions — rephrase instead: "
        f"{', '.join(map(str, hits_so_far)) or '(none)'}"
    )
    dynamic_lines.append(f"Turn limit reached: {concluded_by_turn}")
    dynamic_lines.append("Recent turns:")
    dynamic_lines.append("\n".join(state.digest[-3:]) or "(conversation start)")
    system = static + "\n" + DYNAMIC_MARKER + "\n" + "\n".join(dynamic_lines)

    user_msg = (
        f"user said (ASR): {user_text or '(no speech)'}\n"
        f"action: {action} (retry/hint = learner needs help; be kind and short)\n"
        "word_errors: " + str(_count_errors(state.assembled.get("last_errors", [])))
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user_msg},
    ]


def _count_errors(errors: list | None) -> int:
    return len(errors) if errors else 0


__all__ = ["DYNAMIC_MARKER", "build_context"]
