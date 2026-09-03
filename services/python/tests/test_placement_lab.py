"""Placement Lab 联调测试台冒烟测试（AGENTS.md rule 3：test-only 接口配套验证）。

验证：/run 用 Fake 客户端（APP_TESTING）跑出两维档位（复现真实 finalize 公式）；
联调测试台可删无影响（本测试删掉后其余套件不受影响）。
"""

from __future__ import annotations

from app.api.routes.placement_lab import router
from app.db import get_session_factory
from app.models import PlacementQuestion, User
from app.models.base import PlacementQuestionKind, Roles
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _lab_client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _seed(user_id: int) -> None:
    db = get_session_factory()()
    try:
        if db.get(User, user_id) is None:
            db.add(
                User(username=f"lab{user_id}", password_hash="x", nickname="Lab", role=Roles.USER)
            )
            db.flush()
        db.add(
            PlacementQuestion(
                exam_revision=1,
                item_index=1,
                kind=PlacementQuestionKind.READ,
                prompt="Good morning!",
                status="published",
            )
        )
        db.add(
            PlacementQuestion(
                exam_revision=1,
                item_index=2,
                kind=PlacementQuestionKind.QA,
                prompt="Tell me something about yourself.",
                reference_answer="A short intro.",
                status="published",
            )
        )
        db.commit()
    finally:
        db.close()


def test_placement_lab_run_two_dim():
    """/run 用 Fake 客户端跑出两维档位（pron 90/flu 86/completeness None → F=86 → S=88.4 → L4）。"""
    _seed(1)
    resp = _lab_client().post("/api/v1/placement-lab/run?user_id=1")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["level"] == "L4"
    assert data["total_score"] == 88.4
    assert len(data["items"]) == 2


def test_placement_lab_status_after_run():
    """/run 落 completed 后 /status 可见档位与复测冷却。"""
    _seed(1)
    client = _lab_client()
    client.post("/api/v1/placement-lab/run?user_id=1")
    resp = client.get("/api/v1/placement-lab/status?user_id=1")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["has_completed"] is True
    assert data["current_level"] == "L4"
