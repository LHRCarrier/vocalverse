"""推荐系统演示数据播种（**Python seed，单写豁免**；local/32 A-5.1~A-5.5）。

覆盖（幂等，自然键查重）：
- 演示影子跟读：补 L2/L3/L4 三条 shadow_materials（此前全仓无影子素材，recommend_shadow 恒空，
  联调 AI 反馈本地复现 shadow=0 条）；
- 3 个推荐演示账号（L2/L3/L4）：预置 user_profiles.interest_tags + user_skill_state
  （动态档 est_level + confidence=1.0），使「推荐素材不同」可复现（A-5.1/A-5.2/A-5.3）。

2026-09-21（酒馆迁移）：演示场景（L3/L4）+ 场景 material_difficulty 播种随英语场景对话移除
（`app.difficulty.batch` 一并删除）；影子素材按 `level` 兜底参与推荐，不需 material_difficulty 行。

注意：demo user 行按 seed 单写豁免创建（docs/11 Q-A15，与 scenarios 同先例）；
Java 侧若改 CommandLineRunner 播种，需同步 interest_tags 映射（UserProfileEntity，A-5.1）。

用法（services/python 目录）：
    uv run python -m app.db.seed_recommend
"""

from __future__ import annotations

import sys
from decimal import Decimal

from sqlalchemy import select

from app.db import get_session_factory
from app.models import ShadowMaterial, User, UserProfile, UserSkillState

# 演示补充场景（L3/L4）——2026-09-21 随英语场景对话移除（历史保留注释，代码见 git history）
# 3 个推荐演示账号：level 覆盖 L2/L3/L4；interest_tags 与场景标签匹配（保"命中兴趣≥60%"）
DEMO_RECO_ACCOUNTS = {
    "demo_reco_L2": {
        "cefr": "L2",
        "est_level": "L2",
        "est_score": 62.0,
        "tags": ["daily-life", "ordering", "travel"],
    },
    "demo_reco_L3": {
        "cefr": "L3",
        "est_level": "L3",
        "est_score": 76.0,
        "tags": ["career", "interview"],
    },
    "demo_reco_L4": {
        "cefr": "L4",
        "est_level": "L4",
        "est_score": 88.0,
        "tags": ["career", "negotiation", "advanced"],
    },
}
# 演示影子跟读素材（local/31 §2.4 shadow_materials）：level=内容方初评 1-4；
# 无 material_difficulty 行时推荐引擎拿 level 兜底映射 [L1..L4]，足以让 recommend_shadow 非空。
# 账号标签 vs 影子标签对齐，使 3 个演示账号 shadow 推荐互异（与场景同理，A-5.2）。
DEMO_SHADOWS = [
    {
        "title": "咖啡馆 · 点单跟读（演示）",
        "level": 2,
        "text_content": "Hi, could I get a large flat white to go, please?",
        "audio_url": "/demo/audio/shadow/order.mp3",
        "wpm": 120,
        "duration_s": 12,
        "interest_tags": ["cafe", "ordering"],
    },
    {
        "title": "面试 · 自我介绍跟读（演示）",
        "level": 3,
        "text_content": "Thanks for having me. Let me briefly walk you through my background.",
        "audio_url": "/demo/audio/shadow/intro.mp3",
        "wpm": 145,
        "duration_s": 18,
        "interest_tags": ["career", "interview"],
    },
    {
        "title": "商务谈判 · 深度磋商跟读（演示）",
        "level": 4,
        "text_content": (
            "We propose a revenue-sharing model with a fixed cap for the first three years."
        ),
        "audio_url": "/demo/audio/shadow/negotiation.mp3",
        "wpm": 165,
        "duration_s": 22,
        "interest_tags": ["career", "negotiation", "advanced"],
    },
]


def _reconcile_demo(session, username: str, cfg: dict) -> None:
    """幂等：确保该 demo 账号存在，且 user_profiles/user_skill_state 对齐配置。"""
    user = session.execute(select(User).where(User.username == username)).scalar_one_or_none()
    if user is None:
        user = User(username=username, nickname=username, password_hash="x")
        session.add(user)
        session.flush()
    profile = session.execute(
        select(UserProfile).where(UserProfile.user_id == user.id)
    ).scalar_one_or_none()
    if profile is None:
        profile = UserProfile(user_id=user.id)
        session.add(profile)
        session.flush()
    profile.interest_tags = cfg["tags"]
    profile.cefr_level = cfg["cefr"]

    est = cfg["est_score"]
    skill = session.execute(
        select(UserSkillState).where(UserSkillState.user_id == user.id)
    ).scalar_one_or_none()
    if skill is None:
        session.add(
            UserSkillState(
                user_id=user.id,
                pron_est=Decimal(str(est)),
                flu_est=Decimal(str(est)),
                est_score=Decimal(str(est)),
                est_level=cfg["est_level"],
                confidence=Decimal("1.0"),
                sample_count=10,
                source_version="win-v1",
            )
        )
    else:
        skill.est_score = Decimal(str(est))
        skill.est_level = cfg["est_level"]
        skill.confidence = Decimal("1.0")
        skill.sample_count = 10


def seed_demo_reco_accounts(session) -> int:
    for username, cfg in DEMO_RECO_ACCOUNTS.items():
        _reconcile_demo(session, username, cfg)
    return len(DEMO_RECO_ACCOUNTS)


def seed_demo_shadows(session) -> int:
    """幂等新增演示影子跟读素材（补齐 shadow 推荐无数据可推的缺口）。"""
    n = 0
    for item in DEMO_SHADOWS:
        exists = session.execute(
            select(ShadowMaterial.id).where(ShadowMaterial.title == item["title"])
        ).first()
        if exists:
            continue
        session.add(
            ShadowMaterial(
                title=item["title"],
                level=item["level"],
                text_content=item["text_content"],
                audio_url=item["audio_url"],
                wpm=item["wpm"],
                duration_s=item["duration_s"],
                interest_tags=item["interest_tags"],
                source="demo_only",
                status="published",
            )
        )
        n += 1
    session.flush()
    return n


def main() -> int:
    session = get_session_factory()()
    try:
        n_demo = seed_demo_reco_accounts(session)
        n_shadow = seed_demo_shadows(session)
        session.commit()
        print(f"[seed_recommend] demo_reco 账号 {n_demo} / demo_shadows +{n_shadow}（幂等）")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
