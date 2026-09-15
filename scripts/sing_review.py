#!/usr/bin/env python3
"""SG-14 人工抽检一致性评审 CLI（FF 模糊化 · docs/06 §9.4）。

用法（仓库根 / services/python 均可运行）：

    uv run python scripts/sing_review.py tests/fixtures/review_agree.json
    uv run python scripts/sing_review.py local/review_real.json --title "真实抽检（演示数据替换）"

输入 JSON 结构（任一形态均可）：
    {"songs": [{"title": "...", "lines": [{"seq":1, "algo":95.0,
        "r1_lo":90,"r1_hi":96,"r2_lo":92,"r2_hi":97}, ...]}, ...]}

字段：algo = 算法分（0~100）；r1_lo/r1_hi、r2_lo/r2_hi = 两位评委的区间分
（区间宽度即犹豫度——评委只打区间，不强迫点值；点值 = lo==hi）。

产出：Markdown 评审报告（stdout，可重定向到文件入答辩材料）。评审口径/限制见
`services/python/app/audio/review.py` 模块 docstring；实盘数据放 `local/`
（gitignore；本仓只提交演示 fixtures——仓库红线：不提交真实用户数据）。

退出码：0 = 正常出报告；1 = 文件/格式错误。
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from pathlib import Path

# 允许从仓库根运行：把 services/python 加入导入路径（app.audio.review 所在）
_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "services" / "python"))

from app.audio.review import render_dataset  # noqa: E402


def _load_songs(path: Path) -> list[tuple[str, list[dict]]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        songs = data.get("songs", [data])
    elif isinstance(data, list):
        songs = data
    else:
        raise ValueError(f"{path.name}: 顶层须为对象/数组（见模块 docstring）")
    out: list[tuple[str, list[dict]]] = []
    for s in songs:
        if "lines" not in s:
            raise ValueError(f"{path.name}: 歌曲缺少 lines")
        out.append((str(s.get("title", path.stem)), list(s["lines"])))
    return out


def main() -> int:
    # Windows GBK 控制台打印中文/符号会炸（踩坑：check_feature_flags ✓ 字符）；
    # 新脚本内置规避，不依赖调用方设 PYTHONIOENCODING。
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="SG-14 抽检一致性评审（FF 模糊化）")
    ap.add_argument("files", nargs="+", type=Path, help="评审 JSON（见模块 docstring 结构）")
    ap.add_argument(
        "--title",
        default="VocalVerse 唱歌评分人工抽检（FF 模糊化一致性评审）",
        help="报告标题",
    )
    args = ap.parse_args()

    all_songs: list[tuple[str, list[dict]]] = []
    for path in args.files:
        if not path.exists():
            print(f"[错误] 文件不存在：{path}", file=sys.stderr)
            return 1
        try:
            all_songs.extend(_load_songs(path))
        except (json.JSONDecodeError, ValueError) as exc:
            print(f"[错误] {exc}", file=sys.stderr)
            return 1

    print(f"# {args.title}")
    print(f"\n> 数据源：{len(args.files)} 个文件 · {len(all_songs)} 首 · 生成时间：本地运行")
    print(render_dataset(all_songs).split("\n", 2)[2])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
