"""ContextBuilder 单测（docs/26 P0 · docs/24 §1-B3 P1/P2 修正版）。

P1（A 官 F02 修正）：两次调用用**不同 state**（不同 digest/hits/concluded）→ 断言
`messages[0]` 中 `DYNAMIC_MARKER` 之前的**子串**逐字节一致（整条不要求一致）——旧实现
（单条 system 混装）不含该标记，本用例必失败（先红后绿的核心回归锚点）。
P2：动态字段全部位于标记之后；F01 保真项：`set conclude=true` 指令与 `(none)` 兜底存在。
"""

from __future__ import annotations

from app.agent.runtime.context_builder import DYNAMIC_MARKER, build_context
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


def _prefix(system: str) -> str:
    return system.split(DYNAMIC_MARKER)[0]


def test_prefix_static_across_different_states() -> None:
    """P1（修正版）：不同 state（不同 digest/hits/concluded）→ 标记前子串逐字节一致。"""
    m1 = _build(_state(digest=["U: a | A: b"], hits=["x"]), user_text="one")
    m2 = _build(_state(digest=["U: c | A: d", "U: e | A: f"], hits=["y", "z"]), user_text="two")
    assert len(m1) == 2 and m1[0]["role"] == "system" and m1[1]["role"] == "user"
    assert _prefix(m1[0]["content"]) == _prefix(m2[0]["content"])
    # 整条 system 不必一致（动态段不同）——断言锚点本身
    assert m1[0]["content"] != m2[0]["content"]


def test_prefix_preserves_behavior_instructions() -> None:
    """F01 保真：conclude 行为指令与输出契约必须保留在静态前缀。"""
    system = _build(_state())[0]["content"]
    pre = _prefix(system)
    assert "set conclude=true" in pre
    assert MARKER in pre
    assert "META JSON fields" in pre


def test_dynamic_fields_after_marker() -> None:
    """P2：难度/语料/画像/hits/收尾/摘要全部位于标记之后；前缀不含动态值。"""
    learner = (
        "Learner profile (internal): weak phrases: How much is it?. "
        "Gently address these, do not overcorrect."
    )
    state = _state(digest=["U: hi | A: hello"], hits=["already-hit"])
    system = _build(state, learner=learner)[0]["content"]
    pre, post = system.split(DYNAMIC_MARKER, 1)
    assert "difficulty 2" in post
    assert "I'd like a coffee." in post
    assert "already-hit" in post
    assert "Turn limit reached: True" in post
    assert "U: hi | A: hello" in post
    assert "Learner profile" in post
    assert (
        "difficulty 2" not in pre
    )  # 动态值不出现在前缀（META 字段名 difficulty_delta 属契约，例外）
    assert "Target language level" not in pre
    assert "already-hit" not in pre
    assert "U: hi" not in pre
    assert "Learner profile" not in pre


def test_learner_line_omitted_when_empty() -> None:
    system = _build(_state())[0]["content"]
    assert "Learner profile" not in system
    # 空值兜底（F01）：corpus/hits 为空时保留 (none)
    system2 = build_context(_state(), "p", "", 2, "u", "normal", [], False, learner_profile="")[0][
        "content"
    ]
    assert "(none)" in system2


def test_user_msg_keeps_dynamic_at_tail() -> None:
    state = _state()
    msgs = _build(state, user_text="maybe wrong word")
    assert msgs[1]["content"].startswith("user said (ASR): maybe wrong word")
