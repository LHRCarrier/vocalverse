"""媒体域路由与存储（社区 S3 · docs/47 §4.1 · 拷问裁定 docs/48 B1/B2/B6/B7）。

覆盖：魔数嗅探白名单 / 体积上限（41301）/ 元数据越界（42205）/ 越权删除（40302）/
软删后 40403 / 同 owner 去重与「删了再传」/ 不同 owner 同内容共享物理文件 /
匿名可读 + Range 206 / 响应体带 code（BizError 而非 HTTPException）。
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from app.core.config import get_settings
from app.media import storage
from app.media.sniff import sniff

# 最小合法文件头（嗅探只看头部字节，测试不需要真图）
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 4096
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 4096
GIF = b"GIF89a" + b"\x00" * 4096
WEBP = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 4096
MP4 = b"\x00\x00\x00\x20ftypisom" + b"\x00" * 4096
WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 16 + b"webm" + b"\x00" * 4000
EXE = b"MZ" + b"\x00" * 4096  # 非白名单


def _upload(client, auth_headers, data: bytes, *, kind="image", name="x.bin", **fields):
    return client.post(
        "/api/v1/media",
        headers=auth_headers,
        files={"file": (name, io.BytesIO(data), "application/octet-stream")},
        data={"kind": kind, **fields},
    )


# --------------------------------------------------------------------------- 嗅探纯函数


def test_sniff_whitelist():
    assert sniff(PNG).mime == "image/png"
    assert sniff(JPEG).mime == "image/jpeg"
    assert sniff(GIF).mime == "image/gif"
    assert sniff(WEBP).mime == "image/webp"
    assert sniff(MP4).mime == "video/mp4"
    assert sniff(WEBM).mime == "video/webm"
    # 非白名单 / 空
    assert sniff(EXE) is None
    assert sniff(b"") is None
    # EBML 但 DocType=matroska → 拒绝（只放 webm）
    assert sniff(b"\x1a\x45\xdf\xa3" + b"\x00" * 16 + b"matroska" + b"\x00" * 100) is None


def test_sniff_ignores_client_headers():
    """扩展名/Content-Type 是用户可控的：`.png` 里塞 EXE 必须被拒。"""
    assert sniff(b"MZ\x90\x00" + b"\x00" * 100) is None


def test_storage_content_addressed_and_traversal_guard(tmp_path):
    from datetime import UTC, datetime

    now = datetime(2026, 9, 9, tzinfo=UTC)
    stored = storage.store(tmp_path, [PNG], "png", now)
    assert stored.rel_path == f"2026/09/{stored.sha256}.png"
    assert (tmp_path / stored.rel_path).read_bytes() == PNG
    # 同内容第二次 → 同一路径，不重复写
    again = storage.store(tmp_path, [PNG], "png", now)
    assert again.rel_path == stored.rel_path
    # 路径穿越防护
    with pytest.raises(ValueError):
        storage.resolve(tmp_path, "../../etc/passwd")


# --------------------------------------------------------------------------- 上传


def test_upload_png_ok_and_view_shape(client, auth_headers):
    r = _upload(client, auth_headers, PNG, kind="image", width="800", height="600")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["code"] == 0
    view = body["data"]
    assert view["kind"] == "image"
    assert view["mimeType"] == "image/png"
    assert view["width"] == 800 and view["height"] == 600
    # 对外标识是随机 public_id（32 hex），URL 只用它（docs/48 B2）
    assert len(view["id"]) == 32
    assert view["url"] == f"/api/v1/media/{view['id']}"
    assert view["id"].isdigit() is False


def test_upload_rejects_non_whitelist_type(client, auth_headers):
    r = _upload(client, auth_headers, EXE, kind="image", name="evil.png")
    assert r.status_code == 415
    assert r.json()["code"] == 41501  # BizError 才有 code（docs/48 B7）


def test_upload_rejects_kind_mime_mismatch(client, auth_headers):
    """kind=video 传 PNG → 415（白名单按 kind 分）。"""
    r = _upload(client, auth_headers, PNG, kind="video")
    assert r.status_code == 415
    assert r.json()["code"] == 41501


def test_upload_rejects_bad_kind(client, auth_headers):
    r = _upload(client, auth_headers, PNG, kind="audio")
    assert r.status_code == 422
    assert r.json()["code"] == 42205


def test_upload_rejects_oversize(client, auth_headers, monkeypatch):
    monkeypatch.setattr(get_settings(), "max_upload_bytes", 2048, raising=False)
    r = _upload(client, auth_headers, PNG)
    assert r.status_code == 413
    assert r.json()["code"] == 41301


def test_upload_rejects_bad_meta(client, auth_headers):
    # 元数据先于嗅探校验（失败快速、不落盘）
    r = _upload(client, auth_headers, PNG, width="99999")
    assert r.status_code == 422
    assert r.json()["code"] == 42205
    r2 = _upload(client, auth_headers, MP4, kind="video", duration_s="9999")
    assert r2.status_code == 422
    assert r2.json()["code"] == 42205
    r3 = _upload(client, auth_headers, PNG, width="0")
    assert r3.status_code == 422
    assert r3.json()["code"] == 42205
    # 元数据合法时，类型不符才轮到 415
    r4 = _upload(client, auth_headers, PNG, kind="video")
    assert r4.status_code == 415
    assert r4.json()["code"] == 41501


def test_upload_requires_auth(client):
    r = client.post(
        "/api/v1/media", files={"file": ("x.png", io.BytesIO(PNG))}, data={"kind": "image"}
    )
    assert r.status_code == 401


# --------------------------------------------------------------------------- 去重 / 软删


def test_same_owner_same_content_dedup_then_reupload_after_delete(client, auth_headers):
    """docs/48 B1：全局唯一 + 软删会让「传→删→再传」永久失败；本用例锁住修复后的语义。"""
    first = _upload(client, auth_headers, PNG).json()["data"]
    # 同 owner 同内容 → 复用同一行（不新增）
    second = _upload(client, auth_headers, PNG).json()["data"]
    assert second["id"] == first["id"]

    # 软删
    assert client.delete(f"/api/v1/media/{first['id']}", headers=auth_headers).status_code == 200
    assert client.get(f"/api/v1/media/{first['id']}").status_code == 404

    # 再传同一内容 → 必须成功（新行，旧行保持 deleted）
    third = _upload(client, auth_headers, PNG)
    assert third.status_code == 200, third.text
    assert third.json()["data"]["id"] != first["id"]
    assert client.get(f"/api/v1/media/{third.json()['data']['id']}").status_code == 200


def test_different_owners_share_physical_file(client):
    a = client.post(
        "/api/v1/media",
        headers={"X-Test-User-Id": "1"},
        files={"file": ("a.png", io.BytesIO(PNG))},
        data={"kind": "image"},
    ).json()["data"]
    b = client.post(
        "/api/v1/media",
        headers={"X-Test-User-Id": "2"},
        files={"file": ("b.png", io.BytesIO(PNG))},
        data={"kind": "image"},
    ).json()["data"]
    assert a["id"] != b["id"]
    # 物理文件按 sha256 共享一份
    root = Path(get_settings().media_dir)
    files = [p for p in root.rglob("*") if p.is_file() and p.suffix == ".png"]
    assert len(files) == 1


def test_delete_requires_owner(client, auth_headers):
    view = _upload(client, auth_headers, PNG).json()["data"]
    r = client.delete(f"/api/v1/media/{view['id']}", headers={"X-Test-User-Id": "2"})
    assert r.status_code == 403
    assert r.json()["code"] == 40302


def test_delete_unknown_returns_40403(client, auth_headers):
    r = client.delete("/api/v1/media/" + "0" * 32, headers=auth_headers)
    assert r.status_code == 404
    assert r.json()["code"] == 40403


# --------------------------------------------------------------------------- 读取 / Range


def test_anonymous_read_and_range(client, auth_headers):
    view = _upload(client, auth_headers, PNG).json()["data"]
    # 匿名（无 Authorization）可读：原生 <img> 带不了 Bearer
    r = client.get(f"/api/v1/media/{view['id']}")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.headers.get("accept-ranges") == "bytes"
    assert r.content == PNG

    # Range → 206 + Content-Range（视频拖拽依赖）
    r2 = client.get(f"/api/v1/media/{view['id']}", headers={"Range": "bytes=0-7"})
    assert r2.status_code == 206
    assert r2.content == PNG[:8]
    assert r2.headers["content-range"].startswith("bytes 0-7/")

    # 越界 Range → 416
    r3 = client.get(f"/api/v1/media/{view['id']}", headers={"Range": f"bytes={len(PNG) + 10}-"})
    assert r3.status_code == 416


def test_read_unknown_public_id_returns_40403(client):
    r = client.get("/api/v1/media/" + "f" * 32)
    assert r.status_code == 404
    assert r.json()["code"] == 40403


def test_list_mine_only_own(client):
    client.post(
        "/api/v1/media",
        headers={"X-Test-User-Id": "1"},
        files={"file": ("a.png", io.BytesIO(PNG))},
        data={"kind": "image"},
    )
    client.post(
        "/api/v1/media",
        headers={"X-Test-User-Id": "2"},
        files={"file": ("b.jpg", io.BytesIO(JPEG))},
        data={"kind": "image"},
    )
    r = client.get("/api/v1/media", headers={"X-Test-User-Id": "1"})
    items = r.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["mimeType"] == "image/png"


def test_rate_limit_bucket_registered():
    """新增桶必须登记 bucket_limits（否则运维视图缺项，docs/48 B20）。"""
    from app.core.ratelimit import bucket_limits

    assert "media" in bucket_limits()
