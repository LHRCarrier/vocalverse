"""仓库路径解析（**只读 seed 资产**用；2026-09-14）。

背景（为什么不能用 `parents[N]` 一把梭）：
`data/seed/**` 既是**入库资产**（公版书正文 / LRC / 书封图，`.gitignore` 里显式豁免可提交），
又要在**容器**与**裸跑**两种形态下都能读到。而 `app/` 的绝对位置在两种形态下不同：

| 形态 | `app/api/routes/reading.py` 的 `parents[4]` |
| --- | --- |
| 裸跑（`<仓库>/services/python/app/...`） | **仓库根** ✅ |
| 容器（`/app/app/api/routes/reading.py`） | `/` ❌（实际资产在 `/app/data/seed`） |

⇒ 数层数必然有一种形态是错的（`seed_reading.py` 的 `parents[4]` 就有这个隐患）。故改为
**向上找标记目录**：第一个含 `data/seed` 的祖先即仓库根；都找不到才回退 `/app`（容器口径）。
本模块只做路径计算，无任何副作用；`data/seed` 是只读资产，与 `audio_dir`/`media_dir`
那类"运行时卷"分开——后两者仍按 cwd 解析（见 README 常见问题「共享卷目录」条）。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

#: 容器内的回退根（Dockerfile `WORKDIR /app`）。
CONTAINER_ROOT = Path("/app")


@lru_cache(maxsize=1)
def repo_root() -> Path:
    """仓库根：从本文件向上找第一个含 `data/seed` 的目录；找不到回退 `/app`。"""
    for parent in Path(__file__).resolve().parents:
        if (parent / "data" / "seed").is_dir():
            return parent
    return CONTAINER_ROOT


def seed_dir() -> Path:
    """`data/seed`：入库的种子资产（书正文 JSON / 词典 CSV / LRC / 书封图）。"""
    return repo_root() / "data" / "seed"


def book_cover_dir() -> Path:
    """`data/seed/covers`：书籍封面图（公版，随仓库分发；见 docs/10 books.cover_url）。"""
    return seed_dir() / "covers"
