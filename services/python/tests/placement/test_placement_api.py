"""入学测试 API 集成测试（阶段 A：两维评分 + qa 只 ASR + min_read_items 校验）。

覆盖（C1 / A2 / A3 / C11）：
- 单题评分：read 题回 ISE 三维（pron/flu/completeness）；qa 题**只 ASR**（pron=None，不耗 ISE）；
- finalize：两维 S = 0.6·发音 + 0.4·流利度（FakeScorer 下 completeness=None → F=flu）；
- 语法（LLM）fail-open：FakeLLM 回非 JSON → gram=None，不阻塞结算；
- min_read_items 校验：仅 qa（无 read）→ 42203。
"""

from __future__ import annotations

import pytest
from app.db import get_session_factory
from app.models import PlacementQuestion, User
from app.models.base import PlacementQuestionKind, Roles

FAKE_AUDIO = b"\x1aE\xdf\xa3\xa3" + b"\x00" * 4096  # 正常体积，> min_upload_bytes(1KB)


@pytest.fixture
def seeded():
    """建 1 个用户 + 1 条 read 题 + 1 条 qa 题（exam_revision=1）。"""
    db = get_session_factory()()
    try:
        user = User(username="tester", password_hash="x", nickname="T", role=Roles.USER)
        db.add(user)
        db.flush()
        read = PlacementQuestion(
            exam_revision=1,
            item_index=1,
            kind=PlacementQuestionKind.READ,
            prompt="Good morning! I would like a cup of coffee, please.",
            status="published",
        )
        qa = PlacementQuestion(
            exam_revision=1,
            item_index=2,
            kind=PlacementQuestionKind.QA,
            prompt="Tell me something about yourself.",
            reference_answer="A short self-introduction.",
            status="published",
        )
        db.add_all([read, qa])
        db.commit()
        return user.id, read.id, qa.id
    finally:
        db.close()


def _headers() -> dict[str, str]:
    return {"X-Test-User-Id": "1"}


def _score(client, item_id: int):
    return client.post(
        f"/api/v1/placement/items/{item_id}/audio",
        files={"audio": ("a.webm", FAKE_AUDIO, "audio/webm")},
        headers=_headers(),
    )


def test_qa_item_skips_ise(client, seeded):
    """qa 题只 ASR：返回 pron=None（无 ISE 分），仍回 transcript 与 attempt_id。"""
    _, read_id, qa_id = seeded
    resp = _score(client, qa_id)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["pron"] is None
    assert data["flu"] is None
    assert data["attempt_id"] is not None


def test_read_item_returns_ise_dimensions(client, seeded):
    """read 题走 ISE：回 pron/flu/completeness 三维。"""
    _, read_id, _ = seeded
    resp = _score(client, read_id)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["pron"] is not None  # FakeScorer 90
    assert data["flu"] is not None  # 86
    assert data["completeness"] is None  # FakeScorer completeness=None → F 仅 flu


