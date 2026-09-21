"""酒馆平台卡种子（**Python seed，单写豁免**；docs/52 §12.1）。

首张平台固定卡「迷雾酒馆」= ai4u 迁移示范剧本（酒馆/HP 12/吧台/短剑/任务/线索），
上架后所有用户在开局引导里可选；幂等策略：按 title + owner NULL 查重。

用法（services/python 目录）：
    uv run python -m app.db.seed_trpg
"""

from __future__ import annotations

import sys

from sqlalchemy import select

from app.db import get_session_factory
from app.models.base import TrpgCardSources, TrpgCardStatuses, TrpgLangs
from app.models.trpg import TrpgScenarioCard

DEMO_CARDS = [
    {
        "title": "迷雾酒馆",
        "summary": "小镇酒馆里流传着地下室的传闻，老板的眼神躲闪。",
        "language": TrpgLangs.ZH,
        "tags": ["悬疑", "小镇", "入门"],
        "scene": "酒馆",
        "opening_line": (
            "你推开酒馆的木门，潮湿的空气裹着麦酒味扑面而来。\n\n"
            "老板抬眼看了你一下，又低头擦起了杯子。\n\n"
            "角落里，一个披着斗篷的人朝你举了举酒杯。"
        ),
        "template": {
            "pc_name": "主角",
            "pc": {"hp": 12, "location": "吧台", "inventory": "短剑"},
            "facts": [{"key": "rel.酒保.attitude", "value": "友善", "modality": "fact"}],
            "tasks": ["打听镇上的怪谈"],
            "clues": [
                {
                    "title": "地下室里的暗门",
                    "content": "酒保提到过地下室的门，但马上闭了嘴",
                    "scene": "酒馆",
                }
            ],
        },
    },
    {
        "title": "雨夜驿站",
        "summary": "暴雨封路的夜晚，驿站里挤满了各怀心事的旅人。",
        "language": TrpgLangs.ZH,
        "tags": ["悬疑", "群像", "进阶"],
        "scene": "边陲驿站",
        "opening_line": (
            "雨水敲打着窗棂，驿站的炉火噼啪作响。\n\n"
            "掌柜给你腾出半张桌子：「今晚没人能上路了。」\n\n"
            "你注意到，最里桌的商人一直盯着你腰间的行囊。"
        ),
        "template": {
            "pc_name": "主角",
            "pc": {"hp": 14, "location": "驿站大堂", "inventory": "行囊与短刀"},
            "facts": [{"key": "rel.神秘商人.attitude", "value": "警惕", "modality": "fact"}],
            "tasks": ["查清商人为何盯着你的行囊"],
            "clues": [
                {"title": "行囊里的旧信", "content": "一封没有署名的旧信", "scene": "边陲驿站"}
            ],
        },
    },
]


def seed_platform_cards(session) -> int:
    inserted = 0
    for item in DEMO_CARDS:
        exists = session.execute(
            select(TrpgScenarioCard.id).where(
                TrpgScenarioCard.title == item["title"],
                TrpgScenarioCard.owner_user_id.is_(None),
            )
        ).first()
        if exists:
            continue
        session.add(
            TrpgScenarioCard(
                owner_user_id=None,
                source=TrpgCardSources.ADMIN,
                status=TrpgCardStatuses.PUBLISHED,
                generated_by="manual",
                **item,
            )
        )
        inserted += 1
    session.flush()
    return inserted


def main() -> int:
    session = get_session_factory()()
    try:
        n = seed_platform_cards(session)
        session.commit()
        print(f"[seed_trpg] platform_cards +{n}（跳过已存在）")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
