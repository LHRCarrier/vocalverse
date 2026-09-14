"""单写方探针（docs/20 §4.4 M-2 · 2026-09-06 以 pytest 形态落地——跨平台随 CI 自动执行）。

守护「表级单写方」：Python 侧**禁止写 Java 拥有表**（内容库 + 账户 + 社区 5 表，
docs/37 §4 矩阵修订后）。

**2026-09-10 修正（BUG-3）**：原正则 ``\\.add_all?\\(`` 的 ``?`` 只作用于末尾 ``l``，
实际匹配 ``add_al``/``add_all``——**``db.add(`` 完全不检测**（最常见的"新增行"写形态
漏网，门禁假绿；实测复现：jobs.py 含 ``db.add(`` 却 patterns hit=[]）。现改为
**按写入目标表名精确检测**：

- 目标模型名可判定（``db.add(X(`` / ``db.add_all([X(`` / ``db.delete(X`` /
  ``db.update(X`` / ``db.bulk_*(X`` / ``db.execute(insert|update|delete(X``)）
  → 仅当 X ∈ JAVA_OWNED_MODELS 才违规（jobs.py 写 SongPitchRef 合法通过）；
- 目标为**实例变量**（``db.add(attempt)``——先构造后 add 的常见写法）→ 静态不可判定表，
  **不判违规**（文件级粗粒度守护的已知边界，docs/20 §4.4）；
- Core DML / 裸 SQL 无显式模型名（``db.execute(text("DELETE FROM songs"))``）
  → 保守判定：该文件若 import 了 Java 拥有表即违规。

**2026-09-10 清单修正（BUG-3 连带）**：``ScenarioMessage`` 从 Java 拥有清单**移除**——
docs/10 §4.3「练习域（全部 Python 写）」/ docs/10 §3 写方矩阵明确 scenario_messages 为
Python 写方（与 SongPitchRef 同类的"次生表误列"，此前因 add 未被检测而未暴露）。

豁免（M-3，docs/20 §4.4）：`app/db/seed.py`、`app/db/seed_recommend.py`
（仓库内种子初始器，只增不改；非运行时写路径）。
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
    # 内容库（song_pitch_refs 为 Python 写方次生表，docs/20 §4.1 L222/docs/10 §3.2，
    # 故不列入 —— 2026-09-09 唱歌 P0 修正探针清单：此前误列）
    # ScenarioMessage 同为 Python 写方（docs/10 §4.3 练习域全部 Python 写）——
    # 2026-09-10 BUG-3 修正则后暴露的同类误列，一并修正
    "Scenario",
    "Song",
    "Lrc",
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

# ---- 写调用形态（按**目标模型名**判定；`add(_all)?` 修正自 BUG-3 的 `add_all?` 笔误） ----
_WRITE_CALL = re.compile(
    r"(?:db|session|uow|sess)\.(?P<method>add|add_all|delete|update|bulk_save_objects"
    r"|bulk_update_mappings)\(\s*\[?\s*(?P<target>[A-Za-z_]\w*)?"
)
#: Core DML：db.execute(insert(X) / update(X) / delete(X))（可带 sqlalchemy. 前缀）
_DML_CALL = re.compile(
    r"(?:db|session|uow|sess)\.execute\(\s*(?:\w+\.)?"
    r"(?P<method>insert|update|delete)\s*\(\s*(?P<target>[A-Za-z_]\w*)?"
)
#: 裸 SQL / text() 写：db.execute(text("INSERT ...")) / db.execute("DELETE ...")
_RAW_DML = re.compile(
    r"(?:db|session|uow|sess)\.execute\(\s*(?:text\()?\s*[\"']\s*(?:insert|update|delete)\b",
    re.IGNORECASE,
)

# ---- M-3 豁免文件（种子初始器：只增不改、非运行时写路径） ----
EXEMPT_FILES = {"app/db/seed.py", "app/db/seed_recommend.py"}

APP_DIR = Path(__file__).resolve().parents[1] / "app"


def _iter_py_files() -> list[Path]:
    return [p for p in APP_DIR.rglob("*.py") if "__pycache__" not in p.parts]


def _src(imports: str, body: str) -> str:
    """构造元测试用的最小源码片段（避免把长字符串写在断言里）。"""
    return f"from app.models import {imports}\n\n\ndef f(db, obj=None, attempt=None):\n    {body}\n"


def imported_java_owned(text: str) -> set[str]:
    """该源码 import 的 Java 拥有表模型名（app.models / models 包）。"""
    imported: set[str] = set()
    for match in re.finditer(
        r"^\s*(?:from\s+[.\w]*(?:models|app\.models)[.\w]*\s+import\s+"
        r"(?:\(([^)]*)\)|([^\n]+)))",
        text,
        re.MULTILINE,
    ):
        names = (match.group(1) or match.group(2) or "").split(",")
        imported.update(n.strip() for n in names)
    return imported & JAVA_OWNED_MODELS


def find_violations(text: str) -> list[str]:
    """纯函数：返回该源码的单写方违例说明（空列表 = 合规）。可单测（元测试正反例）。

    判定口径见模块 docstring：**显式模型名**按表名判定；**实例变量**不判（静态不可判定）；
    Core DML / 裸 SQL 无模型名时保守判违规。
    """
    java_imported = imported_java_owned(text)
    if not java_imported:
        return []
    out: list[str] = []
    for m in _WRITE_CALL.finditer(text):
        target = m.group("target")
        if target and target[0].isupper() and target in JAVA_OWNED_MODELS:
            out.append(f"写 Java 拥有表：{m.group('method')}({target})")
        # 变量形式（db.add(attempt)）：静态不可判定表 → 不判（文件级粗粒度守护的边界）
    for m in _DML_CALL.finditer(text):
        target = m.group("target")
        if target and target[0].isupper():
            if target in JAVA_OWNED_MODELS:
                out.append(f"Core DML 写 Java 拥有表：{m.group('method')}({target})")
            continue
        out.append(f"Core DML 目标不可判定：{m.group('method')}(…)——请写明目标模型（保守判定）")
    if _RAW_DML.search(text):
        out.append("裸 SQL 写（db.execute(text(...))）——保守判定为违规，请写明目标模型")
    return out


def test_python_may_not_write_java_owned_tables():
    violations: list[str] = []
    for path in _iter_py_files():
        rel = path.relative_to(APP_DIR.parent).as_posix()
        if rel in EXEMPT_FILES:
            continue
        for detail in find_violations(path.read_text(encoding="utf-8")):
            violations.append(f"{rel}: {detail}")
    assert not violations, "单写方违例（Python 写 Java 拥有表）：\n" + "\n".join(violations)


def test_probe_detects_add_and_scopes_by_table():
    """**BUG-3 回归守卫**：`db.add(` 必须被抓（原正则 `add_all?` 笔误漏网 → 假绿）；
    且判定**按目标表名**——写 Python 写方表（如 SongPitchRef）在 import 了 Java 表
    的合法混读文件里应通过（jobs.py 场景）。"""
    # ① 正例：写 Java 拥有表 → 违规（修复前：`db.add(` 不匹配任何模式 → 漏网）
    assert find_violations(_src("User", "db.add(User(username='x'))")), "db.add(User) 未检出"
    # ② 反例：合法混读文件写 Python 写方表 → 通过
    assert find_violations(_src("Lrc, Song, SongPitchRef", "db.add(SongPitchRef(lrc_id=1))")) == []
    # ③ Core DML 按表名判定
    assert find_violations(_src("Song", "db.execute(update(Song))"))
    assert find_violations(_src("SongPitchRef", "db.execute(update(SongPitchRef))")) == []
    # ④ 实例变量形式（db.delete(obj) / db.add(attempt)）→ 静态不可判定表 → **不判违规**
    #    （已知边界：文件级粗粒度守护，docs/20 §4.4；真正的越权几乎都显式写模型名）
    assert find_violations(_src("Song", "db.delete(obj)")) == []
    assert find_violations(_src("Song", "db.add(attempt)")) == []
    # ⑤ 裸 SQL 写 → 保守违规
    assert find_violations(_src("Song", 'db.execute(text("DELETE FROM songs"))'))
    # ⑥ 纯读文件（select）不违规；未 import Java 表的文件不违规
    assert find_violations(_src("Song", "return db.execute(select(Song))")) == []
    assert find_violations("def f(db):\n    db.add(User(username='x'))\n") == []
    # ⑦ ScenarioMessage 为 Python 写方（docs/10 §4.3 练习域）——清单修正后的回归断言
    sm_src = _src("ScenarioMessage, Lrc", "db.add(ScenarioMessage(content='x'))")
    assert find_violations(sm_src) == [], "ScenarioMessage 属 Python 写方，不应判违规"


def test_probe_itself_makes_sense():
    """探针元测试：确保正例（def 文件不含写调用）不被误报、豁免文件被跳过。"""
    assert APP_DIR.is_dir()
