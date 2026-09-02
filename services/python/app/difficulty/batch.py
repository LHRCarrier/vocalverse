"""素材难度专家规则批量标定（local/28 §2.3 · local/31 §2.2）。

- ``compute_scenario_features``：解析 target_corpus → 专家先验（三维度 + λ 聚合）；
- ``upsert_scenarios``：批量写 ``material_difficulty``（source='expert' + features 落库）；
- CLI：``python -m app.difficulty.batch --json data/seed/scenarios.json``（打印）
        ``python -m app.difficulty.batch --db``（读库 published 场景并 upsert）。

写方唯一性：只写 **Python 拥有**的 material_difficulty；不写 scenarios.difficulty（Java 内容方）。
"""

from __future__ import annotations

import argparse
import json
import logging
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

from app.core.config import get_settings
from app.db import get_session_factory
from app.difficulty.rules import scenario_prior
from app.models import MaterialDifficulty, Scenario

logger = logging.getLogger("vocalverse")


def parse_corpus(target_corpus: str) -> list[str]:
    """target_corpus：每行 'English|中文'，取英文段（local/28 口径）。"""
    out: list[str] = []
    for line in (target_corpus or "").splitlines():
        line = line.strip()
        if not line:
            continue
        eng = line.split("|", 1)[0].strip()
        if eng:
            out.append(eng)
    return out


def compute_scenario_features(
    title: str, target_corpus: str, owner_diff: int | None, lam: float = 0.5
) -> dict:
    """场景专家先验；返回可落 features JSONB 的字典。"""
    lines = parse_corpus(target_corpus)
    r = scenario_prior(lines, lam=lam)
    fb = {1: "L1", 2: "L2", 3: "L3", 4: "L4"}.get(owner_diff, "L1") if owner_diff else None
    return {
        "title": title,
        "lines": lines,
        "per_line": r["per_line"],
        "dims": r["dims"],
        "prior_score": r["prior"],
        "diff_level": r["level"],
        "pending_review": bool(fb and _band_gap(r["level"], fb) >= 2),
        "owner_level": fb,
    }


def _band_gap(a: str, b: str) -> int:
    idx = {"L1": 0, "L2": 1, "L3": 2, "L4": 3}
    return abs(idx.get(a, 0) - idx.get(b, 0))


def upsert_scenarios(db, features_list: list[dict], version: str = "expert-v1") -> int:
    """批量 upsert material_difficulty（difficulty_source='expert'）。返回处理条数。"""
    n = 0
    for f in features_list:
        row = db.execute(
            select(MaterialDifficulty).where(
                MaterialDifficulty.content_type == "scene",
                MaterialDifficulty.content_id == f["_content_id"],
            )
        ).scalar_one_or_none()
        if row is None:
            row = MaterialDifficulty(
                content_type="scene", content_id=f["_content_id"], version=version
            )
            db.add(row)
        row.diff_score = Decimal(str(f["prior_score"]))
        row.diff_level = f["diff_level"]
        row.difficulty_source = "expert"
        row.prior_score = Decimal(str(f["prior_score"]))
        row.features = {
            "dims": f["dims"],
            "weights": {"vocab": 0.4, "syntax": 0.2, "pron": 0.4},
            "lambda": 0.5,
            "lines": f["per_line"],
            "pending_review": f["pending_review"],
            "owner_level": f["owner_level"],
        }
        n += 1
    # 不在此 COMMIT——由调用方统一提交（batch.main --db / seed_recommend 各管各自事务）
    return n


def _load_json(path: str) -> list[dict]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data["scenarios"]


def main(argv: list[str] | None = None) -> int:
    cfg = get_settings()
    ap = argparse.ArgumentParser(description="素材难度专家规则批量标定")
    ap.add_argument("--json", help="读 seed JSON（离线演示，不落库）")
    ap.add_argument(
        "--db", action="store_true", help="读库 published 场景并 upsert material_difficulty"
    )
    args = ap.parse_args(argv)

    if args.json:
        feats = []
        for s in _load_json(args.json):
            feats.append(
                compute_scenario_features(s["title"], s["target_corpus"], s.get("difficulty"))
            )
        print(
            f"{'场景':<20}{'词汇':>6}{'句法':>6}{'发音':>6}{'先验':>7}{'档':>4}  (初评 / pending)"
        )
        for f in feats:
            print(
                f"{f['title'][:18]:<20}{f['dims']['vocab']:>6}{f['dims']['syntax']:>6}"
                f"{f['dims']['pron']:>6}{f['prior_score']:>7}{f['diff_level']:>4}  "
                f"({f['owner_level']} / {'⚠' if f['pending_review'] else ''})"
            )
        return 0

    if args.db:
        db = get_session_factory()()
        try:
            scenarios = db.execute(select(Scenario).where(Scenario.status == "published")).scalars()
            feats = []
            for s in scenarios:
                c = compute_scenario_features(
                    s.title, s.target_corpus, s.difficulty, lam=cfg.material_difficulty_lambda
                )
                c["_content_id"] = int(s.id)
                feats.append(c)
            n = upsert_scenarios(db, feats)
            db.commit()
            logger.info("batch_calculate_difficulty --db upsert %s scenes", n)
            print(f"upsert {n} 条 material_difficulty（content_type='scene', source='expert'）")
            return 0
        finally:
            db.close()

    ap.error("need --json or --db")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
