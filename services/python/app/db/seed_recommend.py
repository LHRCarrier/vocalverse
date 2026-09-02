"""推荐系统演示数据播种（**Python seed，单写豁免**；local/32 A-5.1~A-5.5）。

覆盖（幂等，自然键查重）：
- 演示场景：补 2 个 L3/L4 场景（跨-exam A-5.2：现 seed 只有 difficulty 1/3、专家先验也无 L4，
  "L4 看高端内容"无素材可推）。material_difficulty 强制 L3/L4，使 3 个演示账号推荐互异；
- material_difficulty：全部 published 场景的专家先验（复用 app.difficulty.batch）——推荐 SQL 依赖；
- 3 个推荐演示账号（L2/L3/L4）：预置 user_profiles.interest_tags + user_skill_state
  （动态档 est_level + confidence=1.0），使「推荐素材不同」可复现（A-5.1/A-5.2/A-5.3）。

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
from app.difficulty.batch import compute_scenario_features, upsert_scenarios
from app.models import Scenario, User, UserProfile, UserSkillState

# 演示补充场景（L3/L4）——目标：让 3 个水平账号推荐互异，可行 A-5.2 演示
DEMO_SCENES = [
    {
        "title": "面试 · 压力面（演示）",
        "scene_type": "interview",
        "difficulty": 3,
        "system_prompt": "You are a senior interviewer. Ask tougher follow-ups.",
        "opening_line": "Welcome. Let's dig into your past projects.",
        "target_corpus": "Could you walk me through a conflict at work?|你能讲讲工作中的一次冲突吗？\n"  # noqa: E501
        "How did you resolve the disagreement?|你是如何解决分歧的？",
        "interest_tags": ["career", "interview"],
        "force_level": "L3",
        "force_score": 75.0,
    },
    {
        "title": "商务谈判 · 深度磋商（演示）",
        "scene_type": "other",
        "difficulty": 4,
        "system_prompt": "You are a professional negotiator. Use precise, formal English.",
        "opening_line": "Let's discuss the terms of the partnership.",
        "target_corpus": "We propose a revenue-sharing model with a cap.|我们建议设上限的收益分成模式。\n"  # noqa: E501
        "Our bottom line is a three-year commitment.|我们的底线是三年承诺。",
        "interest_tags": ["career", "negotiation", "advanced"],
        "force_level": "L4",
        "force_score": 88.0,
    },
]
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


def seed_demo_scenes(session) -> int:
    """幂等新增 L3/L4 演示场景。"""
    n = 0
    for item in DEMO_SCENES:
        exists = session.execute(select(Scenario.id).where(Scenario.title == item["title"])).first()
        if exists:
            continue
        session.add(
            Scenario(
                title=item["title"],
                scene_type=item["scene_type"],
                difficulty=item["difficulty"],
                system_prompt=item["system_prompt"],
                opening_line=item["opening_line"],
                target_corpus=item["target_corpus"],
                interest_tags=item["interest_tags"],
                status="published",
            )
        )
        n += 1
    session.flush()
    return n


def seed_material_difficulty(session) -> int:
    """为 published 场景预置专家先验；演示场景强制 L3/L4。"""
    force = {s["title"]: (s["force_level"], s["force_score"]) for s in DEMO_SCENES}
    scenarios = (
        session.execute(select(Scenario).where(Scenario.status == "published")).scalars().all()
    )
    feats = []
    for s in scenarios:
        c = compute_scenario_features(s.title, s.target_corpus, s.difficulty)
        if s.title in force:
            lvl, score = force[s.title]
            c["prior_score"] = score
            c["diff_level"] = lvl
        c["_content_id"] = int(s.id)
        feats.append(c)
    return upsert_scenarios(session, feats) if feats else 0


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


def main() -> int:
    session = get_session_factory()()
    try:
        n_scenes = seed_demo_scenes(session)
        n_difficulty = seed_material_difficulty(session)
        n_demo = seed_demo_reco_accounts(session)
        session.commit()
        print(
            f"[seed_recommend] demo_scenes +{n_scenes} / material_difficulty +{n_difficulty} "
            f"/ demo_reco 账号 {n_demo}（幂等）"
        )
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
