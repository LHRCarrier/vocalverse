"""密钥三档策略测试（docs/19 P0-9，组内拍板 2026-09-07）。

- testing：缺值回退固定测试值（CI 零真实 Key，docs/06 §5/§6）；
- development：缺值仅告警（不抛错）；
- production：缺值启动即失败（fail-fast）。
"""

from __future__ import annotations

import warnings

import pytest
from app.core.config import Settings
from pydantic import ValidationError


def test_production_missing_secret_raises() -> None:
    """production 缺 APP_JWT_SECRET/APP_SERVICE_TOKEN → 启动即失败（docs/19 P0-9）。

    显式 testing=False：pytest 进程由 conftest 注入 APP_TESTING=true（env 优先），
    不钉死会走 testing 档回退（不抛错）。
    """
    with pytest.raises(ValidationError):
        Settings(app_env="production", testing=False, jwt_secret="", service_token="")
    with pytest.raises(ValidationError):
        Settings(app_env="production", testing=False, jwt_secret="x" * 40, service_token="")


def test_development_missing_secret_only_warns() -> None:
    """development 缺值：不抛错，仅告警（本地 .env 惯例提供；缺值鉴权会失败但有明确告警）。"""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        s = Settings(app_env="development", testing=False, jwt_secret="", service_token="")
    assert s.jwt_secret == "" and s.service_token == ""
    assert any("APP_JWT_SECRET 未设置" in str(w.message) for w in caught)


def test_testing_mode_falls_back_to_test_values() -> None:
    """testing 档：缺值回退固定测试值（docs/19 P0-9；CI 零真实 Key）。"""
    s = Settings(app_env="development", testing=True, jwt_secret="", service_token="")
    assert s.jwt_secret == "vocalverse-test-jwt-secret-0123456789abcdef"
    assert s.service_token == "vocalverse-test-internal-service-token"


def test_explicit_secret_not_overridden() -> None:
    """显式提供的密钥不被三档回退覆盖（防误改）。"""
    s = Settings(app_env="production", jwt_secret="z" * 40, service_token="svc-token-0123456789")
    assert s.jwt_secret == "z" * 40
