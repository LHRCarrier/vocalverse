"""真环境联调检查（docs/18 §7）：Java JWT 签发 → Python 验签互通 + 真实 ASR/TTS 回合。

前置（均已在本机启动）：
- postgres/redis 容器（docker compose up -d postgres redis）
- Python 8000（APP_TESTING=false：whisper/edge-tts 真实现；LLM/ISE 缺钥自动 Fake）
- Java 8080（含 demoadult 演示账号播种）

流程：登录(Java) → 场景列表(Python, 真 JWT) → 创建会话 → 上传真实语音 → SSE 回合
（真 whisper 转写 + 真 edge-tts 音频）→ 音频回放鉴权 → 报告 → 埋点 10 类 → SQL 四指标核对。
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import httpx

PY = "http://127.0.0.1:8000"
JV = "http://127.0.0.1:8080"
SPEECH = Path(__file__).parent / "poc_speech_15s.mp3"
SEED_USER = "demoadult"
SEED_PASS = "demo123456"


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'OK' if cond else 'FAIL'}] {label} {detail}")
    if not cond:
        raise SystemExit(f"联调失败于: {label}")


def login() -> str:
    r = httpx.post(
        f"{JV}/manage/auth/login",
        json={"username": SEED_USER, "password": SEED_PASS},
        timeout=10,
    )
    check(f"Java 登录 {SEED_USER}", r.status_code == 200, f"http={r.status_code}")
    token = r.json()["data"]["accessToken"]
    # 顺带验证 me（JWT 回验）
    me = httpx.get(f"{JV}/manage/auth/me", headers={"Authorization": f"Bearer {token}"})
    check("Java /me", me.status_code == 200 and me.json()["data"]["username"] == SEED_USER)
    return token


def main() -> int:
    if not SPEECH.exists():
        print("缺少测试语音，先运行: uv run --with edge-tts python scripts/poc/whisper_rtf.py --speech")
        return 1

    print("[1] 登录与 JWT（Java 8080）")
    token = login()
    headers = {"Authorization": f"Bearer {token}"}

    print("[2] Python 验签互通（真 JWT → /api/v1/scenarios）")
    r = httpx.get(f"{PY}/api/v1/scenarios", headers=headers, timeout=10)
    check("Python 接受 Java JWT", r.status_code == 200, f"http={r.status_code}")
    scenes = r.json()["data"]
    check("场景 8 套", len(scenes) == 8, f"got={len(scenes)}")
    sid = scenes[0]["id"]
    print(f"     首场景: {scenes[0]['title']}")

    print("[3] 创建会话")
    r = httpx.post(
        f"{PY}/api/v1/sessions",
        json={"kind": "dialog", "scenario_id": sid},
        headers=headers,
        timeout=10,
    )
    check("POST /sessions", r.status_code == 200)
    session_id = r.json()["data"]["id"]

    print("[4] 真实语音回合（whisper 转写 + edge-tts 合成 + Fake LLM）")
    t0 = time.perf_counter()
    audio = SPEECH.read_bytes()
    r = httpx.post(
        f"{PY}/api/v1/sessions/{session_id}/turns",
        data={"action": "normal", "expected_turn": "0"},
        files={"audio": ("speech.mp3", audio, "audio/mpeg")},
        headers=headers,
        timeout=120,
    )
    check("POST /turns 200", r.status_code == 200, f"http={r.status_code}")
    first_sound = None
    events: list[dict] = []
    for line in r.text.splitlines():
        if line.startswith("data: "):
            ev = json.loads(line[6:])
            events.append(ev)
            if ev["type"] == "text_delta" and first_sound is None:
                first_sound = time.perf_counter()
    kinds = [e["type"] for e in events]
    check("SSE 事件完备", {"text_delta", "audio_chunk", "meta_block", "turn_end"} <= set(kinds),
          " → ".join(kinds))
    total_ms = (time.perf_counter() - t0) * 1000
    print(f"     回合总耗时 {total_ms:.0f}ms（语音时长约 {len(audio)/16000:.1f}s 等效）")
    hits = next(e for e in events if e["type"] == "meta_block")["corpus_hits"]
    print(f"     覆盖度命中（真转写）: {hits}")

    print("[5] 音频回放鉴权（真实 edge-tts 产物）")
    url = next(e for e in events if e["type"] == "audio_chunk")["url"]
    ar = httpx.get(f"{PY}{url}", headers=headers)
    check("GET /audio 200 且有内容", ar.status_code == 200 and len(ar.content) > 1000,
          f"http={ar.status_code} {len(ar.content)}B")
    # 越权：错误 token（伪造）→ 401
    bad = httpx.get(f"{PY}{url}", headers={"Authorization": "Bearer not-a-jwt"})
    check("越权拒绝", bad.status_code in (401, 403), f"http={bad.status_code}")

    print("[6] 收尾与报告")
    r = httpx.post(
        f"{PY}/api/v1/sessions/{session_id}/complete",
        headers=headers,
        timeout=60,
    )
    check("POST complete", r.status_code == 200)
    report_id = r.json()["data"]["report_id"]
    rr = httpx.get(f"{PY}/api/v1/reports/{report_id}", headers=headers)
    report = rr.json()["data"]
    check("报告可取", rr.status_code == 200 and "attempts" in report["metrics"])
    transcript = str(report["metrics"]["attempts"][0].get("transcript") or "")
    print(f"     真转写文本: {transcript[:120]!r} ...")
    check("真 ASR 完整转写（含 practice）", "practice" in transcript.lower(),
          f"got={transcript[:80]!r}")
    print(f"     summary={report['metrics']['summary'][:50]!r}")

    print("[7] 埋点（模拟前端事件）与 SQL 四指标核对")
    now = int(time.time())
    for i, name in enumerate(
        ["page_view", "scene_start", "recording_start", "recording_complete", "score_event",
         "corpus_hit", "practice_complete", "fun_action", "fun_action", "score_event"]
    ):
        httpx.post(
            f"{PY}/api/v1/events",
            json={"event_type": name, "client_event_id": f"it-{now}-{i}", "occurred_at": now,
                  "scene_id": sid, "payload": {"action": "demo" if name == "fun_action" else None}},
            headers=headers,
            timeout=10,
        )
    # SQL 核对（psql 容器内查）
    sql = (
        "select event_type, count(*) from events where occurred_at >= now() - interval '1 hour' "
        "group by event_type order by event_type;"
    )
    out = subprocess.run(
        ["docker", "compose", "exec", "-T", "postgres", "psql", "-U", "vocalverse", "-d", "vocalverse",
         "-c", sql],
        capture_output=True, text=True, cwd=str(Path(__file__).resolve().parents[2]),
    )
    print(out.stdout.strip()[-600:] if out.stdout else out.stderr[-300:])
    check("埋点落库", "corpus_hit" in out.stdout and "practice_complete" in out.stdout)

    print("\n[OK] 真环境联调通过：JWT 互通 -> 真 ASR/TTS 回合 -> 音频鉴权 -> 报告 -> 埋点核对")
    return 0


if __name__ == "__main__":
    sys.exit(main())
