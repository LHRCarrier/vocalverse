"""SSE 事件协议 golden 校验（va-arch-04：单语料、双端断言）。

共享语料 ``tests/fixtures/sse_event_cases.json`` 由事件模型生成（v1）：
- 本测试断言：后端 pydantic 模型重建 + ``sse_payload`` 序列化 == 语料 payload（字节级）；
- 前端 ``sse-protocol-golden.test.ts`` 同读该文件，断言 ``parseSseBuffer`` 解析 == 语料 event；
  任何一边漂移（字段改名/加字段/序列化差异）→ 单边 CI 红，契约漂移在合并前暴露。
"""

from __future__ import annotations

import json
from pathlib import Path

from app.practice import events as ev

_CASES = json.loads(
    (Path(__file__).parent / "fixtures" / "sse_event_cases.json").read_text(encoding="utf-8")
)


def _build(name: str, event: dict):
    cls = {
        "turn_start": ev.TurnStart,
        "user_transcript": ev.UserTranscript,
        "text_delta": ev.TextDelta,
        "audio_chunk_plain": ev.AudioChunk,
        "audio_chunk_with_duration": ev.AudioChunk,
        "meta_block_min": ev.MetaBlock,
        "meta_block_full": ev.MetaBlock,
        "score_delta": ev.ScoreDelta,
        "error": ev.StreamError,
        "turn_end_authoritative": ev.TurnEnd,
        "turn_end_legacy_no_expected": ev.TurnEnd,
        "turn_end_with_words": ev.TurnEnd,
        "session_end": ev.SessionEnd,
    }[name]
    return cls(**event)


def test_golden_serialization_matches_fixture() -> None:
    for case in _CASES["cases"]:
        payload = ev.sse_payload(_build(case["name"], case["event"]))
        assert payload == case["payload"], f"序列化漂移: {case['name']}"


def test_golden_parse_roundtrip() -> None:
    """解析侧回环：语料 event → 模型重建 → 再序列化（与语料 payload 同字节）。"""
    for case in _CASES["cases"]:
        rebuilt = ev.sse_payload(_build(case["name"], case["event"]))
        assert rebuilt == case["payload"], f"roundtrip 漂移: {case['name']}"


def test_golden_exclude_none_semantics() -> None:
    """exclude_none 语义固化：未设置的可选字段（duration/expected_turn/words/…）不出现在载荷。"""
    plain = next(c for c in _CASES["cases"] if c["name"] == "audio_chunk_plain")
    assert "duration" not in plain["event"]
    legacy = next(c for c in _CASES["cases"] if c["name"] == "turn_end_legacy_no_expected")
    assert "expected_turn" not in legacy["event"]
    assert "words" not in legacy["event"]  # B4：无词时字段缺省（旧端安全忽略）
    authoritative = next(c for c in _CASES["cases"] if c["name"] == "turn_end_authoritative")
    assert authoritative["event"]["expected_turn"] == 1
    with_words = next(c for c in _CASES["cases"] if c["name"] == "turn_end_with_words")
    assert with_words["event"]["words"][0] == {
        "word": "I'd",
        "start": 0.12,
        "end": 0.36,
        "probability": 0.99,
    }
