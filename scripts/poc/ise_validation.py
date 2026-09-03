"""ISE 批量对照验证脚本：SpeechOcean762 人工标注（gold 0-10） vs 讯飞 ISE 评分（0-100）。

用途（发音评测准确性实证）：
- 从本地素材库 `local/english-audio/01-speechocean762/`（2500 句 ESL + 句级人工评分/词级/音素级标注）
  按 gold 总分抽 低/中/高 三档样本，逐句走真 ISE（in-process ISEClient，与 /api/v1/score 同源）；
- 输出 TSV 对照表 + 汇总：gold→ISE 皮尔逊相关、各档 ISE 均值（分档单调性）、失败数。

用法（services/python 目录，需 .env 有 ISE 三件套 + 本地素材已按 README 准备好）：
    uv run python ../scripts/poc/ise_validation.py            # 默认每档 30 句
    uv run python ../scripts/poc/ise_validation.py --per-band 10 --out ../local/out.tsv
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import os
import random
import sys
import time
from pathlib import Path

# 素材库（local/，gitignored，不入库）
_LOCAL = (
    Path(__file__).resolve().parents[2]
    / "local"
    / "english-audio"
    / "01-speechocean762"
)
_SERVICE_DIR = Path(__file__).resolve().parents[2] / "services" / "python"
if str(_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICE_DIR))

BANDS: dict[str, tuple[float, float]] = {
    "low": (0.0, 5.0),  # gold total 0-5 低档
    "mid": (6.0, 8.0),  # 6-8 中档
    "high": (9.0, 10.0),  # 9-10 高档（语料分布 max=10）
}


def _load_metadata() -> list[dict]:
    rows = []
    with open(_LOCAL / "metadata.tsv", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            rows.append(
                {
                    "utt": r["utt_name"],
                    "spk": r["spk"],
                    "text": r["text"],
                    "gold_total": float(r["total"]),
                    "gold_acc": float(r["accuracy"]),
                    "gold_flu": float(r["fluency"]),
                }
            )
    return rows


def _sample_bands(
    rows: list[dict], per_band: int, seed: int = 42
) -> dict[str, list[dict]]:
    """按 gold 总分分档抽样（固定种子可复现）。"""
    rng = random.Random(seed)
    out: dict[str, list[dict]] = {}
    for band, (lo, hi) in BANDS.items():
        pool = [r for r in rows if lo <= r["gold_total"] <= hi]
        if len(pool) < per_band:
            print(f"[warn] {band}: 样本不足（{len(pool)} < {per_band}），取全部")
        out[band] = rng.sample(pool, min(per_band, len(pool)))
        print(f"[band] {band}: 候选 {len(pool)} → 取 {len(out[band])}")
    return out


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx == 0 or vy == 0:
        return None
    return cov / (vx**0.5 * vy**0.5)


async def _run_check(per_band: int, sleep_s: float) -> list[dict]:
    from dotenv import load_dotenv

    load_dotenv(_SERVICE_DIR / ".env")
    from app.audio.ise import ISEClient

    rows = _load_metadata()
    print(f"[data] 语料 {len(rows)} 句（gold 0-10）")
    bands = _sample_bands(rows, per_band)
    if sum(len(v) for v in bands.values()) == 0:
        print("无样本，先按 local/english-audio/README.md 准备素材")
        return []

    client = ISEClient(
        app_id=os.environ.get("APP_ISE_APP_ID", ""),
        api_key=os.environ.get("APP_ISE_API_KEY", ""),
        api_secret=os.environ.get("APP_ISE_API_SECRET", ""),
    )
    records: list[dict] = []
    total = sum(len(v) for v in bands.values())
    done = 0
    for band, items in bands.items():
        for r in items:
            done += 1
            rec = {
                "band": band,
                "utt": r["utt"],
                "spk": r["spk"],
                "text": r["text"],
                "gold_total": r["gold_total"],
                "gold_acc": r["gold_acc"],
                "gold_flu": r["gold_flu"],
                "ise_overall": "",
                "ise_pron": "",
                "ise_flu": "",
                "ise_completeness": "",
                "ise_words": "",
                "ms": "",
                "error": "",
            }
            try:
                audio = (_LOCAL / "wavs" / f"{r['utt']}.wav").read_bytes()
                t0 = time.perf_counter()
                s = await client.score(audio, r["text"])
                rec.update(
                    {
                        "ise_overall": round(s.overall, 2),
                        "ise_pron": round(s.pronunciation, 2),
                        "ise_flu": round(s.fluency, 2),
                        "ise_completeness": round(s.completeness, 2),
                        "ise_words": len(s.word_level),
                        "ms": int((time.perf_counter() - t0) * 1000),
                    }
                )
            except (
                ValueError,
                RuntimeError,
                OSError,
            ) as e:  # 网络/额度/解析失败：记 error 继续
                rec["error"] = f"{type(e).__name__}: {str(e)[:120]}"
            records.append(rec)
            if done % 10 == 0:
                print(f"[progress] {done}/{total}")
            await asyncio.sleep(sleep_s)
    return records


def _write_tsv(out_path: Path, records: list[dict]) -> None:
    header = [
        "band",
        "utt",
        "spk",
        "text",
        "gold_total",
        "gold_acc",
        "gold_flu",
        "ise_overall",
        "ise_pron",
        "ise_flu",
        "ise_completeness",
        "ise_words",
        "ms",
        "error",
    ]
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header, delimiter="\t", extrasaction="ignore")
        w.writeheader()
        w.writerows(records)


def _print_summary(records: list[dict]) -> None:
    ok = [r for r in records if not r["error"]]
    print(f"\n[summary] 成功 {len(ok)}/{len(records)}；失败 {len(records) - len(ok)}")
    if ok:
        for dim, gold_key, ise_key in [
            ("gold_total→ise_overall", "gold_total", "ise_overall"),
            ("gold_acc→ise_pron", "gold_acc", "ise_pron"),
            ("gold_flu→ise_flu", "gold_flu", "ise_flu"),
        ]:
            xs = [float(r[gold_key]) for r in ok]
            ys = [float(r[ise_key]) for r in ok]
            print(f"  pearson({dim}) = {_pearson(xs, ys):.3f}")
        print("  各档 ISE overall 均值：")
        for band in BANDS:
            vals = [
                float(r["ise_overall"])
                for r in ok
                if r["band"] == band and r["ise_overall"] != ""
            ]
            if vals:
                print(
                    f"    {band:5s} n={len(vals):3d} mean={sum(vals) / len(vals):6.2f}"
                )


def main() -> int:
    ap = argparse.ArgumentParser(description="ISE gold 对照验证（SpeechOcean762）")
    ap.add_argument("--per-band", type=int, default=30, help="每档抽样句数（默认 30）")
    ap.add_argument("--seed", type=int, default=42, help="抽样随机种子")
    ap.add_argument("--sleep", type=float, default=0.4, help="调用间隔秒（防限流）")
    ap.add_argument("--out", type=Path, default=None, help="报告输出路径")
    args = ap.parse_args()
    out_path = args.out or _LOCAL / f"ise_validation_{time.strftime('%Y%m%d_%H%M')}.tsv"
    records = asyncio.run(_run_check(args.per_band, args.sleep))
    _write_tsv(out_path, records)
    _print_summary(records)
    print(f"\n[out] {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
