"""pytest 公共夹具（docs/06 第 6 章：CI 零真实 Key；M2 全链路走 Fake + SQLite）。"""

from __future__ import annotations

import os

# —— 必须在导入 app 前设置（get_settings 为 lru_cache 单例）——
os.environ.setdefault("APP_TESTING", "true")
os.environ.setdefault("APP_DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("APP_JWT_SECRET", "vocalverse-dev-jwt-secret-0123456789abcdef")
os.environ.setdefault("APP_AUDIO_DIR", "./data/audio-test")

import shutil  # noqa: E402

import pytest  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.db import create_all_for_tests, reset_engine  # noqa: E402
from app.main import app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_db():
    """每测试函数一个全新 :memory: 库（reset_engine + create_all）。

    :memory: 与 StaticPool 共享单连接，若跨测试复用会导致自增主键/数据在测试间泄漏（如
    test_mastery 写 user_id=1，后续 test_skill 的 user 又拿 id=1 撞上其 attempts）。
    reset_engine 重建全局 engine/session_factory → 新 :memory:（docs/06 第 6 章：SQLite 单测）。
    """
    reset_engine()
    create_all_for_tests()
    # 音频目录隔离（BUG：见 worklog/BUG实测/音频残留过期410flaky.md）——
    # save_audio_bytes 对已存在文件不更新 mtime（sha1 去重），data/audio-test 残留的
    # 过期 mtime 旧文件会在 GET /audio 先判 410 并惰性删除，导致
    # test_save_audio_and_ownership 全量跑时红、单跑时绿（顺序依赖 flaky）。
    shutil.rmtree(get_settings().audio_dir, ignore_errors=True)
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
