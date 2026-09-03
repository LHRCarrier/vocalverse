"""流利度特征测试台（test-only）可用性 + 无影响验证（docs/06 §9.3）。

- 默认关闭：路由未注册 → 404，/openapi.json 无 fluency-preview（契约快照零影响）；
- 开启态：本地 FastAPI 挂载路由（monkeypatch 环境），Fake ASR → 特征 → 演示载荷。
"""

from __future__ import annotations

from app.api.routes.fluency_preview import router
from fastapi import FastAPI
from fastapi.testclient import TestClient

FAKE_AUDIO = b"fake-audio-bytes" * 128


def test_fluency_preview_disabled_returns_404(client) -> None:
    """默认 fluency_preview_enabled=False：路由未注册 → 404（对其它代码零影响）。"""
    r = client.post("/api/v1/fluency-preview/analyze", files={"audio": ("a.webm", FAKE_AUDIO)})
    assert r.status_code == 404
    schemas = client.get("/openapi.json").json()
    assert "/api/v1/fluency-preview" not in schemas["paths"]  # include_in_schema=False


def _mounted_client() -> TestClient:
    app = FastAPI()
    app.include_router(router)  # 测试内挂载，模拟开启态（不影响全局 app 的 404 断言）
    return TestClient(app)


def test_analyze_endpoint_features_with_fake_asr() -> None:
    """开启态：Fake ASR（词级时间戳）→ 特征与演示载荷（wpm>0、停顿 1 次）。"""
    c = _mounted_client()
    r = c.post(
        "/api/v1/fluency-preview/analyze",
        files={"audio": ("a.webm", FAKE_AUDIO, "audio/webm")},
        data={"reference": "hello, I would like a coffee, please."},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["code"] == 0
    data = body["data"]
    assert "[stub]" in data["text"]
    assert data["duration_s"] == 3.2
    assert len(data["words"]) == 7
    f = data["features"]
    assert f["wpm"] > 100 and f["pause_count"] == 1 and f["long_pause_count"] == 1
    # 演示载荷与报告同构（service.py metrics.attempts 条目键）
    demo = data["attempt_demo"]
    assert demo["transcript"] == data["text"]
    assert demo["wpm"] == f["wpm"]
    assert demo["fluency_features"] == f
    # 参考文本非空 → FakeScorer 出分
    assert data["score"]["overall"] == 88.0


def test_analyze_without_reference_skips_score() -> None:
    c = _mounted_client()
    r = c.post(
        "/api/v1/fluency-preview/analyze",
        files={"audio": ("a.webm", FAKE_AUDIO, "audio/webm")},
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["score"] is None
    assert data["score_ref"] is None


def test_analyze_uses_transcript_as_reference_when_flag_on() -> None:
    """use_transcript_ref=true：无手动参考时用 ASR 转写喂 ISE（生产对话同款转写对转写）。"""
    c = _mounted_client()
    r = c.post(
        "/api/v1/fluency-preview/analyze",
        files={"audio": ("a.webm", FAKE_AUDIO, "audio/webm")},
        data={"use_transcript_ref": "true"},
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["score"] is not None
    assert data["score_ref"] == "transcript"
    assert data["score"]["overall"] == 88.0  # FakeScorer 固定分


def test_manual_reference_takes_priority_over_transcript_flag() -> None:
    """手动 reference 优先于 use_transcript_ref（题卡原文 > 转写对转写）。"""
    c = _mounted_client()
    r = c.post(
        "/api/v1/fluency-preview/analyze",
        files={"audio": ("a.webm", FAKE_AUDIO, "audio/webm")},
        data={"reference": "Hello there.", "use_transcript_ref": "true"},
    )
    assert r.status_code == 200
    assert r.json()["data"]["score_ref"] == "manual"
