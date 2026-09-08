#!/usr/bin/env python3
"""功能位/配置开关三处对账（arch-04）：docs/06 §17 登记表 ↔ 实现与文档。

- Python 开关：`services/python/app/core/config.py` 存在对应字段（APP_ 前缀 → snake_case）；
- Java 开关：`services/java/src/main/resources/application.yml` 存在环境变量名；
- README 需登记行：`README.md` 存在开关名（对外演示开关，生产治理口径强制）。

增删开关的纪律：改 Python config / Java application.yml 后必须同步 docs/06 §17 登记表
（+ README 若为对外演示开关）；本脚本在 python-ci 跑（AGENTS：workflow 改动本地
yaml.safe_load；新增开关先登记本表再用）。

退出码：0 = 全部一致；1 = 有缺失/漂移（CI 红）。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

#: docs/06 功能位登记表行（架构位置：`:name: | 默认 | 位置 | 说明 | README 登记 |`）
_ROW = re.compile(
    r"^\|\s*(APP_[A-Z0-9_]+|VOICEVERSE_[A-Z0-9_]+)\s*"
    r"\|\s*([^|]*?)\s*"
    r"\|\s*(python|java)\s*"
    r"\|\s*([^|]*?)\s*"
    r"\|\s*(是|否)\s*\|"
)

_REGISTRY_HEADER = "## 17. 功能位/配置开关登记表"


def parse_registry(text: str) -> list[dict]:
    """解析 docs/06 §17 登记表 → 行结构 {name, default_, location, note, readme}。"""
    rows: list[dict] = []
    active = False
    for line in text.splitlines():
        if line.strip().startswith(_REGISTRY_HEADER):
            active = True
            continue
        if active and line.startswith("## "):
            break
        if not active:
            continue
        m = _ROW.match(line)
        if m:
            rows.append(
                {
                    "name": m.group(1),
                    "default_": m.group(2),
                    "location": m.group(3),
                    "note": m.group(4),
                    "readme": m.group(5),
                }
            )
    return rows


def check_rows(rows: list[dict], python_text: str, java_text: str, readme_text: str) -> list[tuple[dict, bool, str]]:
    """对账：Python 字段名=APP_ 前缀去尾+lower()；Java=环境变量原名字面；README 按登记要求。"""
    results: list[tuple[dict, bool, str]] = []
    for row in rows:
        name = row["name"]
        if row["location"] == "python":
            field = name[len("APP_") :].lower()
            ok = regex_contains_word(python_text, field)
            reason = f"config.py 缺字段 {field}" if not ok else "ok"
        else:
            ok = name in java_text
            reason = f"application.yml 缺 {name}" if not ok else "ok"
        if ok and row["readme"] == "是":
            ok = name in readme_text
            reason = f"README.md 未登记 {name}（对外演示开关）" if not ok else "ok"
        results.append((row, ok, reason))
    return results


def regex_contains_word(text: str, word: str) -> bool:
    """词边界匹配（防 agent_lab_enabled 被 agent_lab_enabled_x 冒充）。"""
    return re.search(rf"\b{re.escape(word)}\b", text) is not None


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    registry_text = (root / "docs" / "06-技术框架决策.md").read_text(encoding="utf-8")
    python_text = (root / "services" / "python" / "app" / "core" / "config.py").read_text(
        encoding="utf-8"
    )
    java_text = (root / "services" / "java" / "src" / "main" / "resources" / "application.yml").read_text(
        encoding="utf-8"
    )
    readme_text = (root / "README.md").read_text(encoding="utf-8")

    rows = parse_registry(registry_text)
    if not rows:
        print(f"✗ 登记表未解析到任何开关行（docs/06 {_REGISTRY_HEADER}）", file=sys.stderr)
        return 1

    failed = 0
    for row, ok, reason in check_rows(rows, python_text, java_text, readme_text):
        mark = "✓" if ok else "✗"
        print(f"{mark} {row['name']:<38} [{row['location']}] {reason}")
        if not ok:
            failed += 1
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
