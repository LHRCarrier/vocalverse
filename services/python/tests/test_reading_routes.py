"""读书域 · 路由测试（TestClient + X-Test-User-Id 直通认证；docs/45 §4 契约）。"""

from __future__ import annotations

import pytest
from app.db import get_session_factory
from app.models import Book, BookChapter, DictionaryEntry, DictionaryForm


@pytest.fixture()
def reading_seed():
    with get_session_factory()() as session:
        book = Book(title="Demo Book", author="Tester", level="L1", chapter_count=1)
        session.add(book)
        session.flush()
        content = "Alice knew it was only a dream. The inventions amazed her!"
        chapter = BookChapter(
            book_id=book.id,
            chapter_no=1,
            title="Chapter 1",
            content=content,
            content_version=1,
            word_count=8,
            char_count=len(content),
        )
        session.add(chapter)
        session.flush()
        entry = DictionaryEntry(
            word="invention",
            phonetic="in'venʃәn",
            translation="n. 发明",
            exchange={"s": "inventions"},
            frequency=4773,
        )
        session.add(entry)
        session.flush()
        session.add(DictionaryForm(form="inventions", entry_id=entry.id))
        session.commit()
        return {"book_id": book.id, "chapter_id": chapter.id}


class TestBooks:
    def test_list_books(self, client, auth_headers, reading_seed):
        resp = client.get("/api/v1/reading/books", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        assert body["data"]["items"][0]["title"] == "Demo Book"

    def test_book_detail(self, client, auth_headers, reading_seed):
        resp = client.get(f"/api/v1/reading/books/{reading_seed['book_id']}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["chapters"][0]["chapter_no"] == 1

    def test_book_not_found_45001(self, client, auth_headers, reading_seed):
        resp = client.get("/api/v1/reading/books/99999", headers=auth_headers)
        assert resp.status_code == 404
        assert resp.json()["code"] == 45001

    def test_unauthorized(self, client, reading_seed):
        resp = client.get("/api/v1/reading/books")
        assert resp.status_code == 401


class TestChapter:
    def test_chapter_with_sentences(self, client, auth_headers, reading_seed):
        resp = client.get(
            f"/api/v1/reading/chapters/{reading_seed['chapter_id']}", headers=auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["content_version"] == 1
        assert len(data["paragraphs"]) == 1
        sentences = data["sentences"]
        assert sentences[0]["idx"] == 0
        # 坐标系契约：content[start:end] == text
        assert data["content"][sentences[0]["start"] : sentences[0]["end"]] == sentences[0]["text"]


class TestLookup:
    def test_lookup_hit(self, client, auth_headers, reading_seed):
        resp = client.post(
            "/api/v1/reading/lookup", headers=auth_headers, json={"word": "inventions"}
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["word"] == "invention"
        assert data["translation"].startswith("n.")
        assert data["in_vocab"] is False

    def test_lookup_miss_45003(self, client, auth_headers, reading_seed):
        resp = client.post(
            "/api/v1/reading/lookup", headers=auth_headers, json={"word": "zzzzunknown"}
        )
        assert resp.status_code == 404
        assert resp.json()["code"] == 45003

    def test_lookup_invalid_45002(self, client, auth_headers, reading_seed):
        resp = client.post("/api/v1/reading/lookup", headers=auth_headers, json={"word": "123"})
        assert resp.status_code == 422
        assert resp.json()["code"] == 45002


class TestVocab:
    def test_add_and_list_and_delete(self, client, auth_headers, reading_seed):
        resp = client.post(
            "/api/v1/reading/vocab",
            headers=auth_headers,
            json={
                "word": "inventions",
                "book_id": reading_seed["book_id"],
                "chapter_id": reading_seed["chapter_id"],
                "context": "The inventions amazed her!",
            },
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["added"] is True
        assert data["vocab"]["word"] == "invention"
        # 幂等：二次 added=false
        resp2 = client.post(
            "/api/v1/reading/vocab",
            headers=auth_headers,
            json={"word": "invention"},
        )
        assert resp2.json()["data"]["added"] is False
        # 列表
        resp3 = client.get("/api/v1/reading/vocab", headers=auth_headers)
        assert resp3.status_code == 200
        assert len(resp3.json()["data"]["items"]) == 1
        vocab_id = resp3.json()["data"]["items"][0]["id"]
        # 状态更新
        resp4 = client.patch(
            f"/api/v1/reading/vocab/{vocab_id}", headers=auth_headers, json={"status": "known"}
        )
        assert resp4.json()["data"]["status"] == "known"
        # 删除
        resp5 = client.delete(f"/api/v1/reading/vocab/{vocab_id}", headers=auth_headers)
        assert resp5.json()["data"]["deleted"] is True
        assert (
            len(client.get("/api/v1/reading/vocab", headers=auth_headers).json()["data"]["items"])
            == 0
        )

    def test_vocab_ownership(self, client, auth_headers, reading_seed):
        client.post("/api/v1/reading/vocab", headers=auth_headers, json={"word": "dream"})
        items = client.get("/api/v1/reading/vocab", headers=auth_headers).json()["data"]["items"]
        vid = items[0]["id"]
        resp = client.delete(f"/api/v1/reading/vocab/{vid}", headers={"X-Test-User-Id": "2"})
        assert resp.status_code == 404  # 越权按不存在处理（docs/06 §11 口径）

    def test_add_vocab_scene_community(self, client, auth_headers, reading_seed):
        """社区划词来源（docs/47 §5.5）：scene 入参必须落库并回带。"""
        resp = client.post(
            "/api/v1/reading/vocab",
            headers=auth_headers,
            json={"word": "wonderful", "context": "A wonderful post!", "scene": "community"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["vocab"]["scene"] == "community"
        items = client.get("/api/v1/reading/vocab", headers=auth_headers).json()["data"]["items"]
        assert items[0]["scene"] == "community"

    def test_add_vocab_default_scene_is_reading(self, client, auth_headers, reading_seed):
        resp = client.post("/api/v1/reading/vocab", headers=auth_headers, json={"word": "dream"})
        assert resp.json()["data"]["vocab"]["scene"] == "reading"

    def test_add_vocab_invalid_scene_45002(self, client, auth_headers, reading_seed):
        resp = client.post(
            "/api/v1/reading/vocab",
            headers=auth_headers,
            json={"word": "dream", "scene": "hacking"},
        )
        assert resp.status_code == 422
        assert resp.json()["code"] == 45002


class TestAnnotations:
    def test_crud(self, client, auth_headers, reading_seed):
        chapter_id = reading_seed["chapter_id"]
        resp = client.post(
            "/api/v1/reading/annotations",
            headers=auth_headers,
            json={
                "kind": "highlight",
                "chapter_id": chapter_id,
                "start_offset": 0,
                "end_offset": 5,
                "text": "Alice",
                "color": "#fbbf24",
                "sentence_idx": 0,
            },
        )
        assert resp.status_code == 200
        ann = resp.json()["data"]
        assert ann["kind"] == "highlight"
        resp2 = client.get(
            f"/api/v1/reading/annotations?chapter_id={chapter_id}", headers=auth_headers
        )
        assert len(resp2.json()["data"]["items"]) == 1
        resp3 = client.patch(
            f"/api/v1/reading/annotations/{ann['id']}", headers=auth_headers, json={"note": "伏笔"}
        )
        assert resp3.json()["data"]["note"] == "伏笔"
        resp4 = client.delete(f"/api/v1/reading/annotations/{ann['id']}", headers=auth_headers)
        assert resp4.json()["data"]["deleted"] is True

    def test_offset_out_of_range_45004(self, client, auth_headers, reading_seed):
        resp = client.post(
            "/api/v1/reading/annotations",
            headers=auth_headers,
            json={
                "kind": "note",
                "chapter_id": reading_seed["chapter_id"],
                "start_offset": 5,
                "end_offset": 2,
                "text": "x",
            },
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == 45004


class TestProgress:
    def test_put_get(self, client, auth_headers, reading_seed):
        bid = reading_seed["book_id"]
        cid = reading_seed["chapter_id"]
        resp = client.put(
            f"/api/v1/reading/progress/{bid}",
            headers=auth_headers,
            json={"chapter_id": cid, "char_offset": 42},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["char_offset"] == 42
        resp2 = client.get(f"/api/v1/reading/progress/{bid}", headers=auth_headers)
        assert resp2.json()["data"]["chapter_id"] == cid
        # 书/章不匹配 → 45001
        resp3 = client.put(
            "/api/v1/reading/progress/99999",
            headers=auth_headers,
            json={"chapter_id": cid, "char_offset": 0},
        )
        assert resp3.status_code == 404
        assert resp3.json()["code"] == 45001


class TestVoices:
    def test_voices_always_has_edge(self, client, auth_headers):
        resp = client.get("/api/v1/reading/voices", headers=auth_headers)
        assert resp.status_code == 200
        engines = {v["engine"] for v in resp.json()["data"]}
        assert "edge" in engines
