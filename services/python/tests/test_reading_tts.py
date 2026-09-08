"""读书域 · 听书路由与编排测试（Fake TTS：APP_TESTING → get_reading_tts_client 自动 Fake；
docs/46 B-3 缓存分目录 / B-4 只扣真实合成 / SSE 事件契约 golden 单边）。"""

from __future__ import annotations

import json

import pytest
from app.db import get_session_factory
from app.models import Book, BookChapter, TtsTask
from app.reading import orchestrator
from sqlalchemy import select


@pytest.fixture()
def chapter_seed():
    with get_session_factory()() as session:
        book = Book(title="TTS Book", author="Tester", level="L1", chapter_count=1)
        session.add(book)
        session.flush()
        content = "One. Two. Three. Four."
        chapter = BookChapter(
            book_id=book.id,
            chapter_no=1,
            title="Chapter 1",
            content=content,
            content_version=1,
            word_count=4,
            char_count=len(content),
        )
        session.add(chapter)
        session.commit()
        return {"book_id": book.id, "chapter_id": chapter.id}


def _read_events(resp):
    """SSE 响应 → ReadingStreamEvent 列表（跨块解析简化版：逐行 data:）。"""
    events = []
    for raw in resp.iter_lines():
        line = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)
        if line and line.startswith("data: "):
            events.append(json.loads(line[6:]))
    return events


class TestSegment:
    def test_segment_first_request_synthesizes(self, client, auth_headers, chapter_seed):
        cid = chapter_seed["chapter_id"]
        resp = client.get(f"/api/v1/reading/chapters/{cid}/tts/segment/0", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.headers.get("content-type", "").startswith("audio/mpeg")
        assert resp.headers.get("x-tts-provider") == "edge"
        assert resp.content.startswith(b"RIFF__fake")

    def test_segment_cache_hit_second_call(self, client, auth_headers, chapter_seed):
        cid = chapter_seed["chapter_id"]
        client.get(f"/api/v1/reading/chapters/{cid}/tts/segment/0", headers=auth_headers)
        resp2 = client.get(f"/api/v1/reading/chapters/{cid}/tts/segment/0", headers=auth_headers)
        assert resp2.status_code == 200
        assert resp2.headers.get("x-tts-cache") == "hit"

    def test_segment_bad_idx_404(self, client, auth_headers, chapter_seed):
        resp = client.get(
            f"/api/v1/reading/chapters/{chapter_seed['chapter_id']}/tts/segment/99",
            headers=auth_headers,
        )
        assert resp.status_code == 404

    def test_word_pronounce(self, client, auth_headers):
        resp = client.get("/api/v1/reading/tts/word/invention", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.content.startswith(b"RIFF__fake")


class TestPrepare:
    def test_sse_event_sequence(self, client, auth_headers, chapter_seed):
        cid = chapter_seed["chapter_id"]
        with client.stream(
            "POST",
            f"/api/v1/reading/chapters/{cid}/tts/prepare",
            headers=auth_headers,
            data={"voice": "en-US-JennyNeural", "rate": "+0%"},
        ) as resp:
            assert resp.status_code == 200
            events = _read_events(resp)
        types = [e["type"] for e in events]
        assert types[0] == "task_start"
        assert "sentence_progress" in types
        assert types[-1] == "task_done"
        task_id = events[0]["task_id"]
        assert events[0]["total"] == 4
        # 快照兜底（GET /tts/tasks/{id}）
        snap = client.get(f"/api/v1/reading/tts/tasks/{task_id}", headers=auth_headers)
        assert snap.status_code == 200
        assert snap.json()["data"]["status"] in ("done", "failed")
        assert snap.json()["data"]["total"] == 4

    def test_running_task_conflict_409(self, client, auth_headers, chapter_seed):
        """running 复用语义：先手动造一个 running 任务 → prepare 409（docs/45 §5.2）。"""
        cid = chapter_seed["chapter_id"]
        with get_session_factory()() as session:
            session.add(
                TtsTask(
                    user_id=1,
                    book_id=chapter_seed["book_id"],
                    chapter_id=cid,
                    voice="en-US-JennyNeural",
                    rate="+0%",
                    provider="edge",
                    status="running",
                    total=4,
                    done=1,
                    failed_count=0,
                )
            )
            session.commit()
        resp = client.post(
            f"/api/v1/reading/chapters/{cid}/tts/prepare",
            headers=auth_headers,
            data={"voice": "en-US-JennyNeural", "rate": "+0%"},
        )
        assert resp.status_code == 409

    def test_snapshot_endpoint_ownership(self, client, auth_headers, chapter_seed):
        cid = chapter_seed["chapter_id"]
        with get_session_factory()() as session:
            task = TtsTask(
                user_id=1,
                book_id=chapter_seed["book_id"],
                chapter_id=cid,
                voice="v",
                rate="+0%",
                provider="edge",
                status="done",
                total=1,
                done=1,
            )
            session.add(task)
            session.commit()
            tid = task.id
        resp = client.get(f"/api/v1/reading/tts/tasks/{tid}", headers={"X-Test-User-Id": "2"})
        assert resp.status_code == 404  # 越权按不存在处理


class TestWorker:
    def test_sweep_orphans(self, chapter_seed):
        with get_session_factory()() as session:
            session.add(
                TtsTask(
                    user_id=1,
                    book_id=chapter_seed["book_id"],
                    chapter_id=chapter_seed["chapter_id"],
                    voice="v",
                    rate="+0%",
                    provider="edge",
                    status="running",
                    total=1,
                )
            )
            session.add(
                TtsTask(
                    user_id=1,
                    book_id=chapter_seed["book_id"],
                    chapter_id=chapter_seed["chapter_id"],
                    voice="v",
                    rate="+0%",
                    provider="edge",
                    status="done",
                    total=1,
                    done=1,
                )
            )
            session.commit()
        assert orchestrator.sweep_orphans() == 1
        with get_session_factory()() as session:
            rows = list(session.scalars(select(TtsTask)).all())
            running = [r for r in rows if r.status == "running"]
            assert running == []
            failed = [r for r in rows if r.status == "failed"]
            assert len(failed) == 1
            assert failed[0].error["reason"] == "orphan_sweep"
