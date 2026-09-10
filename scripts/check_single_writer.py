"""P0-7 写方唯一性静态探针（docs/10 §3.1 写归属矩阵 · docs/19 P0-7 · 2026-09-07）。

守护对象：Python 服务**不得对 Java 拥有的表做任何 ORM 写**（Single Writer，docs/10 §5/P8）——
一旦出现双写，社区/账户/内容数据即失守（无任何机制防护，此前仅文档约定）。

规则（AST 精确版，误报最小化）：
1. 收集文件级 `from app.models... import X` 的本地名 ↔ 模型类名映射；
2. 变量追踪：`x = X(...)` 且 X ∈ Java-owned 名单 → x 为"Java 实例"；
3. 检查 `*.add(` / `*.add_all(` 的参数树（直接构造 Call / 实例变量 / 列表元素）→ 命中即违规；
4. 违规输出 `文件:行: ...`，退出码 1（CI 阻断，非告警——守护必须是硬门禁）。

已知局限（注释声明，覆盖评审"grep add()/update()"意图的主力面）：
- 不查 `query().update()` 批量更新（项目无先例；出现时再加规则）；
- 跨函数不追踪实例变量（保守：内联/同函数赋值必抓，跨函数漏网由 code review 补）；
- `db.flush()` 不单独判违（被 flush 的对象必然先经 add，已在 3 覆盖）。

豁免：`app/db/seed*.py`（docs/11 Q-A15 拍板①：seed=初始化器，单写豁免）；
tests/ 与 alembic/ 不在扫描范围（测试构造数据、迁移为 schema 演进，均非运行时写方）。

用法：python scripts/check_single_writer.py            # 扫描 services/python/app
     python scripts/check_single_writer.py --root <dir> # 自定义根
"""

from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass
from pathlib import Path

# docs/10 §3.1 总表：Java 拥有的表 → Python 侧模型类名
# （post_likes 写方 2026-09-06 由 Python 反转为 Java，docs/20 §4.1）
JAVA_WRITTEN_MODELS = frozenset(
    {
        "User",  # users
        "UserProfile",  # user_profiles
        "RefreshToken",  # refresh_tokens
        "Scenario",  # scenarios
        "Song",  # songs
        "Lrc",  # lrc
        "ListeningMaterial",  # listening_materials
        "PlacementQuestion",  # placement_questions
        "Ticket",  # tickets
        "Post",  # posts
        "PostComment",  # post_comments
        "PostLike",  # post_likes
        "PostInteraction",  # post_interactions
        "Follow",  # follows
        "DirectMessage",  # direct_messages（私信 IM · docs/49 §1 · 迁移 0012）
        "DmReadState",  # dm_read_state（同上）
    }
)

DEFAULT_EXCLUDE_PATTERNS = ("app/db/seed",)


@dataclass
class Violation:
    path: str
    lineno: int
    model: str
    message: str


def _collect_java_imports(tree: ast.AST) -> dict[str, str]:
    """文件级 `from app.models... import X` → {本地名: 模型类名}，仅保留 Java-owned。"""
    mapping: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("app.models"):
            for alias in node.names:
                local = alias.asname or alias.name
                if alias.name in JAVA_WRITTEN_MODELS:
                    mapping[local] = alias.name
    return mapping


def _flatten_add_args(arg: ast.AST):
    """add/add_all 参数展开为叶子节点（Name/Call）；常量忽略。"""
    if isinstance(arg, (ast.Name, ast.Call)):
        yield arg
    elif isinstance(arg, (ast.List, ast.Tuple, ast.Set)):
        for elt in arg.elts:
            yield from _flatten_add_args(elt)
    # starred / 表达式等忽略（保守漏报 > 误报）


def find_violations(path: Path) -> list[Violation]:
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(path))
    java_models = _collect_java_imports(tree)

    # 2) 实例追踪：`x = X(...)` 或 `x: Type = ...`（限本文件同级；跨函数不追踪=保守）
    instances: set[str] = set()
    for node in ast.walk(tree):
        targets: list[ast.expr] = []
        value: ast.expr | None = None
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign):
            targets, value = [node.target], node.value
        if value is None or not targets:
            continue
        if isinstance(value, ast.Call) and isinstance(value.func, ast.Name):
            if value.func.id in java_models:
                for t in targets:
                    if isinstance(t, ast.Name):
                        instances.add(t.id)

    violations: list[Violation] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in ("add", "add_all"):
            continue
        for arg in node.args:
            for leaf in _flatten_add_args(arg):
                if isinstance(leaf, ast.Call) and isinstance(leaf.func, ast.Name):
                    model = java_models.get(leaf.func.id)
                    if model:
                        violations.append(
                            Violation(str(path), node.lineno, model, f"db.add({model}(...)) 疑似越权写 Java-owned 表")
                        )
                elif isinstance(leaf, ast.Name) and leaf.id in instances:
                    model = _model_for_var(leaf.id, java_models, tree)  # 从构造点反查模型类
                    if model:
                        violations.append(
                            Violation(str(path), node.lineno, model, f"db.add({leaf.id}) 疑似越权写 Java-owned 表（{model} 实例）")
                        )
    return violations


def _model_for_var(var: str, java_models: dict[str, str], tree: ast.AST) -> str | None:
    """反查：`x = Scenario(...)` 的 x 对应模型类名（重复赋值取首个命中）。"""
    for node in ast.walk(tree):
        targets: list[ast.expr] = []
        value: ast.expr | None = None
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign):
            targets, value = [node.target], node.value
        if value is None or not isinstance(value, ast.Call):
            continue
        if not isinstance(value.func, ast.Name) or value.func.id not in java_models:
            continue
        for t in targets:
            if isinstance(t, ast.Name) and t.id == var:
                return java_models[value.func.id]
    return None


def scan(root: Path, exclude_patterns: tuple[str, ...] = DEFAULT_EXCLUDE_PATTERNS) -> list[Violation]:
    violations: list[Violation] = []
    for path in sorted(root.rglob("*.py")):
        rel = path.as_posix()
        if any(pattern in rel for pattern in exclude_patterns):
            continue
        try:
            violations.extend(find_violations(path))
        except (SyntaxError, UnicodeDecodeError) as exc:  # 解析不了的文件跳过（非 .py 陷阱）
            print(f"[warn] 无法解析 {path}: {exc}", file=sys.stderr)
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description="P0-7 Single-Writer AST probe")
    parser.add_argument("--root", default="app", help="扫描根目录（默认 app；相对仓库 services/python 运行）")
    args = parser.parse_args()
    root = Path(args.root)
    violations = scan(root)
    if not violations:
        print(f"ok：{root} 无越权写 Java-owned 表（{JAVA_WRITTEN_MODELS.__len__()} 张表受守护）")
        return 0
    for v in violations:
        print(f"{v.path}:{v.lineno}: {v.message}")
    print(f"FAILED：{len(violations)} 处疑似越权写（docs/10 §3.1 Single Writer，需改经内部委托）")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
