"""唱歌模块容器层全链路复测（2026-09-10 复测轮 · 真容器 + 真 PG/Redis + 真 pyin）。

与 `local/sing_e2e_test.py`（v4 时代的端到端脚本）的分工：本脚本面向**本轮 P0/P1 修复**，
逐条给出容器级证据：

- 契约（P1-14）：`/openapi.json` 含具名 DTO；`/songs`、结果端点的**响应键集合 == DTO 字段**；
- 选歌/详情/收藏（含跨用户隔离与幂等）；
- 主链路：建会话 → 上传 → 轮询 → 结果（v5 口径、逐句、alignment、`bpm_source` 四值）；
- 回放归属（本人 200 / 他人 40301 / 无 token 401）+ **P0-1**：参考旋律素材 age > 24h 仍可播且未被删；
- 幂等（同会话重复上传同 attempt）+ **P1-3**：PG 直插重复 `(user_id, session_id)` 被唯一键拒绝；
- 边界：40101 / 40401 / 40905 / 40002 / 41302 / **41301（python 与 nginx 两条路径）**；
- **P1-13**：Redis 桶置满 → 429 + 42901 + `Retry-After`，且**另一桶未被扣**（Redis 回滚路径）；
- 长歌（`--long`）：175s 音频端到端计时（**P1-11**：降采样后不应再是 ~50s 的整首 DTW 病态耗时）。

用法（仓库根）：
    uv run python scripts/sing_container_test.py            # 主流程（约 2~5 分钟）
    uv run python scripts/sing_container_test.py --long      # 追加 175s 长歌用例（+3~6 分钟）
"""

from __future__ import annotations

import base64
import json
import subprocess
import sys
import time
import uuid
import wave
from pathlib import Path

import httpx

PY = "http://localhost:8000"  # python-api 直连
JAVA = "http://localhost:8080"
WEB = "http://localhost:8088"  # nginx（web 容器）
ROOT = Path(__file__).resolve().parents[1]
LONG_MODE = "--long" in sys.argv
SERVICE_TOKEN = "change-me-internal-service-token"  # .env SERVICE_TOKEN（本地演示值）
ISE_LIMIT = 30  # APP_ISE_RATE_PER_HOUR（docs/06 §7）

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" —— {detail}" if detail else ""), flush=True)
    return ok


def dck(*args: str) -> subprocess.CompletedProcess:
    """在仓库根执行 docker compose 子命令（psql/redis-cli 断言用）。"""
    return subprocess.run(
        ["docker", "compose", *args], cwd=ROOT, capture_output=True, text=True, check=False
    )


def jwt_sub(token: str) -> int:
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return int(json.loads(base64.urlsafe_b64decode(payload))["sub"])


def register(username: str) -> tuple[str, int]:
    body = {"username": username, "nickname": "复测", "password": "Test123456!"}
    with httpx.Client(base_url=JAVA, timeout=15) as jc:
        jc.post("/auth/register", json=body)
        login = jc.post("/auth/login", json={"username": username, "password": "Test123456!"})
    data = login.json()
    data = data.get("data", data)
    token = data.get("accessToken") or data.get("access_token")
    assert token, login.text
    return token, jwt_sub(token)


def wav_bytes(seconds: float, *, silent: bool = False) -> bytes:
    """合成 wav（默认 440Hz 正弦；silent=True 为长静音，用于时长边界）。"""
    import io

    import numpy as np
    import soundfile as sf

    sr = 16000
    t = np.linspace(0, seconds, int(sr * seconds), endpoint=False)
    data = np.zeros_like(t) if silent else 0.5 * np.sin(2 * np.pi * 440 * t)
    buf = io.BytesIO()
    sf.write(buf, data.astype("float32"), sr, format="WAV")
    return buf.getvalue()


