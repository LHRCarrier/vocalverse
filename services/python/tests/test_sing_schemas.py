"""唱歌端点响应契约测试（P1-14：response_model 补齐 + 键集合不漂移）。

**修复前必失败**（两条）：
1. `test_singing_endpoints_declare_response_schema`：请求前 OpenAPI 里这些端点 200 响应**无 schema**
   （`responses.200.content` 为空）→ `pnpm gen:api` 生成的 TS 类型无内容 → 前端只能手写 DTO，
   契约漂移无人拦（实测 `alignment.bpm_source` 前端写成 `'onset' | 'duration'`，后端实际四值）。
2. `test_attempt_result_keys_match_schema` / `test_song_summary_keys_match_schema`：把响应体逐键
   与 DTO 字段对齐（多键=前端类型少字段；少键=前端类型骗人）。

另覆盖 `SingAlignment(extra="allow")`：口径升级新增的诊断键必须原样透传（响应模型不做过滤）。
"""

from __future__ import annotations

import uuid
from typing import Any

from app.models import Lrc, Session, SingAttempt, Song, SongPitchRef
from app.models.base import ContentStatus, PitchRefStatus
from app.sing.schemas import (
    AttemptResult,
    AttemptStatus,
    FavoriteState,
    SongDetail,
    SongSummary,
    SubmitAck,
)
from fastapi.testclient import TestClient

# 端点 → (HTTP 方法, 期望 envelope 内的 DTO)
_ENDPOINTS: list[tuple[str, str, type]] = [
    ("/api/v1/songs", "get", SongSummary),
    ("/api/v1/songs/{song_id}", "get", SongDetail),
    ("/api/v1/songs/{song_id}/favorite", "put", FavoriteState),
    ("/api/v1/songs/{song_id}/favorite", "delete", FavoriteState),
    ("/api/v1/sessions/{session_id}/audio", "post", SubmitAck),
    ("/api/v1/sing/attempts/{attempt_id}/status", "get", AttemptStatus),
    ("/api/v1/sing/attempts/{attempt_id}", "get", AttemptResult),
]


def _headers(uid: int) -> dict[str, str]:
    return {"X-Test-User-Id": str(uid)}


def _new_db():
    from app.db import get_session_factory

    return get_session_factory()()


def _seed(db) -> tuple[int, int, int]:
    """建 user/song/lrc/ref 与一条已定稿 attempt；返回 (user_id, song_id, attempt_id)。"""
    from app.models import User

    user = User(
        username=f"schema_{uuid.uuid4().hex[:8]}", email=None, password_hash="x", nickname="U"
    )
    db.add(user)
    db.flush()
    song = Song(
        title="Twinkle",
        level=1,
        duration_s=120,
        bpm=100,
        musical_key="C",
        audio_url="/data/audio/twinkle.wav",
        status=ContentStatus.PUBLISHED,
        pitch_ref_status=PitchRefStatus.READY,
    )
    db.add(song)
    db.flush()
    lrc = Lrc(
        song_id=song.id,
        seq=1,
        offset_ms=0,
        end_offset_ms=3000,
        line_text="twinkle",
    )
    db.add(lrc)
    db.flush()
    db.add(
        SongPitchRef(
            lrc_id=lrc.id,
            start_ms=0,
            end_ms=3000,
            pitch_ref={
                "f0s": [440.0] * 3,
                "notes": ["A4"] * 3,
                "midi": [69] * 3,
                "onsets_ms": [0.0],
            },
            version="pyin-v2",
        )
    )
    sess = Session(user_id=user.id, kind="sing", song_id=song.id, assigned_turns=3)
    db.add(sess)
    db.flush()
    attempt = SingAttempt(
        user_id=user.id,
        session_id=sess.id,
        song_id=song.id,
        duration_s=120,
        is_complete=True,
        expected_lines=1,
        overall_score=80.0,
        pitch_score=80.0,
        rhythm_score=80.0,
        pron_score=80.0,
        scoring_version="v5",
        ref_version="pyin-v2",
        lines=[
            {
                "seq": 1,
                "start_ms": 0,
                "end_ms": 3000,
                "pitch_score": 80.0,
                "rhythm_score": 80.0,
                "pron_score": 80.0,
                "synced": True,
                "skipped": False,
                "reason": None,
                "ref_seq": 1,
                "no_ref": False,
                "onset_dev_ms": 120.0,
                "note_hit_rate": 0.9,
                "user_f0": [[0.0, 440.0]],
                "cent_dev": [0.0],
            }
        ],
        # 未来口径的诊断键（模拟"评分侧新增留痕字段"）：响应必须原样带出
        alignment={
            "bpm_ratio": 1.0,
            "bpm_source": "duration",
            "offset_ms": 0.0,
            "method": "dtw-local-sakoe-chiba-v3",
            "version": "v5",
            "breath_structure": True,
            "future_diag_key": 42,
        },
    )
    db.add(attempt)
    db.commit()
    return int(user.id), int(song.id), int(attempt.id)


