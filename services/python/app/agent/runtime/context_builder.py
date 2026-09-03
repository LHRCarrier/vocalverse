"""上下文组装（docs/26 runtime/context-builder：ai4u context-builder 的 VocalVerse 版）。

单一入口：组装 [system, user] 两条消息（docs/14 §3.4 契约）。

**POC 实证修正（2026-09-03 真 Key 实验，docs/26 §POC 复盘——违反直觉但铁证）**：
- system 内出现任何「动态 context 块」→ META 契约遵守率从 100% 暴跌至 0%（四臂探针
  D/E3 复现）；动态全部挂 user 消息尾部 + 语料仅英文 → **100%**（E2）；
- 因此 system = **纯静态**（角色 + 句长/语气规则 + conclude 指令 + 输出契约 + META 字段说明），
  逐字恒定 → 同时满足 DeepSeek 前缀缓存「完整匹配缓存前缀单元」（全量命中）；
- 动态上下文（难度/语料[仅英文 phrase]/画像/已命中/收尾/滚动摘要）全部在 user 端
  `[context]` 段内（ai4u 同款姿势 + IB ⑤「动态内容挂最后一条消息尾部」）；
- 画像注入（docs/24 ⑥）：learner_profile 行放 [context] 段（会话级稳定、用户专属）；
- 语义保真（docs/25 拷问 F01）：`set conclude=true` 指令、`(none)` 兜底全部保留。
"""

from __future__ import annotations

from collections.abc import Sequence

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


def _corpus_english(corpus_text: str) -> str:
    """语料只取英文 phrase（`phrase|中文释义` 行制式，corpus.py）——
    中文释义仅供用户展示，进 LLM 上下文会破坏 META 契约（POC 实证）。"""
    out: list[str] = []
    for line in (corpus_text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        phrase = line.split("|", 1)[0].strip()
        if phrase:
            out.append(phrase)
    return "; ".join(out)


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
    rolling_summary: str = "",
) -> list[dict[str, str]]:
    """组装 [system, user] 消息（system 纯静态；动态全部进 user 尾部 [context] 段）。

    state 仅用于读取滚动摘要（state.digest[-3:]）；其余全部显式传参（可单测、无 db 依赖）。
    rolling_summary：会话滚动摘要（sessions.summary，docs/26 §10.3①）——与画像行同级
    会话级稳定段，注入 [context] 尾部（绝不影响 system 静态契约）。
    """
    from app.practice.meta import MARKER

    system = _STATIC_TEMPLATE.format(scenario_prompt=scenario_prompt, marker=MARKER)

    ctx_lines = [
        f"Target language level: difficulty {difficulty}",
        "Naturally steer the topic toward these target expressions WITHOUT reading them "
        f"aloud: {_corpus_english(corpus_text) or '(none)'}",
    ]
    if learner_profile:
        ctx_lines.append(learner_profile)
    if rolling_summary:
        ctx_lines.append(f"Rolling summary (earlier turns): {rolling_summary}")
    ctx_lines.append(
        "Already used expressions — rephrase instead: "
        f"{', '.join(map(str, hits_so_far)) or '(none)'}"
    )
    ctx_lines.append(f"Turn limit reached: {concluded_by_turn}")
    ctx_lines.append("Recent turns:")
    ctx_lines.append("\n".join(state.digest[-3:]) or "(conversation start)")

    user_msg = (
        f"user said (ASR): {user_text or '(no speech)'}\n"
        f"action: {action} (retry/hint = learner needs help; be kind and short)\n"
        "word_errors: "
        + str(_count_errors(state.assembled.get("last_errors", [])))
        + "\n[context]\n"
        + "\n".join(ctx_lines)
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user_msg},
    ]


def _count_errors(errors: list | None) -> int:
    return len(errors) if errors else 0


__all__ = ["build_context"]
