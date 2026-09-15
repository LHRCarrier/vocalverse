"""媒体文件落盘（内容寻址 · docs/47 §4.1）。

布局：``<media_dir>/yyyy/mm/<sha256>.<ext>``；同内容（同 sha256）跨用户只落一份。

写盘纪律（依据 docs/48 拷问）：
1. **分块写**（1MB）——不把 20/64MB 全量读进内存；
2. **uuid 临时名**（不是按目标名派生）——两个并发写者不会互写同一个 tmp
   （实测：按目标名派生时后写者会覆盖前写者的尾部）；
3. **``os.replace`` 原子改名**——同分区原子；Windows 上目标文件被读句柄占用会
   ``PermissionError [WinError 5]``（``FileResponse`` 正在流式读即触发）→ 此时**不视为失败**，
   文件已存在即返回（内容寻址保证内容一致）。
"""

from __future__ import annotations

import hashlib
import os
import uuid
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

CHUNK = 1024 * 1024  # 1MB


@dataclass(frozen=True)
class StoredFile:
    sha256: str
    size: int
    #: 相对 media_dir 的路径（POSIX 分隔符，跨平台一致）
    rel_path: str


def rel_path_for(sha256: str, ext: str, now: datetime) -> str:
    """内容寻址相对路径：``yyyy/mm/<sha256>.<ext>``。"""
    return f"{now.year:04d}/{now.month:02d}/{sha256}.{ext}"


def store(root: Path, chunks: Iterable[bytes], ext: str, now: datetime) -> StoredFile:
    """把字节流写入内容寻址路径（同步；调用方放 to_thread 执行）。

    :param root: media_dir
    :param chunks: 可迭代的 bytes 分块
    :param ext: 由嗅探得到的扩展名
    :param now: 生成 yyyy/mm 目录用的时间
    """
    root.mkdir(parents=True, exist_ok=True)
    tmp_dir = root / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    digest = hashlib.sha256()
    size = 0
    tmp_path = tmp_dir / f"{uuid.uuid4().hex}.part"
    try:
        with open(tmp_path, "wb") as fh:
            for chunk in chunks:
                if not chunk:
                    continue
                digest.update(chunk)
                size += len(chunk)
                fh.write(chunk)
            fh.flush()
            os.fsync(fh.fileno())
        sha = digest.hexdigest()
        rel = rel_path_for(sha, ext, now)
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            # 内容寻址：已存在即同一份内容，直接复用（无需覆盖）
            tmp_path.unlink(missing_ok=True)
            return StoredFile(sha, size, rel)
        try:
            os.replace(tmp_path, target)
        except OSError:
            # Windows：目标被流式读句柄占用 → 若目标已存在则内容一致，视作成功
            if not target.exists():
                raise
            tmp_path.unlink(missing_ok=True)
        return StoredFile(sha, size, rel)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


def iter_file(path: Path, chunk: int = CHUNK) -> Iterator[bytes]:
    """同步分块读（供 to_thread 包装）。"""
    with open(path, "rb") as fh:
        while True:
            data = fh.read(chunk)
            if not data:
                break
            yield data


def read_head(path: Path, n: int) -> bytes:
    with open(path, "rb") as fh:
        return fh.read(n)


def resolve(root: Path, rel_path: str) -> Path:
    """相对路径 → 绝对路径（防路径穿越：解析后必须仍在 root 下）。"""
    base = root.resolve()
    target = (base / rel_path).resolve()
    if base != target and base not in target.parents:
        raise ValueError("storage path escapes media dir")
    return target
