"""X-Request-Id 透传测试（docs/06 §11）：读入回写 / 缺失自动生成。"""

from fastapi.testclient import TestClient


def test_trace_propagates_provided_id(client: TestClient) -> None:
    resp = client.get("/healthz", headers={"X-Request-Id": "trace-test-01"})
    assert resp.headers["x-request-id"] == "trace-test-01"


def test_trace_generates_when_missing(client: TestClient) -> None:
    resp = client.get("/healthz")
    assert len(resp.headers["x-request-id"]) >= 16  # uuid4.hex = 32 位
