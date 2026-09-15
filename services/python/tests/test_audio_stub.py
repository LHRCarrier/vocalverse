"""语音管线骨架接口测试（Fake 客户端打桩）。

docs/19 P0-4（2026-09-07）：四端点已挂鉴权(401)+分桶限流(429)，且**先校验后扣额度**；
测试模式经 X-Test-User-Id 直通（app/core/auth.py L63-64；conftest 提供 auth_headers）。
"""

from fastapi.testclient import TestClient

SAMPLE_WAV = b"RIFF____fake_sample_wav____"  # 程序生成即可，仅验证管线


def test_asr_stub(client: TestClient, auth_headers) -> None:
    resp = client.post(
        "/api/v1/asr",
        files={"audio": ("sample.wav", SAMPLE_WAV, "audio/wav")},
        data={"language": "en"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert "[stub]" in body["data"]["text"]


def test_asr_stub_contract_has_word_timestamps(client: TestClient, auth_headers) -> None:
    """ASR 契约（docs/06 §9.3）：词级时间戳 words + duration 反序列化（开 word_timestamps 后）。"""
    resp = client.post(
        "/api/v1/asr",
        files={"audio": ("sample.wav", SAMPLE_WAV, "audio/wav")},
        data={"language": "en"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data["words"]) == 7
    w = data["words"][0]
    assert set(w) == {"word", "start", "end", "probability"}
    assert data["duration"] == 3.2
    # 时间戳单调且与转写文本词序对应
    assert data["words"][0]["word"] == "hello"
    assert all(
        data["words"][i]["start"] <= data["words"][i + 1]["start"]
        for i in range(len(data["words"]) - 1)
    )


def test_score_stub(client: TestClient, auth_headers) -> None:
    resp = client.post(
        "/api/v1/score",
        files={"audio": ("sample.wav", SAMPLE_WAV, "audio/wav")},
        data={"reference": "hello, I would like a coffee, please."},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["overall"] == 88.0


def test_tts_stub(client: TestClient, auth_headers) -> None:
    resp = client.post("/api/v1/tts", data={"text": "hello"}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["length"] > 0


def test_upload_too_large(client: TestClient, auth_headers) -> None:
    """超过 20MB 返回 413 + 业务 41301（docs/api/error-codes.md）。"""
    big = b"x" * (21 * 1024 * 1024)
    resp = client.post(
        "/api/v1/asr",
        files={"audio": ("big.wav", big, "audio/wav")},
        headers=auth_headers,
    )
    assert resp.status_code == 413
    assert resp.json()["code"] == 41301


def test_audio_endpoints_require_auth(client: TestClient) -> None:
    """docs/19 P0-4 失败用例：无 Authorization 调 /api/v1/tts 必须 401。

    修复前（2026-09-07 复现）：无 token 直连返回 200（免费代理敞口）；
    修复后：401；其余三端点同口径（由本用例代表，避免四端重复）。
    """
    resp = client.post("/api/v1/tts", data={"text": "hello"})
    assert resp.status_code == 401, resp.text


def test_tts_empty_text_rejected(client: TestClient, auth_headers) -> None:
    """docs/19 P0-4 先校验后扣额度：空文本 422，不消耗 tts 配额。"""
    resp = client.post("/api/v1/tts", data={"text": "   "}, headers=auth_headers)
    assert resp.status_code == 422, resp.text
