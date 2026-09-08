"""幂等种子：公版书 + 词典子集（docs/45 §7 · 拷问 M-4/V-15：迁移只建表，数据走 seed）。

覆盖内容：
- books/book_chapters：``data/seed/reading_books.json``（Project Gutenberg 公版书，清洗产物）；
- dictionary_entries/dictionary_forms：``data/seed/ecdict_subset.csv``（ECDICT MIT 子集，
  书本词表 ∪ 词频 top，词形反向索引由 exchange 派生）。

幂等策略（docs/10 §7.3 自然键口径）：
- books 自然键 (title, author)（同名异作/异版本场景，拷问 M-5）；已存在 → 跳过（不覆盖后续编辑）；
- chapters (book_id, chapter_no)；dictionary_entries.word（ON CONFLICT DO NOTHING 语义：
  先查已有集合，缺失批次才插入）；
- dictionary_forms 由 exchange 派生；entry 无 exchange → 不产生 forms。

用法（services/python 目录）：
    uv run python -m app.db.seed_reading
"""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

from sqlalchemy import select

from app.db import get_session_factory
from app.models import Book, BookChapter, DictionaryEntry, DictionaryForm

try:
    REPO_ROOT = Path(__file__).resolve().parents[4]  # 本地：仓库根
except IndexError:
    REPO_ROOT = Path("/app")  # 容器回退（seed.py 同款，2026-09-04 修复口径）

BOOKS_SEED = REPO_ROOT / "data" / "seed" / "reading_books.json"
DICT_SEED = REPO_ROOT / "data" / "seed" / "ecdict_subset.csv"

#: exchange 键 → 词形类型（ECDICT：p 过去式 / d 过去分词 / i 现在分词 / 3 三单 /
#: r 比较级 / t 最高级 / s 复数）
EXCHANGE_KEYS = ("p", "d", "i", "3", "r", "t", "s")

_WORD_RE = re.compile(r"[A-Za-z]+")


def _count_words(text: str) -> int:
    return len(_WORD_RE.findall(text))


def seed_books(session) -> int:
    """书 + 章节（自然键 (title, author) 与 (book_id, chapter_no) 幂等）。"""
    if not BOOKS_SEED.exists():
        print(f"[seed_reading] 跳过书：缺 {BOOKS_SEED}")
        return 0
    data = json.loads(BOOKS_SEED.read_text(encoding="utf-8"))
    created = 0
    for spec in data:
        book = session.execute(
            select(Book).where(Book.title == spec["title"], Book.author == spec["author"])
        ).scalar_one_or_none()
        if book is None:
            book = Book(
                title=spec["title"],
                author=spec["author"],
                description=spec.get("description"),
                language="en",
                level=spec.get("level", "L1"),
                source="public_domain",
                cover_color=spec.get("cover_color"),
                cover_emoji=spec.get("cover_emoji"),
                word_count=spec.get("word_count", 0),
                chapter_count=len(spec.get("chapters", [])),
            )
            session.add(book)
            session.flush()
            created += 1
        existing_nos = set(
            session.execute(
                select(BookChapter.chapter_no).where(BookChapter.book_id == book.id)
            ).scalars()
        )
        for ch in spec.get("chapters", []):
            no = int(ch.get("chapter_no", ch.get("no", 0)))
            if no in existing_nos:
                continue
            paragraphs = ch.get("paragraphs") or []
            content = "\n\n".join(p.strip() for p in paragraphs if p.strip())
            if not content:
                continue
            existing_nos.add(no)
            session.add(
                BookChapter(
                    book_id=book.id,
                    chapter_no=no,
                    title=str(ch.get("title") or f"Chapter {no}")[:255],
                    content=content,
                    content_version=1,
                    word_count=_count_words(content),
                    char_count=len(content),
                )
            )
    session.commit()
    print(f"[seed_reading] books: 新增 {created}（其余已存在跳过）")
    return created


def _parse_exchange(raw: str | None) -> dict[str, str] | None:
    """ECDICT exchange "s:inventions/p:ran/..." → {key: value}（无效/空 → None）。"""
    if not raw:
        return None
    out: dict[str, str] = {}
    for part in raw.split("/"):
        if ":" in part:
            k, v = part.split(":", 1)
            if k in EXCHANGE_KEYS and v:
                out[k] = v
    return out or None


def seed_dictionary(session) -> int:
    """词典子集（word 唯一幂等；forms 由 exchange 派生幂等）。"""
    if not DICT_SEED.exists():
        print(f"[seed_reading] 跳过词典：缺 {DICT_SEED}")
        return 0
    created = 0
    with DICT_SEED.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        batch: list[dict] = []
        for row in reader:
            word = (row.get("word") or "").strip().lower()
            if not word:
                continue
            batch.append(
                {
                    "word": word,
                    "phonetic": (row.get("phonetic") or "").strip() or None,
                    "translation": (row.get("translation") or "").strip() or None,
                    "definition": (row.get("definition") or "").strip() or None,
                    "pos": (row.get("pos") or "").strip() or None,
                    "exchange": _parse_exchange(row.get("exchange")),
                    "frequency": int(row["frequency"])
                    if (row.get("frequency") or "").isdigit()
                    else None,
                }
            )
        # 分块幂等插入（word 唯一约束兜底；10k 行 × 千行块）
        for i in range(0, len(batch), 1000):
            chunk = batch[i : i + 1000]
            existing = set(
                session.execute(
                    select(DictionaryEntry.word).where(
                        DictionaryEntry.word.in_([r["word"] for r in chunk])
                    )
                ).scalars()
            )
            for row in chunk:
                if row["word"] in existing:
                    continue
                session.add(DictionaryEntry(**row))
                existing.add(row["word"])
                created += 1
        session.flush()
        # 词形反向索引：只补缺失 forms（entry 按 word 找 id）
        for row in batch:
            if not row["exchange"]:
                continue
            entry = session.execute(
                select(DictionaryEntry).where(DictionaryEntry.word == row["word"])
            ).scalar_one_or_none()
            if entry is None:
                continue
            for value in row["exchange"].values():
                if not value:
                    continue
                form_existing = session.execute(
                    select(DictionaryForm).where(DictionaryForm.form == value)
                ).scalar_one_or_none()
                if form_existing is None:
                    session.add(DictionaryForm(form=value, entry_id=entry.id))
    session.commit()
    print(f"[seed_reading] dictionary: 新增 {created} 条目（其余已存在跳过）")
    return created


def main() -> int:
    with get_session_factory()() as session:
        seed_books(session)
        seed_dictionary(session)
    return 0


if __name__ == "__main__":
    sys.exit(main())
