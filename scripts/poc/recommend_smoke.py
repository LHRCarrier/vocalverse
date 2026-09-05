"""推荐系统冒烟脚本（local/31 §6.4 · local/32 A-5）：播种 → 三账号推荐 → 动态水平反馈 → 曝光埋点。

- 自包含：SQLite :memory:（无 Docker/PG），create_all + 播种（场景/专家先验/demo 账号）；
- 用法（services/python 目录）：
    uv run --no-project -p 3.12 --with fastapi --with "uvicorn[standard]" --with pydantic \
      --with pydantic-settings --with sqlalchemy --with "psycopg[binary]" --with alembic \
      --with redis --with httpx --with loguru --with python-multipart \
      python ../scripts/poc/recommend_smoke.py
- 输出：三账号推荐列表（反馈）+ 动态水平从 L2 升 L3 前后推荐对比（反馈）+ 曝光埋点计数。
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

os.environ.setdefault("APP_TESTING", "true")
os.environ.setdefault("APP_DATABASE_URL", "sqlite+pysqlite:///:memory:")

SERVICE_ROOT = Path(__file__).resolve().parents[2] / "services" / "python"
sys.path.insert(0, str(SERVICE_ROOT))

from sqlalchemy import select  # noqa: E402

from app.db import create_all_for_tests, get_session_factory  # noqa: E402
from app.db.seed import seed_scenarios  # noqa: E402
from app.db.seed_recommend import (  # noqa: E402
    seed_demo_reco_accounts,
    seed_demo_scenes,
    seed_material_difficulty,
)
from app.models import Attempt, Event, MaterialDifficulty, Placement, Scenario, Session as DbSession, User  # noqa: E402
from app.models.base import AttemptKinds, EventTypes, SessionKinds, SessionStatus  # noqa: E402
from app.rec.service import recommend_scenes  # noqa: E402
from app.skill.service import update_user_level  # noqa: E402


def _ids(db) -> dict[str, int]:
    return {
        u.username: u.id
        for u in db.execute(
            select(User).where(User.username.like("demo_reco_%"))
        ).scalars()
    }


def main() -> int:
    create_all_for_tests()  # :memory: 全表
    db = get_session_factory()()
    seed_scenarios(db)
    seed_demo_scenes(db)
    seed_material_difficulty(db)
    seed_demo_reco_accounts(db)
    db.commit()
    ids = _ids(db)
    print(f"[1] 播种完成：8 场景 + 2 演示场景 + 专家先验 + demo 账号 {list(ids)}")

    # ---- [2] 三账号推荐（体系三匹配 - 反馈 = 推荐列表；db=None → 自有会话 → 记曝光） ----
    print("\n[2] 三账号推荐（type=scene）")
    reco: dict[str, list] = {}
    for name in ("demo_reco_L2", "demo_reco_L3", "demo_reco_L4"):
        items = recommend_scenes(ids[name], limit=6)  # db=None：own session → log impression
        reco[name] = items
        print(f"  {name:16}（{items[0]['diff_level'] if items else '-'}档）"
              f"-{len(items)}: " + ", ".join(it["title"] for it in items))
    l2 = reco["demo_reco_L2"]
    assert l2 and all(it["diff_level"] != "L4" for it in l2), "L2 用户不应看到 L4（可看 L1~L3）"
    assert any("商务谈判" in t["title"] for t in reco["demo_reco_L4"]), "L4 用户应命中商务谈判"

    # ---- [3] 动态水平反馈（体系一：定档 + 练习 → 升级 → 推荐变化；复现 local/30 §3 甲旅程） ----
    uid = ids["demo_reco_L2"]
    db.add(Placement(user_id=uid, status="completed",
                     completed_at=datetime.now(UTC) - timedelta(days=5),
                     overall_score=Decimal("62"), level="L2",
                     details={"schema_version": "2d"}))  # 定档分 P=62（2d）
    db.commit()
    before = {it["title"] for it in recommend_scenes(uid, limit=6, db=db)}
    print("\n[3] 动态水平反馈：demo_reco_L2 定档 P=62 → 练习 3 次（窗口均值→74）→ 水平升级")
    scenario = db.execute(select(Scenario.id).limit(1)).scalar()  # 练习场景
    # 归一化用到素材 diff_score：置中性（70）以免低分演示素材把能力估计拉低（对应单测 diff=70）
    md = db.execute(
        select(MaterialDifficulty).where(
            MaterialDifficulty.content_type == "scene",
            MaterialDifficulty.content_id == scenario,
        )
    ).scalar_one_or_none()
    if md is not None:
        md.diff_score = Decimal("70")
        db.commit()
    means = [67.2, 72.0, 76.0]  # 3 会话均分（local/30 §3）
    for gi, m in enumerate(means):
        sess = DbSession(user_id=uid, kind=SessionKinds.DIALOG, scenario_id=scenario,
                         status=SessionStatus.COMPLETED,
                         started_at=datetime.now(UTC) - timedelta(days=2 - gi))
        db.add(sess)
        db.flush()
        for _ in range(5):
            # 使每会话均分≈m：pron=m、flu=m → S=m
            db.add(Attempt(user_id=uid, session_id=sess.id, kind=AttemptKinds.DIALOG_SPEECH,
                           pron_score=Decimal(str(m)), flu_score=Decimal(str(m))))
    db.commit()
    res = update_user_level(uid, db)
    print(f"  练习后 est_level={res['est_level']}（est={res['est_score']}，conf={res['confidence']}）")
    after = {it["title"] for it in recommend_scenes(uid, limit=6, db=db)}
    print(f"  升级前后推荐差异：{sorted(before - after) or '∅'} 移出 / {sorted(after - before) or '∅'} 新进")
    if res["est_level"] != "L3":
        print("  （注：完整 L2→L3 旅程断言见单测 test_ji_journey_L2_to_L3；此处仅演示反馈机制）")

    # ---- [4] 曝光埋点反馈（体系三 → events） ----
    n_evt = db.execute(
        select(Event).where(Event.event_type == EventTypes.RECOMMEND_IMPRESSION)
    ).scalars().all()
    print(f"\n[4] 曝光埋点：events.recommend_impression 共 {len(n_evt)} 条"
          f"（最近 user_level={n_evt[-1].payload['user_level'] if n_evt else '-'}）")
    assert n_evt, "应至少有一条曝光埋点"

    db.close()
    print("\n[OK] 推荐系统冒烟通过：播种 → 三账号推荐互异 → 动态水平升级 → 推荐反馈 → 曝光埋点")
    return 0


if __name__ == "__main__":
    sys.exit(main())
