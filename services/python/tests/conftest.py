"""pytest 公共夹具（docs/06 第 6 章：CI 零真实 Key；M2 全链路走 Fake + SQLite）。"""

from __future__ import annotations

import os

# —— 必须在导入 app 前设置（get_settings 为 lru_cache 单例）——
os.environ.setdefault("APP_TESTING", "true")
os.environ.setdefault("APP_DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("APP_JWT_SECRET", "vocalverse-dev-jwt-secret-0123456789abcdef")
os.environ.setdefault("APP_AUDIO_DIR", "./data/audio-test")

import pytest  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.db import create_all_for_tests  # noqa: E402
from app.main import app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _create_schema():
    """会话级：SQLite 建全表（测试用 create_all，生产走 Alembic——docs/10 §7）。"""
    create_all_for_tests()
    yield


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """测试模式直通认证（docs/18：X-Test-User-Id 仅 APP_TESTING 生效）。"""
    return {"X-Test-User-Id": "1"}


@pytest.fixture
def settings():
    return get_settings()
