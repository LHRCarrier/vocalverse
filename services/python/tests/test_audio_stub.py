"""语音管线骨架接口测试（Fake 客户端打桩）。"""

from fastapi.testclient import TestClient

SAMPLE_WAV = b"RIFF____fake_sample_wav____"  # 程序生成即可，仅验证管线


def test_asr_stub(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/asr",
        files={"audio": ("sample.wav", SAMPLE_WAV, "audio/wav")},
        data={"language": "en"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert "[stub]" in body["data"]["text"]


def test_score_stub(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/score",
        files={"audio": ("sample.wav", SAMPLE_WAV, "audio/wav")},
        data={"reference": "hello, I would like a coffee, please."},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["overall"] == 88.0


def test_tts_stub(client: TestClient) -> None:
    resp = client.post("/api/v1/tts", data={"text": "hello"})
    assert resp.status_code == 200
    assert resp.json()["data"]["length"] > 0


def test_upload_too_large(client: TestClient) -> None:
    """超过 20MB 返回 413 + 业务 41301（docs/api/error-codes.md）。"""
    big = b"x" * (21 * 1024 * 1024)
    resp = client.post(
        "/api/v1/asr",
        files={"audio": ("big.wav", big, "audio/wav")},
    )
    assert resp.status_code == 413
    assert resp.json()["code"] == 41301