def gapped_fixture(line_bounds_s: list[float], *, gap_s: float = 0.3) -> bytes:
    """生成"有换气"的跟唱素材：参考旋律降 3 半音 + 慢 18.9%（一次重采样）+ 句间插静音。

    为什么需要它：仓库自带 `sing_test_user.wav` 是**连奏**素材（静音占比 0.2%、最长静音 0.03s），
    在新口径 v5 的逐句起唱判据下每句都是 `no_onset` → 节奏维度整体为 None（见报告「发现 1」）。
    本素材在句间插入 300ms 静音 → 每句都是"新起唱" → 用来**正向**验证节奏通路真的能算分。
    """
    import io

    import numpy as np
    import soundfile as sf

    ref = ROOT / "data/audio/song_twinkle.wav"
    y, sr = sf.read(str(ref))
    if y.ndim > 1:
        y = y.mean(axis=1)
    target_sr = int(round(sr * 1.189))  # 写入后按 16k 播放 → 降 3 半音 + 慢 18.9%
    idx = np.arange(0, len(y), sr / target_sr)
    up = np.interp(idx, np.arange(len(y)), y)
    bounds = [0, *[int(round(t * target_sr)) for t in line_bounds_s], len(up)]
    gap = np.zeros(int(round(gap_s * target_sr)))
    segs = []
    for i in range(len(bounds) - 1):
        segs.append(up[bounds[i] : bounds[i + 1]])
        if i < len(bounds) - 2:
            segs.append(gap)
    out = np.concatenate(segs)
    buf = io.BytesIO()
    sf.write(buf, out.astype("float32"), sr, format="WAV")
    return buf.getvalue()


