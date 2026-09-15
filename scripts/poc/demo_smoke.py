"""M2 全链路冒烟脚本（docs/18 §7 联调）：注册态模拟 → seed → 会话 → 2 轮对话(SSE) → 报告。

- 无密钥环境跑 Fake 全链路（APP_TESTING=true 默认）；有密钥时 export APP_TESTING=false
  走真实 ASR/ISE/LLM（需 ffmpeg + whisper 模型 + .env 密钥）；
- 用法（services/python 目录）：
    uv run --no-project -p 3.12 --with fastapi --with "uvicorn[standard]" --with pydantic \
      --with pydantic-settings --with sqlalchemy --with "psycopg[binary]" --with alembic \
      --with redis --with httpx --with loguru --with python-multipart \
      python ../scripts/poc/demo_smoke.py
- 成功输出：每轮 SSE 事件摘要 + 报告 JSON；任意环节报错则非零退出。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# 测试模式默认开：无 Key/无服务依赖也能跑通全链路（CI 同款口径）
os.environ.setdefault("APP_TESTING", "true")
os.environ.setdefault("APP_DATABASE_URL", "sqlite+pysqlite:///:memory:")

SERVICE_ROOT = Path(__file__).resolve().parents[2] / "services" / "python"  # 仓库根/services/python
sys.path.insert(0, str(SERVICE_ROOT))

from app.db import create_all_for_tests, get_session_factory
from app.db.seed import seed_scenarios
from app.main import app
from fastapi.testclient import TestClient


def main() -> int:
    create_all_for_tests()
    db = get_session_factory()()
    n = seed_scenarios(db)
    db.commit()
    db.close()
    print(f"[1] 场景 seed +{n}（预期 8）")

    client = TestClient(app)
    headers = {"X-Test-User-Id": "1"}

    scenes = client.get("/api/v1/scenarios", headers=headers).json()["data"]
    print(f"[2] GET /scenarios → {len(scenes)} 套（首套：{scenes[0]['title']}）")
    sid = scenes[0]["id"]

    session = client.post(
        "/api/v1/sessions",
        json={"kind": "dialog", "scenario_id": sid},
        headers=headers,
    )
    data = session.json()["data"]
    print(f"[3] POST /sessions → id={data['id']} assigned_turns={data['assigned_turns']}")

    def turn(action: str, expected: int, with_audio: bool = True) -> list[dict]:
        form = {"action": action, "expected_turn": str(expected)}
        # ≥1KB 假音频：生产 `min_upload_bytes=1024` 下界挡空/近空录音（40002），
        # 17 字节的 b"fake-audio-bytes" 会被拒（2026-09-03 实测：回 400/40002 → 冒烟红）
        fake_audio = b"fake-audio-bytes" * 100
        files = {"audio": ("a.webm", fake_audio, "audio/webm")} if with_audio else None
        resp = client.post(
            f"/api/v1/sessions/{data['id']}/turns", data=form, files=files, headers=headers
        )
        assert resp.status_code == 200, f"turn {action} → {resp.status_code}: {resp.text[:200]}"
        events = []
        for line in resp.text.splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
        return events

    print("[4] 回合 1（normal，Fake ASR 命中语料）")
    evs = turn("normal", 0)
    kinds = [e["type"] for e in evs]
    assert {"turn_start", "text_delta", "audio_chunk", "meta_block", "turn_end"} <= set(kinds), kinds
    print("    ", " → ".join(kinds))
    hits = next(e for e in evs if e["type"] == "meta_block")["corpus_hits"]
    print(f"    覆盖度命中: {hits}")

    print("[5] 回合 2（normal）")
    evs = turn("normal", 1)
    print("    ", " → ".join(e["type"] for e in evs))

    print("[6] 结束会话（abandon → 报告）")
    evs = turn("abandon", 2, with_audio=False)
    kinds = [e["type"] for e in evs]
    assert "session_end" in kinds, kinds
    report_id = next(e for e in evs if e["type"] == "session_end")["report_id"]
    print(f"    报告 id={report_id}")

    report = client.get(f"/api/v1/reports/{report_id}", headers=headers).json()["data"]
    print(f"[7] GET /reports/{report_id} → summary={report['metrics']['summary'][:60]!r}")
    print("    coverage=", report["metrics"]["coverage"])
    print("\n[OK] 全链路冒烟通过：seed -> 场景 -> 会话 -> 2 轮 SSE -> 收尾报告")
    return 0


if __name__ == "__main__":
    sys.exit(main())