def test_singing_endpoints_declare_response_schema():
    """P1-14：每个唱歌端点的 200 响应必须引用**具名 DTO**（修复前为空 schema `{}`）。"""
    from app.main import app

    spec = app.openapi()
    for path, method, dto in _ENDPOINTS:
        responses = spec["paths"][path][method]["responses"]
        content = responses["200"].get("content")
        assert content, f"{method.upper()} {path} 响应无 content/schema（P1-14 回归）"
        ref = content["application/json"]["schema"].get("$ref", "")
        assert dto.__name__ in ref, (
            f"{method.upper()} {path} 响应 schema 未引用 {dto.__name__}：{ref}"
        )
        # DTO 自身必须在 components 里可展开（否则前端生成的类型是 empty object）
        name = ref.rsplit("/", 1)[-1]
        props = spec["components"]["schemas"][name]["properties"]
        assert "data" in props, f"{name} 缺 data（envelope 契约）"


def test_song_summary_keys_match_schema(client: TestClient):
    """响应键集合 == DTO 字段集合（多键=前端类型少字段；少键=类型骗人）。"""
    db = _new_db()
    try:
        uid, song_id, _ = _seed(db)
    finally:
        db.close()

    listed = client.get("/api/v1/songs", headers=_headers(uid)).json()["data"][0]
    assert set(listed) == set(SongSummary.model_fields), listed
    detail = client.get(f"/api/v1/songs/{song_id}", headers=_headers(uid)).json()["data"]
    assert set(detail) == set(SongDetail.model_fields), detail
    assert set(detail["lines"][0]) == {"seq", "start_ms", "end_ms", "text", "pitch_ref"}
    assert set(detail["lines"][0]["pitch_ref"]) == {"f0s", "notes", "midi", "onsets_ms"}


def test_sing_attempt_keys_and_alignment_passthrough(client: TestClient):
    """结果端点逐键对齐 DTO；`alignment` 未知键（未来诊断字段）必须透传。"""
    db = _new_db()
    try:
        uid, _song_id, attempt_id = _seed(db)
    finally:
        db.close()

    resp = client.get(f"/api/v1/sing/attempts/{attempt_id}", headers=_headers(uid))
    assert resp.status_code == 200, resp.text
    data: dict[str, Any] = resp.json()["data"]
    assert set(data) == set(AttemptResult.model_fields), data
    assert set(data["lines"][0]) == set(
        AttemptResult.model_fields["lines"].annotation.__args__[0].model_fields
    )
    # extra="allow"：新增口径字段不得被响应模型吞掉（否则前端"字段时有时无"）
    assert data["alignment"]["future_diag_key"] == 42
    assert data["alignment"]["bpm_source"] == "duration"

    status = client.get(f"/api/v1/sing/attempts/{attempt_id}/status", headers=_headers(uid)).json()[
        "data"
    ]
    assert set(status) == set(AttemptStatus.model_fields), status


def test_favorite_endpoint_keys_match_schema(client: TestClient):
    """收藏端点响应键 == FavoriteState（PUT/DELETE 同构）。"""
    db = _new_db()
    try:
        uid, song_id, _ = _seed(db)
    finally:
        db.close()

    for method in ("put", "delete"):
        data = getattr(client, method)(
            f"/api/v1/songs/{song_id}/favorite", headers=_headers(uid)
        ).json()["data"]
        assert set(data) == set(FavoriteState.model_fields), data