def main() -> int:
    owner_token, owner_id = register(f"sing_rt_{uuid.uuid4().hex[:8]}")
    other_token, _ = register(f"sing_rt_{uuid.uuid4().hex[:8]}")
    H = {"Authorization": f"Bearer {owner_token}"}
    HO = {"Authorization": f"Bearer {other_token}"}
    print(f"owner uid={owner_id}\n")

    # ---------------- A. 契约（P1-14） ----------------
    spec = httpx.get(f"{PY}/openapi.json", timeout=20).json()
    schemas = spec.get("components", {}).get("schemas", {})
    check(
        "P1-14 契约含具名 DTO（AttemptResult/SingAlignment/SubmitAck/SongDetail）",
        all(k in schemas for k in ("AttemptResult", "SingAlignment", "SubmitAck", "SongDetail")),
        f"共 {len(schemas)} 个 schema",
    )
    bpm_union = schemas.get("SingAlignment", {}).get("properties", {}).get("bpm_source", {})
    enum = bpm_union.get("anyOf") or bpm_union.get("enum") or []
    flat = json.dumps(enum)
    check(
        "P1-14 bpm_source 四值闭合（前端联合类型来源）",
        all(v in flat for v in ("onset-f0", "onset-flux", "onset-arbitrated", "duration")),
        flat[:120],
    )
    ref = spec["paths"]["/api/v1/sing/attempts/{attempt_id}"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"].get("$ref", "")
    check("P1-14 结果端点响应引用 Envelope_AttemptResult_", "AttemptResult" in ref, ref)

    # ---------------- B. 选歌 / 详情 / 收藏 ----------------
    with httpx.Client(base_url=PY, timeout=30) as c:
        songs = c.get("/api/v1/songs", headers=H).json()["data"]
        check(
            "歌曲列表 ≥3 首且全部 ready",
            len(songs) >= 3 and all(s["pitch_ref_status"] == "ready" for s in songs),
            str([(s["id"], s["pitch_ref_status"]) for s in songs]),
        )
        keys = set(songs[0])
        check(
            "列表响应键 == SongSummary DTO",
            keys == set(schemas["SongSummary"]["properties"]),
            f"diff={keys ^ set(schemas['SongSummary']['properties'])}",
        )
        song_id = songs[0]["id"]
        detail = c.get(f"/api/v1/songs/{song_id}", headers=H).json()["data"]
        check(
            "详情逐句参考 f0s 非空",
            all((line.get("pitch_ref") or {}).get("f0s") for line in detail["lines"]),
            f"{len(detail['lines'])} 句",
        )
        check(
            "详情响应键 == SongDetail DTO",
            set(detail) == set(schemas["SongDetail"]["properties"]),
            f"diff={set(detail) ^ set(schemas['SongDetail']['properties'])}",
        )

        fav = c.put(f"/api/v1/songs/{song_id}/favorite", headers=H).json()["data"]
        check("收藏 PUT → favorited=true", fav.get("favorited") is True, str(fav))
        fav2 = c.put(f"/api/v1/songs/{song_id}/favorite", headers=H).json()["data"]
        check("收藏幂等（重复 PUT 仍 true）", fav2.get("favorited") is True, str(fav2))
        other_view = [
            s for s in c.get("/api/v1/songs", headers=HO).json()["data"] if s["id"] == song_id
        ]
        check(
            "收藏跨用户隔离",
            other_view and other_view[0]["favorited"] is False,
            str(other_view[:1]),
        )
        un = c.delete(f"/api/v1/songs/{song_id}/favorite", headers=H).json()["data"]
        check("取消收藏 DELETE → false", un.get("favorited") is False, str(un))

        # ---------------- C. 主链路 ----------------
        sess = c.post("/api/v1/sessions", headers=H, json={"kind": "sing", "song_id": song_id})
        sid = sess.json()["data"]["id"]
        # 主链路用**面向本曲的跟唱素材**（整体低 3 半音 / 慢 18.9% / 晚起唱 0.5s）——
        # 440Hz 单音只能验证管道跑通，分数必然很低（覆盖率不足 → overall=None，属合法口径）
        fixture = ROOT / "local/sing_test_user.wav"
        audio = fixture.read_bytes() if fixture.exists() else wav_bytes(6.0)
        t0 = time.time()
        up = c.post(
            f"/api/v1/sessions/{sid}/audio",
            headers=H,
            files={"audio": ("rt.wav", audio, "audio/wav")},
        )
        ack = up.json().get("data", {})
        check(
            "上传受理 200 且回执仅 {attempt_id,status}",
            up.status_code == 200 and set(ack) == {"attempt_id", "status"},
            up.text[:160],
        )
        attempt = ack.get("attempt_id")
        status = "?"
        for _ in range(150):
            status = c.get(f"/api/v1/sing/attempts/{attempt}/status", headers=H).json()["data"][
                "status"
            ]
            if status in ("done", "failed"):
                break
            time.sleep(2)
        elapsed = time.time() - t0
        check("短曲评分完成（done）", status == "done", f"status={status} 耗时={elapsed:.1f}s")
        r = c.get(f"/api/v1/sing/attempts/{attempt}", headers=H).json()["data"]
        check(
            "结果响应键 == AttemptResult DTO",
            set(r) == set(schemas["AttemptResult"]["properties"]),
            f"diff={set(r) ^ set(schemas['AttemptResult']['properties'])}",
        )
        check(
            "scoring_version=v6 / ref_version=pyin-v2",
            r["scoring_version"] == "v6" and r["ref_version"] == "pyin-v2",
            f"{r['scoring_version']} / {r['ref_version']}",
        )
        align = r["alignment"]
        check(
            "alignment.method=v3",
            align.get("method") == "dtw-local-sakoe-chiba-v3",
            str(align.get("method")),
        )
        check(
            "bpm_source ∈ 四值闭合集",
            align.get("bpm_source") in ("onset-f0", "onset-flux", "onset-arbitrated", "duration"),
            str(align.get("bpm_source")),
        )
        evaluated = [line for line in r["lines"] if not line.get("skipped")]
        check(
            "参与评分的句均含 user_f0 + cent_dev",
            bool(evaluated)
            and all(line.get("user_f0") and "cent_dev" in line for line in evaluated),
            f"有效句 {len(evaluated)}/{len(r['lines'])}",
        )
        check(
            "综合分与音准/发音落库（连奏素材：多数句按 v6 判 no_onset 属预期）",
            all(r.get(k) is not None for k in ("overall", "pitch", "pron")),
            f"overall={r['overall']} pitch={r['pitch']} rhythm={r['rhythm']} pron={r['pron']}",
        )
        no_onset = [line for line in r["lines"] if line.get("reason") == "no_onset"]
        check(
            "v5/v6 逐句起唱判据：连奏素材多数句 reason=no_onset 且 rhythm=None（负向）",
            len(no_onset) >= len(r["lines"]) - 1
            and all(line.get("rhythm_score") is None for line in no_onset),
            f"{len(no_onset)}/{len(r['lines'])} 句 no_onset",
        )
        check(
            "音准 ≥65（移调补偿 + 命中率衰减生效）",
            (r.get("pitch") or 0) >= 65,
            f"pitch={r['pitch']}",
        )
        check(
            "有效句覆盖率 ≥0.8 且不给 None 综合分（口径 v5.1）",
            (r["alignment"].get("user_coverage") or 0) >= 0.8,
            f"cov={r['alignment'].get('user_coverage')} conf={r['alignment'].get('coverage_conf')}",
        )
        print(
            f"    概览 overall={r['overall']} pitch={r['pitch']} rhythm={r['rhythm']} "
            f"pron={r['pron']} expected={r['expected_lines']}\n"
        )

        # ---------------- D. 回放归属 + P0-1 素材保护 ----------------
        name = r["audio_url"].rsplit("/", 1)[-1]
        check("本人录音回放 200", c.get(f"/api/v1/audio/{name}", headers=H).status_code == 200)
        foreign = c.get(f"/api/v1/audio/{name}", headers=HO)
        check(
            "他人录音回放 → 403/40301",
            foreign.status_code == 403 and foreign.json().get("code") == 40301,
            foreign.text[:120],
        )
        check("无 token 回放 → 401", c.get(f"/api/v1/audio/{name}").status_code == 401)
        # 参考旋律素材（song_*.wav）age > 24h：P0-1 修复后必须 200 且文件仍在
        asset = (detail.get("audio_url") or "").rsplit("/", 1)[-1]
        asset_resp = c.get(f"/api/v1/audio/{asset}", headers=H)
        check(
            "P0-1 参考旋律素材可播（age>24h 未被 TTL 删除）",
            asset_resp.status_code == 200 and len(asset_resp.content) > 1000,
            f"HTTP {asset_resp.status_code} bytes={len(asset_resp.content)} asset={asset}",
        )
        ls = dck("exec", "-T", "python-api", "sh", "-c", f"ls -l /app/data/audio/{asset}")
        check("P0-1 素材文件仍存在", "song_" in ls.stdout, ls.stdout.strip()[:100])

        # ---------------- D2. 节奏维度正向（换气素材 → 非 no_onset） ----------------
        bounds = [4.94, 9.88, 14.82, 19.76, 24.7]  # song 1 的 LRC 句界（参考时间轴，秒）
        with httpx.Client(base_url=PY, timeout=120) as c2:
            sid_r = c2.post(
                "/api/v1/sessions", headers=H, json={"kind": "sing", "song_id": song_id}
            ).json()["data"]["id"]
            gap_audio = gapped_fixture(bounds)
            up_r = c2.post(
                f"/api/v1/sessions/{sid_r}/audio",
                headers=H,
                files={"audio": ("gapped.wav", gap_audio, "audio/wav")},
            )
            a_r = up_r.json().get("data", {}).get("attempt_id")
            status_r = "?"
            for _ in range(150):
                status_r = c2.get(f"/api/v1/sing/attempts/{a_r}/status", headers=H).json()["data"][
                    "status"
                ]
                if status_r in ("done", "failed"):
                    break
                time.sleep(2)
            r_r = c2.get(f"/api/v1/sing/attempts/{a_r}", headers=H).json().get("data", {})
            scored = [line for line in r_r.get("lines", []) if line.get("rhythm_score") is not None]
            check(
                "节奏维度正向：句间换气 → 起唱检出并计分",
                status_r == "done" and len(scored) >= 4 and r_r.get("rhythm") is not None,
                f"status={status_r} 计分句={len(scored)}/{len(r_r.get('lines', []))} "
                f"rhythm={r_r.get('rhythm')} overall={r_r.get('overall')}",
            )

        # ---------------- E. 幂等 + P1-3 数据层 ----------------
        up2 = c.post(
            f"/api/v1/sessions/{sid}/audio",
            headers=H,
            files={"audio": ("rt.wav", audio, "audio/wav")},
        )
        check(
            "同会话重复上传幂等（同 attempt_id）",
            up2.json()["data"]["attempt_id"] == attempt,
            up2.text[:120],
        )
        row = dck(
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            "vocalverse",
            "-d",
            "vocalverse",
            "-tAc",
            f"select user_id, session_id, song_id from sing_attempts where id={attempt}",
        ).stdout.strip()
        uid, sid_db, song_db = [x.strip() for x in row.split("|")]
        dup = dck(
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            "vocalverse",
            "-d",
            "vocalverse",
            "-c",
            "insert into sing_attempts "
            "(user_id, session_id, song_id, duration_s, is_complete, lines, alignment, scoring_version) "
            f"values ({uid}, {sid_db}, {song_db}, 1, false, '[]'::jsonb, '{{}}'::jsonb, 'v5')",
        )
        check(
            "P1-3 PG 唯一键拒绝重复 (user_id, session_id)",
            "uq_sing_attempts_user_session" in (dup.stderr + dup.stdout),
            (dup.stderr or dup.stdout).strip().splitlines()[-1][:140]
            if (dup.stderr or dup.stdout)
            else "",
        )

        # ---------------- F. 边界 ----------------
        check(
            "无 token 轮询 → 401/40101",
            c.get(f"/api/v1/sing/attempts/{attempt}/status").status_code == 401,
        )
        foreign_attempt = c.get(f"/api/v1/sing/attempts/{attempt}/status", headers=HO)
        check(
            "他人 attempt → 404/40401",
            foreign_attempt.status_code == 404 and foreign_attempt.json()["code"] == 40401,
            foreign_attempt.text[:100],
        )

        # 40905：内部 REST 把 song 3 置 missing → 建会话必须 40905 → 复原 ready
        target_song = songs[-1]["id"]
        flip = httpx.post(
            f"{JAVA}/internal/song/{target_song}/pitch-status",
            json={"songId": target_song, "status": "missing", "version": None},
            headers={"Authorization": f"Bearer {SERVICE_TOKEN}"},
            timeout=15,
        )
        not_ready = c.post(
            "/api/v1/sessions", headers=H, json={"kind": "sing", "song_id": target_song}
        )
        ok_40905 = not_ready.status_code == 409 and not_ready.json().get("code") == 40905
        httpx.post(
            f"{JAVA}/internal/song/{target_song}/pitch-status",
            json={"songId": target_song, "status": "ready", "version": "pyin-v2"},
            headers={"Authorization": f"Bearer {SERVICE_TOKEN}"},
            timeout=15,
        )
        check(
            "参考旋律未就绪 → 40905",
            ok_40905,
            f"flip={flip.status_code} resp={not_ready.status_code} {not_ready.text[:100]}",
        )

        sid_b = c.post(
            "/api/v1/sessions", headers=H, json={"kind": "sing", "song_id": song_id}
        ).json()["data"]["id"]
        tiny = c.post(
            f"/api/v1/sessions/{sid_b}/audio",
            headers=H,
            files={"audio": ("t.wav", b"RIFF0000WAVE", "audio/wav")},
        )
        check(
            "过短音频 → 40002",
            tiny.status_code == 400 and tiny.json().get("code") == 40002,
            tiny.text[:120],
        )

        sid_c = c.post(
            "/api/v1/sessions", headers=H, json={"kind": "sing", "song_id": song_id}
        ).json()["data"]["id"]
        long_resp = c.post(
            f"/api/v1/sessions/{sid_c}/audio",
            headers=H,
            files={"audio": ("long.wav", wav_bytes(200, silent=True), "audio/wav")},
        )
        check(
            "超 180s → 413/41302",
            long_resp.status_code == 413 and long_resp.json().get("code") == 41302,
            long_resp.text[:120],
        )

        # 41301：>20MB（python 中间件 + nginx 边缘两条路径）
        big = b"RIFF" + b"\x00" * (int(20.5 * 1024 * 1024))
        sid_d = c.post(
            "/api/v1/sessions", headers=H, json={"kind": "sing", "song_id": song_id}
        ).json()["data"]["id"]
        too_big = c.post(
            f"/api/v1/sessions/{sid_d}/audio",
            headers=H,
            files={"audio": ("big.wav", big, "audio/wav")},
        )
        check(
            "体量超限（直连 8000）→ 413/41301",
            too_big.status_code == 413 and too_big.json().get("code") == 41301,
            too_big.text[:120],
        )

    # 经 nginx 的两级体量：① 应用层上限（20MB 音频）→ 41301；② 网关层上限（65m）→ @err413 envelope。
    # 注意必须用**新会话**：同会话已有定稿 attempt 时，端点会先命中幂等分支直接返回结果（P1-3 语义），
    # 根本读不到 body，也就不会触发体积校验（早期脚本用固定 session 1，合并 main 后即出现假绿）。
    with httpx.Client(base_url=PY, timeout=120) as c3:
        sid_e = c3.post(
            "/api/v1/sessions", headers=H, json={"kind": "sing", "song_id": song_id}
        ).json()["data"]["id"]
        big_nginx = httpx.post(
            f"{WEB}/api/v1/sessions/{sid_e}/audio",
            headers={"Authorization": f"Bearer {owner_token}"},
            files={"audio": ("big.wav", b"RIFF" + b"\x00" * (int(23 * 1024 * 1024)), "audio/wav")},
            timeout=120,
        )
        check(
            "体量超限（经 nginx 8088 → 应用层）→ 413 + 41301 envelope",
            big_nginx.status_code == 413
            and big_nginx.headers.get("content-type", "").startswith("application/json")
            and big_nginx.json().get("code") == 41301,
            f"HTTP {big_nginx.status_code} body={big_nginx.text[:100]}",
        )
    # 网关层：> 65m 由 nginx `client_max_body_size` 拦截，且必须是 JSON envelope（非 HTML 错误页）
    huge_nginx = httpx.post(
        f"{WEB}/api/v1/sessions/{sid_e}/audio",
        headers={"Authorization": f"Bearer {owner_token}"},
        files={"audio": ("huge.wav", b"RIFF" + b"\x00" * (int(66 * 1024 * 1024)), "audio/wav")},
        timeout=180,
    )
    check(
        "网关层体量超限（>65m，经 nginx）→ 413 + JSON envelope",
        huge_nginx.status_code == 413
        and huge_nginx.headers.get("content-type", "").startswith("application/json")
        and huge_nginx.json().get("code") == 41301,
        f"HTTP {huge_nginx.status_code} body={huge_nginx.text[:100]}",
    )

    # ---------------- G. P1-13 多桶限流（Redis 回滚路径） ----------------
    win = int(time.time() // 3600)
    dck(
        "exec",
        "-T",
        "redis",
        "redis-cli",
        "set",
        f"rl:ise:{owner_id}:{win}",
        str(ISE_LIMIT),
        "ex",
        "7200",
    )
    dck("exec", "-T", "redis", "redis-cli", "del", f"rl:sing:{owner_id}:{win}")
    with httpx.Client(base_url=PY, timeout=60) as c:
        sid_e = c.post(
            "/api/v1/sessions", headers=H, json={"kind": "sing", "song_id": song_id}
        ).json()["data"]["id"]
        limited = c.post(
            f"/api/v1/sessions/{sid_e}/audio",
            headers=H,
            files={"audio": ("rt.wav", audio, "audio/wav")},
        )
        body = (
            limited.json()
            if limited.headers.get("content-type", "").startswith("application/json")
            else {}
        )
        check(
            "ISE 桶满 → 429/42901 + Retry-After",
            limited.status_code == 429
            and body.get("code") == 42901
            and int(limited.headers.get("Retry-After", "0")) >= 1,
            f"HTTP {limited.status_code} code={body.get('code')} RA={limited.headers.get('Retry-After')}",
        )
    sing_cnt = dck(
        "exec", "-T", "redis", "redis-cli", "get", f"rl:sing:{owner_id}:{win}"
    ).stdout.strip()
    check(
        "P1-13 被拒请求不消耗 sing 桶（Redis 回滚生效）",
        sing_cnt in ("", "0", "(nil)") or int(sing_cnt or 0) == 0,
        f"rl:sing={sing_cnt!r}",
    )
    dck(
        "exec",
        "-T",
        "redis",
        "redis-cli",
        "del",
        f"rl:ise:{owner_id}:{win}",
        f"rl:sing:{owner_id}:{win}",
    )

    # ---------------- H. 前端真形态（nginx + 构建产物） ----------------
    page = httpx.get(f"{WEB}/m/sing", timeout=20)
    check(
        "GET /m/sing 返回 SPA（200）",
        page.status_code == 200 and '<div id="app"' in page.text,
        f"HTTP {page.status_code}",
    )
    dist = dck(
        "exec", "-T", "web", "sh", "-c", "ls /usr/share/nginx/html/assets | grep -i mobilesing"
    )
    check(
        "构建产物含 MobileSingView 分包（真形态已打包）",
        "MobileSingView" in dist.stdout,
        dist.stdout.strip()[:120] or dist.stderr.strip()[:120],
    )

    # ---------------- I. P1-11 长歌（可选） ----------------
    if LONG_MODE:
        with httpx.Client(base_url=PY, timeout=120) as c:
            sid_l = c.post(
                "/api/v1/sessions", headers=H, json={"kind": "sing", "song_id": song_id}
            ).json()["data"]["id"]
            payload = wav_bytes(175.0)
            print(f"    长歌上传 {len(payload) / 1e6:.1f}MB（175s）…", flush=True)
            t0 = time.time()
            up_l = c.post(
                f"/api/v1/sessions/{sid_l}/audio",
                headers=H,
                files={"audio": ("long175.wav", payload, "audio/wav")},
            )
            a_l = up_l.json().get("data", {}).get("attempt_id")
            status = "?"
            for _ in range(450):
                status = c.get(f"/api/v1/sing/attempts/{a_l}/status", headers=H).json()["data"][
                    "status"
                ]
                if status in ("done", "failed"):
                    break
                time.sleep(2)
            cost = time.time() - t0
            r_l = c.get(f"/api/v1/sing/attempts/{a_l}", headers=H).json().get("data", {})
            check(
                "P1-11 175s 长歌评分完成（容器未 OOM）",
                status == "done",
                f"status={status} 总耗时={cost:.1f}s overall={r_l.get('overall')}",
            )
            print(f"    长歌耗时明细：上传+评分总 {cost:.1f}s（P1-11 修复前仅整首 DTW 就 ~48s）")

    ok = all(x[1] for x in RESULTS)
    print(f"\n===== 汇总：{sum(1 for x in RESULTS if x[1])}/{len(RESULTS)} PASS =====")
    for name, passed, detail in RESULTS:
        if not passed:
            print(f"  FAIL: {name} —— {detail}")
    return 0 if ok else 1


if __name__ == "__main__":
    import contextlib

    with contextlib.suppress(BrokenPipeError):
        raise SystemExit(main())
