"""读书域端到端冒烟（schema + 种子 + 路由；不入库；本地临时 sqlite）。

用法（services/python 目录）：uv run python ../scripts/poc/reading_smoke.py
注：Alembic 迁移为 PG 优先（0002 起 SQLite ALTER 不支持），冒烟以 create_all 建 schema；
迁移的 PG 离线渲染断言由 pytest tests/test_models.py 覆盖。
"""
from __future__ import annotations

import os

os.environ["APP_TESTING"] = "true"
os.environ["APP_DATABASE_URL"] = "sqlite+pysqlite:///./data/reading-smoke.db"

import json  # noqa: E402
import shutil  # noqa: E402
from pathlib import Path  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

shutil.rmtree("data/reading-smoke.db", ignore_errors=True)

from app.db import create_all_for_tests, reset_engine  # noqa: E402

reset_engine()
create_all_for_tests()
print("schema ok（迁移 0010 的 PG 渲染断言已由 pytest test_models 覆盖）")

from app.db.seed_reading import main as seed_main  # noqa: E402

seed_main()

client = TestClient(app)
h = {"X-Test-User-Id": "1"}

r = client.get("/api/v1/reading/books", headers=h)
assert r.status_code == 200, r.text
items = r.json()["data"]["items"]
print("books:", len(items), [b["title"][:22] for b in items])
book = items[0]
bid = book["id"]

r = client.get(f"/api/v1/reading/books/{bid}", headers=h)
detail = r.json()["data"]
print("detail:", detail["title"], "chapters:", len(detail["chapters"]))
cid = detail["chapters"][0]["id"]
print("first chapter:", detail["chapters"][0]["title"])

r = client.get(f"/api/v1/reading/chapters/{cid}", headers=h)
chapter = r.json()["data"]
print("chapter sentences:", len(chapter["sentences"]), "paragraphs:", len(chapter["paragraphs"]))
s0 = chapter["sentences"][0]
assert chapter["content"][s0["start"] : s0["end"]] == s0["text"], "offset 坐标系破损"

# 查词：找书里第一个像样的词
word = next(iter(chapter["sentences"][0]["text"].split())) if chapter["sentences"] else "dream"
r = client.post("/api/v1/reading/lookup", headers=h, json={"word": word})
print(f"lookup({word}):", r.status_code, (r.json().get("data") or r.json()).get("word"))

# 生词 + 批注 + 进度
r = client.post("/api/v1/reading/vocab", headers=h, json={"word": word, "book_id": bid, "chapter_id": cid, "context": s0["text"]})
assert r.status_code == 200, r.text
print("vocab added:", r.json()["data"]["added"])
ann = client.post(
    "/api/v1/reading/annotations",
    headers=h,
    json={"kind": "highlight", "chapter_id": cid, "start_offset": s0["start"], "end_offset": s0["start"] + 6, "text": s0["text"][:6], "color": "#fde68a", "sentence_idx": s0["idx"]},
)
assert ann.status_code == 200, ann.text
print("annotation:", ann.json()["data"]["kind"])
prog = client.put("/api/v1/reading/progress/%d" % bid, headers=h, json={"chapter_id": cid, "char_offset": 42})
assert prog.status_code == 200, prog.text
print("progress:", prog.json()["data"]["char_offset"])

# 听书：单句音频 + 缓存命中
r1 = client.get(f"/api/v1/reading/chapters/{cid}/tts/segment/0", headers=h)
print("segment#0:", r1.status_code, r1.headers.get("content-type"), r1.headers.get("x-tts-provider"))
r2 = client.get(f"/api/v1/reading/chapters/{cid}/tts/segment/0", headers=h)
print("segment#0 hit:", r2.headers.get("x-tts-cache"))
w = client.get("/api/v1/reading/tts/word/%s" % word, headers=h)
print("word tts:", w.status_code)
v = client.get("/api/v1/reading/voices", headers=h)
print("voices:", [x["id"] for x in v.json()["data"]])

print("SMOKE OK")
