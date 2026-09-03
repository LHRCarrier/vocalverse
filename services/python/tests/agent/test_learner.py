"""学习者画像域单测（docs/26 P0 · docs/24 B3 表格 P4/P5/P7/P8 修订版）。

覆盖：聚合排序与条数上限、词级窗口、渲染/省略双态、开关关闭、invalidate 重建、收尾挂钩。
前置失败语义（docs/24 拷问口径）：以下用例在本域模块建立前一律失败（不存在）；实现回归时
每例都应有独立的失败理由（词级空串误判、窗口越界、缓存不失效等）。
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from app.agent.domains import learner as lm
from app.core.config import get_settings
from app.db import get_session_factory
from app.models import Attempt, Scenario, User, UserCorpusMastery
from app.models import Session as DbSession
from app.models.base import AttemptKinds, MasteryStatus, SessionKinds, SessionStatus


def _seed_user() -> int:
    db = get_session_factory()()
    try:
        u = User(username=f"lu{uuid4().hex[:8]}", nickname="n", password_hash="x")
        db.add(u)
        db.flush()
        return int(u.id)
    finally:
        db.close()


def _seed_session(uid: int) -> tuple[int, int]:
    """最小 dialog 会话（attempts 的 FK 依赖）。"""
    db = get_session_factory()()
    try:
        sc = Scenario(
            title="s",
            scene_type="cafe",
            difficulty=2,
            system_prompt="p",
            opening_line="o",
            target_corpus="a|b",
        )
        db.add(sc)
        db.flush()
        sess = DbSession(
            user_id=uid,
            kind=SessionKinds.DIALOG,
            scenario_id=sc.id,
            status=SessionStatus.COMPLETED,
            started_at=datetime.now(UTC),
        )
        db.add(sess)
        db.flush()
        sid = int(sess.id)
        db.commit()
        return sid, int(sc.id)
    finally:
        db.close()


def _seed_corpus(uid: int, scenario_id: int, phrases: list[str], start_index: int = 1) -> None:
    """line_index 从 start_index 递增；last_practiced_at 按索引递增（验证排序）。"""
    db = get_session_factory()()
    try:
        for i, ph in enumerate(phrases, start=start_index):
            db.add(
                UserCorpusMastery(
                    user_id=uid,
                    scenario_id=scenario_id,
                    line_index=i,
                    phrase=ph,
                    status=MasteryStatus.NOT_MASTERED,
                    last_practiced_at=datetime(2026, 9, 1 + i),
                )
            )
        db.commit()
    finally:
        db.close()


def _seed_attempts(uid: int, sess_id: int, word_levels: list[list[dict]]) -> None:
    """按顺序创建 attempts（id 递增即创建序）；word_levels 与 attempt 一一对应。"""
    db = get_session_factory()()
    try:
        for wl in word_levels:
            db.add(
                Attempt(
                    user_id=uid,
                    session_id=sess_id,
                    kind=AttemptKinds.DIALOG_SPEECH,
                    details={"word_level": wl},
                )
            )
        db.commit()
    finally:
        db.close()


def _weak_word(word: str, etype: str = "E1", score: float = 40.0) -> dict:
    return {"word": word, "error_type": etype, "score": score}


# ---------------------------------------------------------------------------
# P4：聚合排序与条数上限
# ---------------------------------------------------------------------------
def test_build_profile_aggregates_and_caps() -> None:
    uid = _seed_user()
    sess_id, sc_id = _seed_session(uid)
    _seed_attempts(
        uid,
        sess_id,
        [
            [
                {"word": "hello", "error_type": "E1", "score": 42},
                {"word": "order", "error_type": "", "score": 55},
            ],  # 空字符串 ≠ 错误（F04）
            [{"word": "hello", "error_type": "E1", "score": 40}],
            [{"word": "okay", "error_type": "E0", "score": 80}],  # E0=标准音，不算
        ],
    )
    db = get_session_factory()()
    try:
        p = lm.build_profile(db, uid)
    finally:
        db.close()
    # 词频：hello×2 > order×1（E0/空串均不计）；条数上限 3
    assert p.weak_words[:2] == ["hello", "order"]
    assert all(w in ("hello", "order") for w in p.weak_words)
    assert len(p.weak_words) <= get_settings().learner_max_items


def test_render_empty_profile_omits_line() -> None:
    assert lm.render(lm.LearnerProfile([], [], None)) == ""
    text = lm.render(lm.LearnerProfile(["How much is it?"], ["hello"], "L2"))
    assert "How much is it?" in text and "hello" in text and "L2" in text
    assert "do not overcorrect" in text


# ---------------------------------------------------------------------------
# P5：词级窗口越界（窗口外不参与聚合）
# ---------------------------------------------------------------------------
def test_word_window_excludes_oldest() -> None:
    uid = _seed_user()
    sess_id, _ = _seed_session(uid)
    # 21 条：最新 20 条都含 "comm"；最旧 1 条（id 最小）仅含 "zoldest"
    levels = [[_weak_word("zoldest")]] + [[_weak_word("comm")] for _ in range(20)]
    _seed_attempts(uid, sess_id, levels)  # 先写 zoldest（id 最小=最旧）
    db = get_session_factory()()
    try:
        p = lm.build_profile(db, uid)
    finally:
        db.close()
    assert "comm" in p.weak_words
    assert "zoldest" not in p.weak_words  # 窗口 20 → 最旧 1 条被排除


# ---------------------------------------------------------------------------
# P7：开关关闭 → 恒 ""
# ---------------------------------------------------------------------------
def test_disabled_injection_returns_empty(monkeypatch) -> None:
    uid = _seed_user()
    monkeypatch.setattr(get_settings(), "learner_injection_enabled", False)
    assert lm.get_rendered(uid) == ""


# ---------------------------------------------------------------------------
# P6：invalidate 后重建读到新数据
# ---------------------------------------------------------------------------
def test_invalidate_rebuilds_profile() -> None:
    uid = _seed_user()
    sess_id, sc_id = _seed_session(uid)
    _seed_corpus(uid, sc_id, ["old phrase"])
    p1 = lm.get_rendered(uid)
    assert "old phrase" in p1

    _seed_corpus(
        uid, sc_id, ["new phrase", "another new"], start_index=2
    )  # 追加（line_index 递增，避开唯一键）
    assert "new phrase" not in lm.get_rendered(uid)  # 缓存命中（旧画像）

    lm.invalidate(uid)
    p2 = lm.get_rendered(uid)
    assert "new phrase" in p2  # 重建后包含新数据


# ---------------------------------------------------------------------------
# P8：会话收尾挂钩触发 invalidate
# ---------------------------------------------------------------------------
def test_post_session_hook_invalidates(monkeypatch) -> None:
    import app.agent.domains.learner as lm_mod
    from app.practice.service import _post_session_skills

    uid = _seed_user()
    sess_id, _ = _seed_session(uid)
    calls: list[int] = []
    monkeypatch.setattr(lm_mod, "invalidate", lambda u: calls.append(int(u)))

    db = get_session_factory()()
    try:
        session = db.get(DbSession, sess_id)
        assert session is not None
        _post_session_skills(db, session)  # skills 更新可能因缺数据异常，但仍应触发失效
    finally:
        db.close()
    assert calls == [uid]


# ---------------------------------------------------------------------------
# 词级谓词边界（F04：空串/other/E0 不误判为错误）
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "etype,score,expected",
    [
        ("", 80, False),
        ("other", 80, False),
        ("E0", 80, False),
        ("E1", 80, True),
        ("", 30, True),  # 空串但低分 → 弱信号
    ],
)
def test_is_weak_word_predicate(etype: str, score: float, expected: bool) -> None:
    assert lm._is_weak_word({"word": "w", "error_type": etype, "score": score}) is expected
