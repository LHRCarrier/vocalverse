"""PG 集成测试安全网（docs/19 P0-2 补测① · 拍板 2026-09-07「本地安全网，CI 后续接」）。

价值：SQLite 单测覆盖不到的真实方言边界 —— JSONB 存取 / timestamptz 时区 /
`uq_reports_scope_period` 唯一约束（P0-8 幂等）/ Alembic 模型-迁移零 diff（docs/10 §7.1-6）。

运行：本地（Docker 可用）`pytest -m pg`；无 Docker/拉取失败自动 skip，不破坏默认门禁。
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.pg


@pytest.fixture(scope="module")
def pg_url():
    """启动 postgres:16-alpine 容器，返回连接 URL（含端口映射）；无 Docker 则 skip。"""
    try:
        from testcontainers.community.postgres import PostgresContainer
    except ImportError:  # testcontainers <4.14 旧路径
        from testcontainers.postgres import PostgresContainer
    try:
        with PostgresContainer("postgres:16-alpine") as pg:
            url = pg.get_connection_url()
            # 方言归一：本项目唯一驱动为 psycopg（pyproject）。testcontainers 4.14+ 返回
            # postgresql+psycopg2://（或 postgresql://），均转为 postgresql+psycopg://
            if url.startswith("postgresql+psycopg2://"):
                url = url.replace("postgresql+psycopg2://", "postgresql+psycopg://", 1)
            elif url.startswith("postgresql://"):
                url = url.replace("postgresql://", "postgresql+psycopg://", 1)
            yield url
    except Exception as exc:  # Docker daemon 不可用/镜像拉取失败等 → 安全网按可选项处理
        pytest.skip(f"Docker 不可用，PG 集成测试跳过: {exc}")


def _run_alembic(action: str) -> None:
    """在容器 URL 上执行 alembic 动作（env.py 读 APP_DATABASE_URL，docs/11 Q-A03）。"""
    from alembic import command
    from alembic.config import Config

    cfg = Config("alembic.ini")
    if action == "upgrade":
        command.upgrade(cfg, "head")
    elif action == "check":
        command.check(cfg)
    else:  # pragma: no cover
        raise ValueError(action)


class _PgEnv:
    """临时把 app 引擎/env 切到 PG（try/finally 恢复，绝不影响后续测试）。"""

    def __init__(self, url: str) -> None:
        self._url = url
        self._saved_app_env = os.environ.get("APP_DATABASE_URL")

    def __enter__(self):
        from app.core.config import get_settings

        os.environ["APP_DATABASE_URL"] = self._url
        get_settings.cache_clear()
        from app.db import reset_engine

        reset_engine()
        return self

    def __exit__(self, *exc_info):
        from app.core.config import get_settings

        if self._saved_app_env is None:
            os.environ.pop("APP_DATABASE_URL", None)
        else:
            os.environ["APP_DATABASE_URL"] = self._saved_app_env
        get_settings.cache_clear()
        from app.db import reset_engine

        reset_engine()


def test_pg_alembic_upgrade_and_check_zero_diff(pg_url) -> None:
    """docs/10 §7.1-6「M2 接 PG 首日必做」门禁：upgrade head + alembic check 零 diff。

    检查 = 模型 metadata vs PG 实际 schema（无噪音 diff 才通过；环境变量切换由 _PgEnv 保证隔离）。
    """
    with _PgEnv(pg_url):
        _run_alembic("upgrade")  # 失败即测试失败（schema 迁移必须可跑）
        _run_alembic("check")  # 零 diff：漂移（模型/迁移不同步）会在此炸出


def test_pg_full_turn_flow_and_idempotent_complete(pg_url) -> None:
    """完整回合 + P0-8 幂等 + 越权 40401 —— 全部跑在真 PG 上。

    专门抓：JSONB（interest_tags/metrics）往返、timestamptz 时区归一、唯一约束幂等
    （先查后更覆盖 `uq_reports_scope_period`，docs/10 契约）。
    """
    with _PgEnv(pg_url):
        _run_alembic("upgrade")
        from app.db import get_session_factory
        from app.main import app
        from app.models import Report, Scenario, User
        from fastapi.testclient import TestClient

        db = get_session_factory()()
        try:
            # PG 真实 FK（SQLite 测试不强制）：sessions.user_id 必须存在于 users——
            # 安全网抓到的第一类方言差异（2026-09-07）
            db.add(
                User(
                    id=1,
                    username="pguser",
                    email="pguser@test.com",
                    password_hash="x",
                    nickname="PG User",
                    role="user",
                    status="active",
                )
            )
            scenario = Scenario(
                title="PG 集成场景",
                scene_type="cafe",
                difficulty=1,
                system_prompt="You are Bella, a friendly barista.",
                opening_line="Hi there!",
                target_corpus="I'd like a coffee, please.|请给我来杯咖啡",
                interest_tags=["cafe"],
                status="published",
            )
            db.add(scenario)
            db.commit()
            sid = scenario.id
        finally:
            db.close()

        client = TestClient(app)
        auth = {"X-Test-User-Id": "1"}
        # 建会话（PG 落库 + 状态入内存后端——集成用例聚焦 DB 方言）
        r = client.post(
            "/api/v1/sessions", json={"kind": "dialog", "scenario_id": sid}, headers=auth
        )
        assert r.status_code == 200, r.text
        session_id = r.json()["data"]["id"]

        # 完整回合（Fake ASR/META/TTS → SSE）+ 首句落库
        r = client.post(
            f"/api/v1/sessions/{session_id}/turns",
            data={"action": "start"},
            headers=auth,
        )
        assert r.status_code == 200, r.text

        # P0-8：重复 complete → 同一 report_id；报告 metrics 为 JSONB、时间戳为 tz-aware
        r1 = client.post(f"/api/v1/sessions/{session_id}/complete", headers=auth)
        assert r1.status_code == 200, r1.text
        report_id = r1.json()["data"]["report_id"]
        r2 = client.post(f"/api/v1/sessions/{session_id}/complete", headers=auth)
        assert r2.status_code == 200, r2.text
        assert r2.json()["data"]["report_id"] == report_id

        db = get_session_factory()()
        try:
            report = db.get(Report, report_id)
            assert report is not None
            assert report.metrics.get("kind") == "dialog"  # JSONB 往返
            assert report.computed_at.tzinfo is not None  # timestamptz aware
            assert (
                db.execute(Report.__table__.select().where(Report.id == report_id)).fetchone()
                is not None
            )
        finally:
            db.close()

        # P0-3：他人读报告 → 40401（PG 上 JOIN 归属过滤）
        r = client.get(f"/api/v1/reports/{report_id}", headers={"X-Test-User-Id": "2"})
        assert r.status_code == 404 and r.json()["code"] == 40401, r.text
