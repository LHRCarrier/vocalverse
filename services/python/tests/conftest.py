"""pytest 公共夹具（docs/06 第 6 章：CI 零真实 Key）。"""

from __future__ import annotations

import pytest
from app.core.config import get_settings
from app.main import app
from fastapi.testclient import TestClient


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def settings():
    return get_settings()
