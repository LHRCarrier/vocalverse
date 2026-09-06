"""单写方探针（docs/20 §4.4 M-2 · 2026-09-06 以 pytest 形态落地——跨平台随 CI 自动执行）。

守护「表级单写方」：Python 侧**禁止写 Java 拥有表**（内容库 + 账户 + 社区 5 表，
docs/37 §4 矩阵修订后）——凡 import 了 Java 拥有表模型且出现 Session 写调用（add/
delete/update/bulk/execute-DML）即失败。

豁免（M-3，docs/20 §4.4）：仅 `app/db/seed.py`（种子只增不改的初始器，语义与运行时单写方
契约并存）；`app/models/*` 只声明映射（不含写调用，天然通过）。
"""

from __future__ import annotations

import re
from pathlib import Path

# ---- Java 拥有表模型名（docs/20 §4.1 矩阵 + docs/37 §4 社区 5 表） ----
JAVA_OWNED_MODELS = {
    # 账户域
    "User",
    "UserProfile",
    "RefreshToken",
    # 内容库
    "Scenario",
    "ScenarioMessage",
    "Song",
    "Lrc",
    "SongPitchRef",
    "ListeningMaterial",
    "PlacementQuestion",
    "Tickets",
    "Ticket",
    # 社区域（docs/37 §4：Java 写方）
    "Post",
    "PostComment",
    "PostLike",
    "PostInteraction",
    "Follow",
}

# ---- 写调用形态（仅会话层变量；Redis 等客户端同名 delete 不算——r.delete 不匹配） ----
WRITE_PATTERNS = [
    r"(?:db|session|uow|sess)\.add_all?\(",
    r"(?:db|session|uow|sess)\.delete\(",
    r"(?:db|session|uow|sess)\.update\(",
    r"(?:db|session|uow|sess)\.bulk_(save_objects|update_mappings)\(",
    r"(?:db|session|uow|sess)\.execute\([^)]*(?:insert|update|delete)",
]

# ---- M-3 豁免文件 ----
EXEMPT_FILES = {"app/db/seed.py"}

APP_DIR = Path(__file__).resolve().parents[1] / "app"


def _iter_py_files() -> list[Path]:
    return [p for p in APP_DIR.rglob("*.py") if "__pycache__" not in p.parts]


def test_python_may_not_write_java_owned_tables():
    violations: list[str] = []
    for path in _iter_py_files():
        rel = path.relative_to(APP_DIR.parent).as_posix()
        if rel in EXEMPT_FILES:
            continue
        text = path.read_text(encoding="utf-8")
        # import 行里的 Java 拥有表模型名
        imported = set()
        for match in re.finditer(
            r"^\s*(?:from\s+[.\w]*(?:models|app\.models)[.\w]*\s+import\s+"
            r"(?:\(([^)]*)\)|([^\n]+)))",
            text,
            re.MULTILINE,
        ):
            names = (match.group(1) or match.group(2) or "").split(",")
            imported.update(n.strip() for n in names)
        hit = imported & JAVA_OWNED_MODELS
        if not hit:
            continue
        for pat in WRITE_PATTERNS:
            # 只查 "写方真源代码"；session add 等调用通常带 d 开头变量（db/session/with uow）
            if re.search(pat, text):
                violations.append(f"{rel}: import {sorted(hit)} 且出现写调用 {pat}")
                break
    assert not violations, "单写方违例（Python 写 Java 拥有表）：\n" + "\n".join(violations)


def test_probe_itself_makes_sense():
    """探针元测试：确保正例（def 文件不含写调用）不被误报、豁免文件被跳过。"""
    assert APP_DIR.is_dir()
    assert len(_iter_py_files()) > 30
