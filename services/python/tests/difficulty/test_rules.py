"""素材难度专家规则单测（local/31 §6.2 B1~B8 + local/32 A-1.1~A-1.3 修订回归）。"""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.db import get_session_factory
from app.difficulty.rules import (
    dim_to_100,
    pron_score,
    scenario_prior,
    shadow_prior,
    syntax_score,
    vocab_score,
)
from app.models import MaterialDifficulty, Scenario
from sqlalchemy import select


def test_dim_to_100() -> None:
    """B2：M(k)=30+15(k-1)，1→30/3→60/5→90。"""
    assert dim_to_100(1) == pytest.approx(30.0)
    assert dim_to_100(3) == pytest.approx(60.0)
    assert dim_to_100(5) == pytest.approx(90.0)


def test_vocab_cefr_whitelist_fixes_long_common_words() -> None:
    """A-1.2 修正回归：'junior/student/majoring/communication' 虽长但属学习者高频词，词典应压实。"""
    easy = vocab_score("I am a junior student majoring in communication.")
    hard = vocab_score("My main responsibility was to coordinate the schedule.")
    assert easy < 3.0  # 白名单把长词压实（不再被"长词=难词"推高）
    assert hard > 3.0  # 学术后缀词（responsibility/coordinate）仍判难


def test_syntax_subordinators() -> None:
    """A-1.3：含从属连词/嵌套的句子，句法分高于简单句。"""
    simple = syntax_score("How much is it?")
    complex_ = syntax_score(
        "I would have communicated earlier because we missed the deadline, which was bad."
    )
    assert complex_ > simple


def test_pron_difficult_phonemes() -> None:
    """B3：含 θ/ð、r、词首辅音连缀的句，发音分高于纯简单句。"""
    easy = pron_score("Here you are.")
    hard = pron_score("I'd like to know my compensation options.")
    assert hard > easy


def test_scenario_prior_aggregate() -> None:
    """B4/B5：场景聚合 + λ 难点句加权 + 档位。"""
    lines = ["How much is it?", "Could you make it with oat milk?", "I'll take the smaller size."]
    r = scenario_prior(lines)
    assert r["dims"]["vocab"] >= 1.0
    assert 0.0 <= r["prior"] <= 100.0
    assert r["level"] in ("L1", "L2", "L3", "L4")


def test_shadow_prior_pause_direction() -> None:
    """B3：停顿方向反转——停顿越多（>16/min）=1 分（易），停顿越少=5 分（难）。"""
    slow = shadow_prior(wps=1.6, pause_per_min=16.0, links_per_100w=4.0)  # 慢+多停顿=易
    fast = shadow_prior(wps=2.5, pause_per_min=2.0, links_per_100w=12.0)  # 快+少停顿=难
    assert slow["prior"] < fast["prior"]


def test_batch_upsert_material_difficulty() -> None:
    """B6：--db 路径把 1 个场景写成 material_difficulty（source='expert' + features）。"""
    from app.difficulty.batch import compute_scenario_features, upsert_scenarios

    db = get_session_factory()()
    try:
        s = Scenario(
            title="batch-t",
            scene_type="cafe",
            difficulty=3,
            system_prompt="p",
            opening_line="o",
            target_corpus="Could you make it with oat milk?|可以\n"
            "I'll take the smaller size, please.|我要小杯。",
            status="published",
        )
        db.add(s)
        db.flush()
        f = compute_scenario_features(s.title, s.target_corpus, s.difficulty)
        f["_content_id"] = int(s.id)
        upsert_scenarios(db, [f], version="expert-v1")
        db.commit()
        row = db.execute(
            select(MaterialDifficulty).where(
                MaterialDifficulty.content_type == "scene",
                MaterialDifficulty.content_id == int(s.id),
            )
        ).scalar_one()
        assert row.difficulty_source == "expert"
        assert row.prior_score == Decimal(str(f["prior_score"]))
        assert row.diff_level == f["diff_level"]
        assert row.features["pending_review"] is not None
    finally:
        db.close()
