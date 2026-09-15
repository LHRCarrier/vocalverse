"""门禁：禁止 JPQL 里出现「会被 PostgreSQL 判为无类型」的参数用法。

## 为什么需要它（2026-09-10 实测，本仓同类第四次）

PostgreSQL 在 **Parse 阶段**就要求确定每个 `$n` 的类型。以下两种写法让参数在 PG 侧
**没有类型线索**，于是参数为 NULL 时直接报错：

| 写法 | PG 报错 | 触发条件 |
|---|---|---|
| `(:p is null or col = :p)`（**时间戳**参数） | `could not determine data type of parameter $N` | 该参数为 NULL |
| `concat('%', :q, '%')` / `(:p is null or …)` 里的 **`\|\|` 拼接参数** | `function lower(bytea) does not exist` / `operator does not exist: character varying ~~ bytea` | PG 把未定类型的 `\|\|` 解析成 bytea 版本 |

**为什么测试抓不到**：Java 测试跑在 **H2** 上，H2 对这两种写法一概接受。
`mvn verify` 全绿 ≠ 真 PG 可用 —— 实测 `GET /content/publish-events`、
`GET /audit-logs`、`GET /users` 三个端点清空筛选即 500，而测试一直绿。

**正确写法**：给参与「空值判断」与「字符串拼接」的参数加显式 cast，
例如 `(cast(:p as string) is null or col = :p)`、`concat('%', cast(:q as string), '%')`。
cast 只影响该次出现，比较那一侧仍由列提供类型，语义逐字不变。

## 门禁规则

扫描 `services/java/src/main/java/**/*.java` 的 JPQL 字符串（`@Query` 注解的实参），
命中以下任一即失败（注释行除外）：

1. `(:param is null or` 而未包 `cast(`；
2. `concat(` 或 `||` 拼接里出现裸的 `:param`。

退出码：0 = 通过；1 = 有违规（逐条打印文件:行号与修法）。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JAVA_MAIN = ROOT / "services" / "java" / "src" / "main" / "java"

# `(:p is null or ...)` —— 参数出现在裸的空值判断里
NULLABLE_CHECK = re.compile(r"\(\s*:(\w+)\s+is\s+null\s+or", re.IGNORECASE)
# concat('%', :q, ...) / ('%' || :q || '%')
CONCAT_PARAM = re.compile(r"concat\s*\([^)]*?:(?P<name>\w+)[^)]*?\)", re.IGNORECASE)
PIPE_PARAM = re.compile(r"\|\|\s*:(?P<name>\w+)|:(?P<name2>\w+)\s*\|\|", re.IGNORECASE)
CAST_AROUND = re.compile(r"cast\s*\(\s*:\w+\s+as\s+\w+\s*\)", re.IGNORECASE)


def is_comment(line: str) -> bool:
    s = line.lstrip()
    return s.startswith("*") or s.startswith("//") or s.startswith("/*")


def scan_file(path: Path) -> list[tuple[int, str, str]]:
    """返回 [(行号, 原文, 原因)]。"""
    hits: list[tuple[int, str, str]] = []
    for idx, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or is_comment(line):
            continue
        # 规则 1：裸的空值判断（整行里没有 cast 包住该参数即算违规）
        for m in NULLABLE_CHECK.finditer(line):
            if not CAST_AROUND.search(line):
                hits.append((idx, line, f"(:{m.group(1)} is null or …) 未加 cast → PG 无法推断参数类型"))
        # 规则 2：拼接里的裸参数
        for regex in (CONCAT_PARAM, PIPE_PARAM):
            for m in regex.finditer(line):
                name = m.groupdict().get("name") or m.groupdict().get("name2")
                if name and f":{name}" not in {c.group(0) for c in CAST_AROUND.finditer(line)}:
                    if not CAST_AROUND.search(line):
                        hits.append((idx, line, f"拼接里的 :{name} 未加 cast → PG 会按 bytea 解析"))
    return hits


def main() -> int:
    if not JAVA_MAIN.is_dir():
        print(f"跳过：找不到 {JAVA_MAIN}")
        return 0
    violations: list[tuple[Path, int, str, str]] = []
    scanned = 0
    for path in JAVA_MAIN.rglob("*.java"):
        scanned += 1
        for lineno, text, reason in scan_file(path):
            violations.append((path, lineno, text, reason))

    if not violations:
        print(f"ok：{scanned} 个 Java 文件的 JPQL 无可空/拼接裸参数（PG 安全写法）")
        return 0

    print(f"✗ 发现 {len(violations)} 处 PG 会判为无类型参数的 JPQL 写法：\n")
    for path, lineno, text, reason in violations:
        rel = path.relative_to(ROOT)
        print(f"  {rel}:{lineno}")
        print(f"      {text}")
        print(f"      → {reason}")
    print(
        "\n修法：给该次出现的参数加显式 cast，例如"
        "\n  and (cast(:targetType as string) is null or a.targetType = :targetType)"
        "\n  concat('%', cast(:q as string), '%')"
        "\n（cast 类型取实体的字段类型：string / long / short / timestamp）"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
