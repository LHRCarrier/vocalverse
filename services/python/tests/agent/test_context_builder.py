"""ContextBuilder 单测（docs/26 P0 · docs/14 §3.4 v2.2 实证契约）。

P1（A 官 F02 修正 + POC 实证升级）：两次调用用**不同 state**（不同 digest/hits/concluded）→
断言 **system 完全一致**（POC 铁证：system 必须 100% 静态，动态块进 system 直接摧毁
META 契约遵守率——0% vs 100%，docs/26 §POC 复盘）。
P2：动态字段（难度/语料/画像/hits/收尾/摘要）全部在 user 消息内；**中文释义不出现在任何消息**。
F01 保真：conclude 指令与 (none) 兜底存在。
"""

from __future__ import annotations

from app.agent.runtime.context_builder import build_context
from app.practice.meta import MARKER
from app.practice.state import SessionState


def _state(digest: list[str] | None = None, hits: list[str] | None = None) -> SessionState:
    s = SessionState(session_id=1, kind="dialog")
    s.digest = digest or []
    s.corpus_done = hits or []
    return s


def _build(state: SessionState, learner: str = "", user_text: str = "hello there"):
    return build_context(
        state,
        scenario_prompt="You are a friendly barista.",
        corpus_text="I'd like a coffee.|我要杯咖啡\nCould I have the bill?|请结账",
        difficulty=2,
        user_text=user_text,
        action="normal",
        hits_so_far=state.corpus_done,
        concluded_by_turn=True,
        learner_profile=learner,
    )


def test_system_static_identical_across_different_states() -> None:
    """P1：不同 state（不同 digest/hits/concluded）→ system 消息逐字节一致（全静态）。"""
    m1 = _build(_state(digest=["U: a | A: b"], hits=["x"]), user_text="one")
    m2 = _build(_state(digest=["U: c | A: d", "U: e | A: f"], hits=["y", "z"]), user_text="two")
    assert len(m1) == 2 and m1[0]["role"] == "system" and m1[1]["role"] == "user"
    assert m1[0]["content"] == m2[0]["content"]  # system 逐字节一致（前缀缓存全量命中）
    assert m1[1]["content"] != m2[1]["content"]  # 动态在 user 尾部


def test_system_preserves_behavior_instructions() -> None:
    """F01 保真：conclude 行为指令与输出契约必须保留在（静态）system。"""
    system = _build(_state())[0]["content"]
    assert "set conclude=true" in system
    assert MARKER in system
    assert "META JSON fields" in system


def test_dynamic_fields_all_in_user_message() -> None:
    """P2：难度/语料/画像/hits/收尾/摘要全部位于 user 消息；system 不含动态值。"""
    learner = (
        "Learner profile (internal): weak phrases: How much is it?. "
        "Gently address these, do not overcorrect."
    )
    state = _state(digest=["U: hi | A: hello"], hits=["already-hit"])
    msgs = _build(state, learner=learner)
    system, user = msgs[0]["content"], msgs[1]["content"]
    assert "difficulty 2" in user
    assert "I'd like a coffee." in user  # 英文短语
    assert (
        "请给我来杯咖啡" not in system and "请给我来杯咖啡" not in user
    )  # 中文释义不出现在 LLM 上下文
    assert "already-hit" in user
    assert "Turn limit reached: True" in user
    assert "U: hi | A: hello" in user
    assert "Learner profile" in user
    for needle in ("difficulty 2", "already-hit", "U: hi", "Learner profile"):
        assert needle not in system


def test_learner_line_omitted_when_empty() -> None:
    user = _build(_state())[1]["content"]
    assert "Learner profile" not in user
    # 空值兜底（F01）：corpus/hits 为空时保留 (none)
    state = _state()
    msgs = build_context(state, "p", "", 2, "u", "normal", [], False, learner_profile="")
    assert "(none)" in msgs[1]["content"]


def test_user_msg_head_kept() -> None:
    state = _state()
    msgs = _build(state, user_text="maybe wrong word")
    assert msgs[1]["content"].startswith("user said (ASR): maybe wrong word")
    assert "[context]" in msgs[1]["content"]
