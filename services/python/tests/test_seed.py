"""seed 实跑验证（docs/18 §3-J1/§3.11：幂等 + 内容规格）。

- 独立 SQLite 内存引擎（create_all，与生产 PG 同模型元数据）→ 执行 seed 函数 → 断言行数与幂等；
- 隔离保证：不共享 conftest 全局引擎（其它用例会向全局库插入数据，污染断言）。

2026-09-21（酒馆迁移）：scenarios 种子随英语场景对话移除，本文件仅覆盖
placement_questions 种子。
"""

from __future__ import annotations

import pytest
from app.db.seed import PLACEMENT_QUESTIONS, seed_placement_questions
from app.models import Base, PlacementQuestion
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool


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


def test_seed_placement_questions_idempotent(seed_session):
    n1 = seed_placement_questions(seed_session)
    seed_session.commit()
    assert n1 == len(PLACEMENT_QUESTIONS) == 6
    n2 = seed_placement_questions(seed_session)
    seed_session.commit()
    assert n2 == 0
    total = seed_session.execute(select(func.count()).select_from(PlacementQuestion)).scalar_one()
    assert total == 6


def test_placement_questions_content_spec():
    """docs/06 §9.2：5 句固定朗读 + 1 轮 QA；自然键 (exam_revision, item_index) 可复现。"""
    assert len(PLACEMENT_QUESTIONS) == 6
    kinds = [q["kind"] for q in PLACEMENT_QUESTIONS]
    assert kinds.count("read") == 5 and kinds.count("qa") == 1
    assert [q["item_index"] for q in PLACEMENT_QUESTIONS] == [1, 2, 3, 4, 5, 6]
    assert all(q["exam_revision"] == 1 for q in PLACEMENT_QUESTIONS)
    assert all(q["prompt"] for q in PLACEMENT_QUESTIONS)