def test_finalize_two_dim_level(client, seeded):
    """两维 S：A=90, F=86, S=0.6*90+0.4*86=88.4 → L4；语法 fail-open gram=None。"""
    _, read_id, qa_id = seeded
    r1 = _score(client, read_id).json()["data"]
    r2 = _score(client, qa_id).json()["data"]
    resp = client.post(
        "/api/v1/placement/finalize",
        json={"attempts": [r1["attempt_id"], r2["attempt_id"]]},
        headers=_headers(),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["total_score"] == pytest.approx(0.6 * 90.0 + 0.4 * 86.0)
    assert data["level"] == "L4"
    assert data["pron"] == pytest.approx(90.0)
    assert data["flu"] == pytest.approx(86.0)
    assert data["gram"] is None  # FakeLLM 非 JSON → fail-open


def test_finalize_requires_min_read(client, seeded):
    """无任何已评分 read 题（只做 qa）→ 422 + 42203（min_read_items=1）。"""
    _, _, qa_id = seeded
    r2 = _score(client, qa_id).json()["data"]
    resp = client.post(
        "/api/v1/placement/finalize",
        json={"attempts": [r2["attempt_id"]]},
        headers=_headers(),
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["code"] == 42203


def test_placement_records_exam_revision(client, seeded):
    """C11：placements.exam_revision 从所考题库版本写入。"""
    _, read_id, _ = seeded
    r1 = _score(client, read_id).json()["data"]
    resp = client.post(
        "/api/v1/placement/finalize",
        json={"attempts": [r1["attempt_id"]]},
        headers=_headers(),
    )
    assert resp.status_code == 200, resp.text
    db = get_session_factory()()
    try:
        from app.models import Placement

        p = db.query(Placement).filter_by(user_id=1).one()
        assert p.exam_revision == 1
        assert p.level == "L4"
        assert float(p.overall_score) == pytest.approx(88.4)
    finally:
        db.close()


def test_run_reused_across_items(client, seeded):
    """B1：同一用户的多个题目评分复用同一 in_progress run（placement_id 一致）。"""
    _, read_id, qa_id = seeded
    r1 = _score(client, read_id).json()["data"]
    r2 = _score(client, qa_id).json()["data"]
    assert r1["placement_id"] == r2["placement_id"]
    db = get_session_factory()()
    try:
        from app.models import Placement

        runs = db.query(Placement).filter_by(user_id=1, status="in_progress").all()
        assert len(runs) == 1  # 一用户仅一个 in_progress run（部分唯一索引语义）
    finally:
        db.close()


def test_finalize_idempotent(client, seeded):
    """B3：finalize 两次 —— 第二次返回同一结果，不新增 placement（幂等）。"""
    _, read_id, _ = seeded
    r1 = _score(client, read_id).json()["data"]
    first = client.post(
        "/api/v1/placement/finalize",
        json={"attempts": [r1["attempt_id"]]},
        headers=_headers(),
    ).json()["data"]
    second = client.post(
        "/api/v1/placement/finalize",
        json={"attempts": [r1["attempt_id"]]},
        headers=_headers(),
    ).json()["data"]
    assert second["placement_id"] == first["placement_id"]
    assert second["total_score"] == first["total_score"]
    assert second["level"] == first["level"]
    db = get_session_factory()()
    try:
        from app.models import Placement

        assert db.query(Placement).filter_by(user_id=1).count() == 1  # 无重复
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 阶段 C · 复测=重考（eligible/冷却/幂等）
# ---------------------------------------------------------------------------
def _complete_test(client, read_id: int) -> dict:
    """完成一次测试打分 + 收尾 → 返回 finalize 数据（须先 score 后 finalize）。"""
    r = _score(client, read_id).json()["data"]
    return client.post(
        "/api/v1/placement/finalize",
        json={"attempts": [r["attempt_id"]]},
        headers=_headers(),
    ).json()["data"]


def test_retest_requires_baseline(client, seeded):
    """C3t：无已完成定档 → POST /retest → 403 + 40302。"""
    _, _, _ = seeded
    resp = client.post("/api/v1/placement/retest", headers=_headers())
    assert resp.status_code == 403, resp.text
    assert resp.json()["code"] == 40302


def test_retest_in_cooldown(client, seeded):
    """C3t：刚完成定档（cooldown=1 天）→ 复测 → 429 + 42902。"""
    _, read_id, _ = seeded
    _complete_test(client, read_id)
    resp = client.post("/api/v1/placement/retest", headers=_headers())
    assert resp.status_code == 429, resp.text
    assert resp.json()["code"] == 42902


def test_retest_allowed_after_cooldown(client, seeded):
    """C3t：冷却过期（completed_at 回拨 2 天）→ 复测放行，返回 run 与题型快照。"""
    _, read_id, _ = seeded
    _complete_test(client, read_id)
    db = get_session_factory()()
    try:
        from datetime import UTC, datetime, timedelta

        from app.models import Placement

        p = db.query(Placement).filter_by(user_id=1, status="completed").one()
        p.completed_at = datetime.now(UTC) - timedelta(days=2)
        db.commit()
    finally:
        db.close()
    resp = client.post("/api/v1/placement/retest", headers=_headers())
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["can_start"] is True
    assert data["placement_id"] is not None
    assert len(data["questions"]) == 2  # C5：2 题迷你版（1 read + 1 QA）


def test_placement_status(client, seeded):
    """C3t：完成定档后 status 反映当前档位 + 冷却状态。"""
    _, read_id, _ = seeded
    before = client.get("/api/v1/placement/status", headers=_headers()).json()["data"]
    assert before["has_completed"] is False
    _complete_test(client, read_id)
    after = client.get("/api/v1/placement/status", headers=_headers()).json()["data"]
    assert after["has_completed"] is True
    assert after["current_level"] == "L4"
    assert after["can_retest"] is False  # 冷却期内
    assert after["cooldown_remaining_days"] >= 1


def test_skip_creates_provisional_l2(client, seeded):
    """C5 跳过：无 completed → POST /skip 建 provisional L2（skipped=True），使 40303 门禁通过。"""
    _, _, _ = seeded
    resp = client.post("/api/v1/placement/skip", headers=_headers())
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["level"] == "L2"
    assert data["skipped"] is True
    db = get_session_factory()()
    try:
        from app.models import Placement

        p = db.query(Placement).filter_by(user_id=1, status="completed").one()
        assert p.level == "L2"
        assert p.details.get("skipped") is True
    finally:
        db.close()


def test_skip_idempotent(client, seeded):
    """C5 跳过幂等：skip 两次不重复建档。"""
    _, _, _ = seeded
    first = client.post("/api/v1/placement/skip", headers=_headers()).json()["data"]
    second = client.post("/api/v1/placement/skip", headers=_headers()).json()["data"]
    assert first["placement_id"] == second["placement_id"]
    db = get_session_factory()()
    try:
        from app.models import Placement

        assert db.query(Placement).filter_by(user_id=1).count() == 1
    finally:
        db.close()


def test_skip_does_not_block_retest(client, seeded):
    """C5：skip（provisional）不计复测冷却 —— 跳过后可立即 retest。"""
    _, _, _ = seeded
    client.post("/api/v1/placement/skip", headers=_headers())
    resp = client.post("/api/v1/placement/retest", headers=_headers())
    assert resp.status_code == 200, resp.text  # 无 42902（skip 不计冷却）
    assert resp.json()["data"]["can_start"] is True
