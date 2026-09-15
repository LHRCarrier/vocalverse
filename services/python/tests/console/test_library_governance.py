"""library 治理端点测试（docs/50 §10.3 + §14.2 第 6 条的邻近项）。

关键回归：**章节下架必须在阅读路径真的生效**。
``book_chapters.status`` 是迁移 0013 新增列，而 Python 阅读服务此前完全不看它 ——
若只在控制台改 status 而读取路径不加谓词，"下架"就是零效果的空操作。
同理 ``books.status``：书架（list_books）已过滤，但书详情页此前**没过滤**
（下架后仍可直连 URL 进入）。
"""

from __future__ import annotations

from app.core.config import get_settings
from sqlalchemy import select

from .helpers import console_headers

BOOK_PERMS = ("content:book:read", "content:book:publish")
MEDIA_PERMS = ("content:media:read", "content:media:write")


def _seed_book(
    *, chapter_status: str = "published", book_status: str = "published"
) -> tuple[int, int]:
    from app.db import get_session_factory
    from app.models.reading import Book, BookChapter

    db = get_session_factory()()
    try:
        book = Book(
            title="Test Book",
            author="Tester",
            description="d",
            level="L1",
            word_count=10,
            chapter_count=1,
            status=book_status,
        )
        db.add(book)
        db.flush()
        chapter = BookChapter(
            book_id=book.id,
            chapter_no=1,
            title="Chapter One",
            content="Hello world. This is a test chapter.",
            word_count=6,
            char_count=36,
            status=chapter_status,
        )
        db.add(chapter)
        db.commit()
        return book.id, chapter.id
    finally:
        db.close()


def _get_book_status(book_id: int) -> str:
    from app.db import get_session_factory
    from app.models.reading import Book

    db = get_session_factory()()
    try:
        return db.execute(select(Book.status).where(Book.id == book_id)).scalar_one()
    finally:
        db.close()


def test_chapter_unpublish_hides_it_from_reading_paths(client, auth_headers) -> None:
    """章节下架 → 章节正文 404、书详情章节列表里消失（修复前两者都仍然可见）。"""
    book_id, chapter_id = _seed_book()
    base = f"/api/v1/reading/books/{book_id}"

    detail = client.get(base, headers=auth_headers).json()["data"]
    assert [c["id"] for c in detail["chapters"]] == [chapter_id]
    assert (
        client.get(f"/api/v1/reading/chapters/{chapter_id}", headers=auth_headers).status_code
        == 200
    )

    resp = client.post(
        f"/api/v1/console/library/chapters/{chapter_id}/publish",
        json={"status": "draft"},
        headers=console_headers(perms=BOOK_PERMS),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["status"] == "draft"

    detail = client.get(base, headers=auth_headers).json()["data"]
    assert detail["chapters"] == [], "下架章节必须从书详情的章节列表消失"
    assert (
        client.get(f"/api/v1/reading/chapters/{chapter_id}", headers=auth_headers).status_code
        == 404
    ), "下架章节的正文必须读不到"


def test_book_unpublish_hides_detail_and_shelf(client, auth_headers) -> None:
    """书上/下架：下架后书架与详情都不可见（详情此前是漏点）。"""
    book_id, _ = _seed_book()
    resp = client.post(
        f"/api/v1/console/library/books/{book_id}/publish",
        json={"status": "draft"},
        headers=console_headers(perms=BOOK_PERMS),
    )
    assert resp.status_code == 200
    assert _get_book_status(book_id) == "draft"
    assert client.get(f"/api/v1/reading/books/{book_id}", headers=auth_headers).status_code == 404
    shelf = client.get("/api/v1/reading/books", headers=auth_headers).json()["data"]["items"]
    assert shelf == []


def test_publish_book_requires_published_chapters(client) -> None:
    """上架校验：仍有未上架章节 → 46011 + ``data.violations[]``（字段级原因）。"""
    book_id, chapter_id = _seed_book(book_status="draft", chapter_status="draft")
    resp = client.post(
        f"/api/v1/console/library/books/{book_id}/publish",
        json={"status": "published"},
        headers=console_headers(perms=BOOK_PERMS),
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == 46011
    assert body["data"]["violations"][0]["field"] == "chapters"
    assert _get_book_status(book_id) == "draft"  # 原状态未变（不是"校验失败但已改"）

    # 章节上架后即可
    client.post(
        f"/api/v1/console/library/chapters/{chapter_id}/publish",
        json={"status": "published"},
        headers=console_headers(perms=BOOK_PERMS),
    )
    assert (
        client.post(
            f"/api/v1/console/library/books/{book_id}/publish",
            json={"status": "published"},
            headers=console_headers(perms=BOOK_PERMS),
        ).status_code
        == 200
    )


def test_publish_rejects_invalid_status(client) -> None:
    book_id, _ = _seed_book()
    resp = client.post(
        f"/api/v1/console/library/books/{book_id}/publish",
        json={"status": "nope"},
        headers=console_headers(perms=BOOK_PERMS),
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == 46007


def _seed_media() -> str:
    """落一条 ready 媒体行 + 对应物理文件（供公共端点真实读取）。"""
    import secrets

    from app.db import get_session_factory
    from app.media import service as media_service
    from app.models.media import MediaAsset, MediaStatus

    rel = "2026/09/test.png"
    path = media_service.media_dir() / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 64)
    public_id = secrets.token_hex(16)
    db = get_session_factory()()
    try:
        db.add(
            MediaAsset(
                public_id=public_id,
                owner_id=1,
                kind="image",
                mime_type="image/png",
                size_bytes=72,
                sha256="a" * 64,
                storage_path=rel,
                status=MediaStatus.READY,
            )
        )
        db.commit()
    finally:
        db.close()
    return public_id


def test_media_hide_blocks_public_read_and_restore_unblocks(client) -> None:
    """隐藏后公共媒体端点读不到（40403），恢复后又能读。"""
    public_id = _seed_media()
    url = f"/api/v1/media/{public_id}"
    assert client.get(url).status_code == 200

    resp = client.post(
        f"/api/v1/console/library/media/{public_id}/hide",
        json={"hidden": True},
        headers=console_headers(perms=MEDIA_PERMS),
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "hidden"
    assert client.get(url).status_code == 404, "隐藏的媒体不得经公共端点读取"

    resp = client.post(
        f"/api/v1/console/library/media/{public_id}/hide",
        json={"hidden": False},
        headers=console_headers(perms=MEDIA_PERMS),
    )
    assert resp.json()["data"]["status"] == "ready"
    assert client.get(url).status_code == 200


def test_media_hide_requires_boolean(client) -> None:
    public_id = _seed_media()
    resp = client.post(
        f"/api/v1/console/library/media/{public_id}/hide",
        json={"hidden": "yes"},
        headers=console_headers(perms=MEDIA_PERMS),
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == 46007


def test_media_list_requires_permission(client) -> None:
    resp = client.get("/api/v1/console/library/media", headers=console_headers(perms=()))
    assert resp.status_code == 403
    assert resp.json()["code"] == 46002


def test_library_reads_unaffected_by_telemetry_flag(client, auth_headers, monkeypatch) -> None:
    """遥测开关只管 ops：关掉后 library 治理链路照常（内容运营不该被观测开关拖下水）。"""
    monkeypatch.setattr(get_settings(), "ops_telemetry_enabled", False)
    book_id, _ = _seed_book()
    resp = client.post(
        f"/api/v1/console/library/books/{book_id}/publish",
        json={"status": "archived"},
        headers=console_headers(perms=BOOK_PERMS),
    )
    assert resp.status_code == 200
