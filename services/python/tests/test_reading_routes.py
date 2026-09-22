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
        # 2026-09-14：书架 DTO 必须带 cover_url（值为空时前端回退合成封面，键位不能缺）
        assert "cover_url" in body["data"]["items"][0]

    def test_list_books_exposes_cover_url(self, client, auth_headers):
        """有封面的书：`cover_url` 原样透出（前端据此渲染 `<img>`）。"""
        with get_session_factory()() as session:
            session.add(
                Book(
                    title="Covered Book",
                    author="Tester",
                    level="L1",
                    cover_url="/api/v1/reading/covers/demo.jpg",
                )
            )
            session.commit()
        resp = client.get("/api/v1/reading/books", headers=auth_headers)
        row = next(b for b in resp.json()["data"]["items"] if b["title"] == "Covered Book")
        assert row["cover_url"] == "/api/v1/reading/covers/demo.jpg"

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


class TestBookCover:
    """书封图端点（2026-09-14 新增）。

    三条口径：① **公开**（`<img src>` 不带 Authorization，故无鉴权）；② 只服务
    `data/seed/covers/` 白名单文件名（目录穿越/子目录一律 400）；③ 缺图回 envelope 40401
    （不是框架的 `{"detail": ...}`——错误码契约见 docs/api/error-codes.md）。
    """

    def test_serve_cover_is_public(self, client, tmp_path, monkeypatch):
        cover = tmp_path / "demo.jpg"
        cover.write_bytes(b"\xff\xd8\xff\xe0JFIF-fake")
        monkeypatch.setattr("app.api.routes.reading.book_cover_dir", lambda: tmp_path)

        resp = client.get("/api/v1/reading/covers/demo.jpg")  # 不带 auth_headers
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/jpeg"
        assert resp.content == b"\xff\xd8\xff\xe0JFIF-fake"
        assert "max-age" in resp.headers.get("cache-control", "")

    def test_missing_cover_40401(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr("app.api.routes.reading.book_cover_dir", lambda: tmp_path)
        resp = client.get("/api/v1/reading/covers/nope.jpg")
        assert resp.status_code == 404
        assert resp.json()["code"] == 40401

    @pytest.mark.parametrize("name", ["..", "...", ".hidden.jpg", "sub/dir.jpg", "a" * 80])
    def test_bad_cover_name_40001(self, client, tmp_path, monkeypatch, name):
        monkeypatch.setattr("app.api.routes.reading.book_cover_dir", lambda: tmp_path)
        (tmp_path / "ok.jpg").write_bytes(b"x")
        resp = client.get(f"/api/v1/reading/covers/{name}")
        # 含 `/` 的会被路由层挡在 404；其余非法名必须被白名单拒成 40001
        assert resp.status_code in (400, 404)
        if resp.status_code == 400:
            assert resp.json()["code"] == 40001

    def test_book_cover_dir_is_seed_assets(self):
        """封面目录锚在**仓库根** `data/seed/covers`（不是 cwd 相对）——容器与裸跑同口径。"""
        from app.core.paths import book_cover_dir, seed_dir

        assert seed_dir().name == "seed"
        assert seed_dir().parent.name == "data"
        assert (seed_dir() / "reading_books.json").is_file()
        assert book_cover_dir() == seed_dir() / "covers"


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

    def test_my_notes_cross_chapter_list(self, client, auth_headers, reading_seed):
        """「我的笔记」跨章列表（docs/53 P5）：join 章节/书名 + kind 过滤 + created_at 倒序。"""
        chapter_id = reading_seed["chapter_id"]
        first = client.post(
            "/api/v1/reading/annotations",
            headers=auth_headers,
            json={
                "kind": "highlight",
                "chapter_id": chapter_id,
                "start_offset": 0,
                "end_offset": 5,
                "text": "Alice",
            },
        ).json()["data"]
        second = client.post(
            "/api/v1/reading/annotations",
            headers=auth_headers,
            json={
                "kind": "note",
                "chapter_id": chapter_id,
                "start_offset": 6,
                "end_offset": 10,
                "text": "knew",
                "note": "过去式",
            },
        ).json()["data"]

        all_notes = client.get("/api/v1/reading/notes", headers=auth_headers).json()["data"]
        assert [n["id"] for n in all_notes["items"]] == [second["id"], first["id"]]  # 倒序
        assert all_notes["has_more"] is False
        top = all_notes["items"][0]
        assert top["book_title"] == "Demo Book" and top["chapter_title"] == "Chapter 1"
        assert top["chapter_id"] == chapter_id and top["note"] == "过去式"

        highlights = client.get(
            "/api/v1/reading/notes?kind=highlight", headers=auth_headers
        ).json()["data"]["items"]
        assert [n["id"] for n in highlights] == [first["id"]]

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

    def test_put_twice_update_path(self, client, auth_headers, reading_seed):
        """第二次保存走 UPDATE 路径（修复前必红：updated_at 过期 → DetachedInstanceError → 500）。

        复现（2026-09-09 联调实测）：第 1 次 PUT 走 INSERT（RETURNING 已取 updated_at）→ 200；
        第 2 次 PUT 走 UPDATE（onupdate 服务端生成列在 commit 后被标记过期）→ 路由在会话外
        访问该属性 → DetachedInstanceError → 500。阅读器每次滚动都保存进度，因此「只有第一次
        保存生效」而前端静默吞掉后续失败。
        """
        bid = reading_seed["book_id"]
        cid = reading_seed["chapter_id"]
        first = client.put(
            f"/api/v1/reading/progress/{bid}",
            headers=auth_headers,
            json={"chapter_id": cid, "char_offset": 10},
        )
        assert first.status_code == 200
        assert first.json()["data"]["updated_at"] is not None

        second = client.put(
            f"/api/v1/reading/progress/{bid}",
            headers=auth_headers,
            json={"chapter_id": cid, "char_offset": 120},
        )
        assert second.status_code == 200, second.text
        body = second.json()["data"]
        assert body["char_offset"] == 120
        assert body["updated_at"] is not None  # 修复前这里在服务端就已 500

        # 第三次仍然可写（幂等 upsert，无状态残留）
        third = client.put(
            f"/api/v1/reading/progress/{bid}",
            headers=auth_headers,
            json={"chapter_id": cid, "char_offset": 300},
        )
        assert third.status_code == 200
        assert (
            client.get(f"/api/v1/reading/progress/{bid}", headers=auth_headers).json()["data"][
                "char_offset"
            ]
            == 300
        )


class TestVoices:
    def test_voices_always_has_edge(self, client, auth_headers):
        resp = client.get("/api/v1/reading/voices", headers=auth_headers)
        assert resp.status_code == 200
        engines = {v["engine"] for v in resp.json()["data"]}
        assert "edge" in engines
