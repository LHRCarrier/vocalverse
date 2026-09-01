"""seed 实跑验证（docs/18 §3-J1/§3.11：幂等 + 内容解析）。

- 独立 SQLite 内存引擎（create_all，与生产 PG 同模型元数据）→ 执行 seed 函数 → 断言行数与幂等；
- 隔离保证：不共享 conftest 全局引擎（其它用例会向全局库插入场景，污染断言）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.db.seed import (
    PLACEMENT_QUESTIONS,
    SCENARIOS_SEED,
    seed_placement_questions,
    seed_scenarios,
)
from app.models import Base, Scenario
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture()
def seed_session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def test_seed_scenarios_idempotent(seed_session):
    n1 = seed_scenarios(seed_session)
    seed_session.commit()
    assert n1 == 8, f"首次应插入 8 套，实际 {n1}"
    n2 = seed_scenarios(seed_session)
    seed_session.commit()
    assert n2 == 0, f"二次应幂等（0），实际 {n2}"
    total = seed_session.execute(select(func.count()).select_from(Scenario)).scalar_one()
    assert total == 8


def test_seed_placement_questions_idempotent(seed_session):
    n1 = seed_placement_questions(seed_session)
    seed_session.commit()
    assert n1 == len(PLACEMENT_QUESTIONS) == 6
    n2 = seed_placement_questions(seed_session)
    seed_session.commit()
    assert n2 == 0


def test_scenarios_json_content_spec():
    """docs/18 §1 P5：4 场景 × 2 套；每套 target_corpus 5 条（phrase|中文释义）；难度分档。"""
    data = json.loads(SCENARIOS_SEED.read_text(encoding="utf-8"))
    items = data["scenarios"]
    assert len(items) == 8
    scene_types = {it["scene_type"] for it in items}
    assert scene_types == {"cafe", "airport", "interview", "library"}
    for it in items:
        assert it["status"] == "published"
        assert it["difficulty"] in (1, 3)  # 入门套=1，进阶套=3（docs/14 §3.1）
        assert it["system_prompt"] and it["opening_line"]
        corpus = it["target_corpus"].strip().split("\n")
        assert len(corpus) == 5, f"{it['title']} 语料应为 5 条"
        for line in corpus:
            assert "|" in line, f"语料行缺释义分隔: {line!r}"
    # 套装：低难度 4 套 + 高难度 4 套
    assert sum(1 for it in items if it["difficulty"] == 1) == 4
    assert sum(1 for it in items if it["difficulty"] == 3) == 4


def test_seed_through_session_roundtrip(seed_session):
    """seed 写入后可按（status, difficulty）索引查询（docs/14 §3.1 列表过滤）。"""
    seed_scenarios(seed_session)
    seed_session.commit()
    rows = (
        seed_session.execute(
            select(Scenario).where(Scenario.status == "published", Scenario.difficulty == 1)
        )
        .scalars()
        .all()
    )
    assert len(rows) == 4
    assert all(r.target_corpus for r in rows)
