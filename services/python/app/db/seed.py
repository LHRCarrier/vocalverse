"""幂等种子数据（docs/10 §7.3 · docs/18 §1 P5）。

覆盖内容（演示数据，单写豁免已随 M2 拍板登记）：
- placement_questions：5 句固定朗读 + 1 轮 QA（docs/06 §9.2 入学测试题库，admin 预置可复现）。

2026-09-21（酒馆迁移）：scenarios 种子（8 套英语场景）随场景对话移除，
`data/seed/scenarios.json` 一并删除；影子素材演示数据见 `app/db/seed_recommend.py`。

幂等策略：自然键查重（placement_questions 的 (exam_revision, item_index)），
已存在则跳过（不覆盖管理员后续编辑）。用户/档案类数据由 Java 侧播种（CommandLineRunner）。

用法（services/python 目录）：
    uv run python -m app.db.seed
"""

from __future__ import annotations

import sys

from sqlalchemy import select

from app.db import get_session_factory
from app.models import PlacementQuestion

# 入学测试题库（docs/06 §9.2：5 条固定朗读句 + 1 轮 QA；演示可复现）
PLACEMENT_QUESTIONS = [
    {
        "exam_revision": 1,
        "item_index": 1,
        "kind": "read",
        "prompt": "Good morning! I would like a cup of coffee, please.",
    },
    {
        "exam_revision": 1,
        "item_index": 2,
        "kind": "read",
        "prompt": "Could you tell me where the nearest bookstore is?",
    },
    {
        "exam_revision": 1,
        "item_index": 3,
        "kind": "read",
        "prompt": "My favorite season is autumn, because the weather is cool.",
    },
    {
        "exam_revision": 1,
        "item_index": 4,
        "kind": "read",
        "prompt": "She has been studying English for three years.",
    },
    {
        "exam_revision": 1,
        "item_index": 5,
        "kind": "read",
        "prompt": "I can finish the report by Friday afternoon.",
    },
    {
        "exam_revision": 1,
        "item_index": 6,
        "kind": "qa",
        "prompt": "Tell me something about yourself.",
        "reference_answer": "A short self-introduction: name, study/work, hobby or goal.",
    },
]


def seed_placement_questions(session) -> int:
    inserted = 0
    for item in PLACEMENT_QUESTIONS:
        exists = session.execute(
            select(PlacementQuestion.id).where(
                PlacementQuestion.exam_revision == item["exam_revision"],
                PlacementQuestion.item_index == item["item_index"],
            )
        ).first()
        if exists:
            continue
        session.add(PlacementQuestion(**item))
        inserted += 1
    session.flush()
    return inserted


def main() -> int:
    session = get_session_factory()()
    try:
        n_questions = seed_placement_questions(session)
        session.commit()
        print(f"[seed] placement_questions +{n_questions}（跳过已存在）")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
