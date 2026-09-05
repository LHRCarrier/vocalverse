"""幂等种子数据（docs/10 §7.3 · docs/18 §1 P5）。

覆盖内容（演示数据，单写豁免已随 M2 拍板登记）：
- scenarios：data/seed/scenarios.json（8 套：4 场景 × 入门/进阶）—— 全文入库；
- placement_questions：5 句固定朗读 + 1 轮 QA（docs/06 §9.2 入学测试题库，admin 预置可复现）。

幂等策略：自然键查重（scenarios.title；placement_questions 的 (exam_revision, item_index)），
已存在则跳过（不覆盖管理员后续编辑）。用户/档案类数据由 Java 侧播种（CommandLineRunner）。

用法（services/python 目录）：
    uv run python -m app.db.seed
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from sqlalchemy import select

from app.db import get_session_factory
from app.models import PlacementQuestion, Scenario

try:
    REPO_ROOT = Path(__file__).resolve().parents[4]  # 本地：services/python/app/db/seed.py → 仓库根
except IndexError:
    # 容器（WORKDIR /app + COPY . . → /app/app/db/seed.py，仅 4 级父目录，无「仓库根」）：
    # seed 数据由 compose migrate 挂载 ./data/seed:/app/data/seed（2026-09-04 方式A 实测：
    # parents[4] 越界抛 IndexError —— 与 PR#27 main.py 同类容器路径假设，一并修复）
    REPO_ROOT = Path("/app")

SCENARIOS_SEED = REPO_ROOT / "data" / "seed" / "scenarios.json"

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


def seed_scenarios(session) -> int:
    if not SCENARIOS_SEED.exists():
        print(f"[seed] 跳过 scenarios：缺 {SCENARIOS_SEED}")
        return 0
    data = json.loads(SCENARIOS_SEED.read_text(encoding="utf-8"))
    inserted = 0
    for item in data["scenarios"]:
        exists = session.execute(select(Scenario.id).where(Scenario.title == item["title"])).first()
        if exists:
            continue
        session.add(Scenario(**item))
        inserted += 1
    session.flush()
    return inserted


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
        n_scenarios = seed_scenarios(session)
        n_questions = seed_placement_questions(session)
        session.commit()
        print(f"[seed] scenarios +{n_scenarios} / placement_questions +{n_questions}（跳过已存在）")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
