"""功能位对账脚本回归（arch-04）：parse_registry / check_rows 纯函数判定口径。

修复前失败：脚本/门禁不存在——登记表新增开关而 config.py 漏字段时 CI 无感（漂移静默）。
加载方式同 test_healthcheck_scripts.py：importlib 直接执行仓库根 scripts/ 下的脚本。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _repo_root() -> Path:
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "scripts" / "check_feature_flags.py").exists():
            return parent
    raise RuntimeError("未找到仓库根（scripts/check_feature_flags.py 缺失）")


ROOT = _repo_root()
_spec = importlib.util.spec_from_file_location(
    "ff_flags", ROOT / "scripts" / "check_feature_flags.py"
)
FF = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(FF)

parse_registry = FF.parse_registry
check_rows = FF.check_rows

REGISTRY_HEADER = "## 17. 功能位/配置开关登记表（arch-04）"
ROW_TPL = "| {name} | false | {loc} | 说明 | {readme} |"


def _rows(*pairs: tuple[str, str, str]) -> list[dict]:
    """(name, location, readme) 三元组 → 登记表文本 → 解析。"""
    lines = [
        REGISTRY_HEADER,
        "",
        "| 开关 | 默认 | 位置 | 说明 | README 登记 |",
        "|---|---|---|---|---|",
    ]
    for name, loc, readme in pairs:
        lines.append(ROW_TPL.format(name=name, loc=loc, readme=readme))
    return parse_registry("\n".join(lines))


def test_parse_registry_skips_head_and_next_section() -> None:
    rows = _rows(("APP_X_ENABLED", "python", "否"), ("VOICEVERSE_Y_ENABLED", "java", "是"))
    assert [(r["name"], r["location"], r["readme"]) for r in rows] == [
        ("APP_X_ENABLED", "python", "否"),
        ("VOICEVERSE_Y_ENABLED", "java", "是"),
    ]
    # 表格外的普通行不参与解析
    assert not parse_registry("| APP_Z | false | python | 说明 | 否 |")


def test_check_rows_python_field_missing_fails() -> None:
    rows = _rows(("APP_MISSING_ENABLED", "python", "否"))
    (_, ok, reason) = check_rows(rows, "agent_lab_enabled = True", "", "")[0]
    assert not ok
    assert "config.py 缺字段" in reason


def test_check_rows_python_word_boundary() -> None:
    """词边界：xxx_agent_lab_enabled_yyy 不冒充 agent_lab_enabled。"""
    rows = _rows(("APP_AGENT_LAB_ENABLED", "python", "否"))
    (_, ok, _) = check_rows(rows, "xxx_agent_lab_enabled_yyy = True", "", "")[0]
    assert not ok
    (_, ok, _) = check_rows(rows, "agent_lab_enabled = True", "", "")[0]
    assert ok


def test_check_rows_java_and_readme_requirements() -> None:
    row = _rows(("VOICEVERSE_COMMUNITY_POST_ENABLED", "java", "是"))
    # Java 缺环境变量 → 失败
    (_, ok, reason) = check_rows(row, "", "post-enabled: false", "")[0]
    assert not ok and "application.yml 缺" in reason
    # Java 有、README 漏登记 → 失败（对外演示开关）
    (_, ok, reason) = check_rows(
        row, "", "post-enabled: ${VOICEVERSE_COMMUNITY_POST_ENABLED:false}", ""
    )[0]
    assert not ok and "README.md 未登记" in reason
    # 两者齐 → 通过
    (_, ok, _) = check_rows(
        row,
        "",
        "post-enabled: ${VOICEVERSE_COMMUNITY_POST_ENABLED:false}",
        "VOICEVERSE_COMMUNITY_POST_ENABLED=true",
    )[0]
    assert ok
