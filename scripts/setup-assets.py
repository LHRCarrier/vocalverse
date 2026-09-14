"""素材物化脚本（D-G2 · 2026-09-09）：合成「旋律主导」演示曲目 + 生成歌曲种子 JSON。

背景（local/唱歌P0六项实施计划书 D1）：参考旋律提取（pyin）需要「旋律主导」音频输入；
仓库红线禁止提交原始音频/商用音乐，故音频**不入库**（`data/audio/` gitignored），
本脚本确定性重建（同一输入 → 同一输出），元数据入 `data/seed/songs.json`。

素材来源与版权：旋律全部为**公有领域**童谣/古典主题（Twinkle 1761 / Ode to Joy 1824 /
Mary Had a Little Lamb 1830s），歌词同为公有领域；演奏为**本脚本合成音色**（自研录音，
`source='original'`）——不涉及任何第三方录音授权。

用法（任选其一）：
    cd services/python && uv run python ../../scripts/setup-assets.py
    python scripts/setup-assets.py            # 需 numpy + soundfile 可用

产物：
    data/audio/song_*.wav      合成旋律（16-bit PCM，22050Hz 单声道；本地共享卷，gitignored）
    data/seed/songs.json       歌曲元数据 + 逐句时间戳（入库；Java SongSeeder 读取）
    data/seed/lrc/*.lrc        逐句 LRC 文本（入库，便于人工核对/管理端展示）
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
AUDIO_DIR = REPO_ROOT / "data" / "audio"
SEED_DIR = REPO_ROOT / "data" / "seed"
LRC_DIR = SEED_DIR / "lrc"

SR = 22050
BPM = 100.0
BEAT_MS = 60_000.0 / BPM  # 四分音符时长（600ms）

# 十二平均律频率（A4=440）：C4 起
_NOTE_BASE = {"C": -9, "C#": -8, "D": -7, "D#": -6, "E": -5, "F": -4, "F#": -3,
              "G": -2, "G#": -1, "A": 0, "A#": 1, "B": 2}


def note_hz(name: str) -> float:
    """音名 → 频率（如 'C4'/'F#5'；A4=440Hz，十二平均律）。"""
    pitch, octave = name[:-1], int(name[-1])
    semitones = _NOTE_BASE[pitch] + (octave - 4) * 12
    return 440.0 * (2 ** (semitones / 12.0))


# ---------------------------------------------------------------------------
# 曲目定义：每行 = 一句歌词 + 该句旋律（(音名, 拍数) 序列）
# 公有领域旋律；歌词公有领域（英文原文）。
# ---------------------------------------------------------------------------
SONGS = [
    {
        "slug": "twinkle",
        "title": "Twinkle Twinkle Little Star",
        "artist": "Traditional · 合成旋律（公有领域童谣）",
        "level": 1,
        "bpm": BPM,
        "musical_key": "C",
        "interest_tags": ["nursery", "classic"],
        "lines": [
            ("Twinkle, twinkle, little star,", [("C4", 1), ("C4", 1), ("G4", 1), ("G4", 1), ("A4", 1), ("A4", 1), ("G4", 2)]),
            ("How I wonder what you are.", [("F4", 1), ("F4", 1), ("E4", 1), ("E4", 1), ("D4", 1), ("D4", 1), ("C4", 2)]),
            ("Up above the world so high,", [("G4", 1), ("G4", 1), ("F4", 1), ("F4", 1), ("E4", 1), ("E4", 1), ("D4", 2)]),
            ("Like a diamond in the sky.", [("G4", 1), ("G4", 1), ("F4", 1), ("F4", 1), ("E4", 1), ("E4", 1), ("D4", 2)]),
            ("Twinkle, twinkle, little star,", [("C4", 1), ("C4", 1), ("G4", 1), ("G4", 1), ("A4", 1), ("A4", 1), ("G4", 2)]),
            ("How I wonder what you are.", [("F4", 1), ("F4", 1), ("E4", 1), ("E4", 1), ("D4", 1), ("D4", 1), ("C4", 2)]),
        ],
    },
    {
        "slug": "ode-to-joy",
        "title": "Ode to Joy",
        "artist": "Beethoven · 合成旋律（公有领域主题）",
        "level": 2,
        "bpm": BPM,
        "musical_key": "C",
        "interest_tags": ["classic", "anthem"],
        "lines": [
            ("Joy, bright spark of divinity,", [("E4", 1), ("E4", 1), ("F4", 1), ("G4", 1), ("G4", 1), ("F4", 1), ("E4", 1), ("D4", 1)]),
            ("Daughter of Elysium,", [("C4", 1), ("C4", 1), ("D4", 1), ("E4", 1), ("E4", 1.5), ("D4", 0.5), ("D4", 2)]),
            ("Fire-inspired we tread", [("E4", 1), ("E4", 1), ("F4", 1), ("G4", 1), ("G4", 1), ("F4", 1), ("E4", 1), ("D4", 1)]),
            ("Thy sanctuary.", [("C4", 1), ("C4", 1), ("D4", 1), ("E4", 1), ("D4", 1.5), ("C4", 0.5), ("C4", 2)]),
        ],
    },
    {
        "slug": "mary-lamb",
        "title": "Mary Had a Little Lamb",
        "artist": "Traditional · 合成旋律（公有领域童谣）",
        "level": 1,
        "bpm": BPM,
        "musical_key": "C",
        "interest_tags": ["nursery", "easy"],
        "lines": [
            ("Mary had a little lamb,", [("E4", 1), ("D4", 1), ("C4", 1), ("D4", 1), ("E4", 1), ("E4", 1), ("E4", 2)]),
            ("Its fleece was white as snow.", [("D4", 1), ("D4", 1), ("D4", 2), ("E4", 1), ("G4", 1), ("G4", 2)]),
            ("And everywhere that Mary went,", [("E4", 1), ("D4", 1), ("C4", 1), ("D4", 1), ("E4", 1), ("E4", 1), ("E4", 1), ("E4", 1)]),
            ("The lamb was sure to go.", [("D4", 1), ("D4", 1), ("E4", 1), ("D4", 1), ("C4", 4)]),
        ],
    },
]


def synth_note(freq: float, dur_s: float) -> list[float]:
    """单音符：正弦 + 2/3 次谐波 + ADSR 包络（避免爆音；纯净利于 pyin 提取）。"""
    n = max(1, int(SR * dur_s))
    attack, decay, release = int(SR * 0.015), int(SR * 0.06), int(SR * 0.08)
    out = []
    for i in range(n):
        t = i / SR
        # 基频 + 谐波（音色略暖，pyin 对基频仍稳定）
        sample = (
            math.sin(2 * math.pi * freq * t)
            + 0.28 * math.sin(2 * math.pi * freq * 2 * t)
            + 0.10 * math.sin(2 * math.pi * freq * 3 * t)
        ) / 1.38
        # ADSR
        if i < attack:
            env = i / attack
        elif i < attack + decay:
            env = 1.0 - 0.25 * (i - attack) / decay
        elif i >= n - release:
            env = 0.75 * max(0.0, (n - i) / release)
        else:
            env = 0.75
        out.append(sample * env)
    return out


def build_track(lines) -> tuple[list[float], list[dict]]:
    """合成整轨 + 返回逐句窗口（offset_ms/end_offset_ms）。"""
    samples: list[float] = []
    windows: list[dict] = []
    gap = int(SR * 0.02)  # 音符间 20ms 静音（清浊门限据此断句）
    for text, notes in lines:
        start_ms = len(samples) / SR * 1000.0
        for name, beats in notes:
            dur_s = beats * BEAT_MS / 1000.0
            samples.extend(synth_note(note_hz(name), dur_s))
            samples.extend([0.0] * gap)
        end_ms = len(samples) / SR * 1000.0
        windows.append({"offset_ms": int(round(start_ms)), "end_offset_ms": int(round(end_ms)), "text": text})
    # 归一化到 0.7 峰值
    peak = max((abs(v) for v in samples), default=1.0)
    if peak > 0:
        samples = [v * (0.7 / peak) for v in samples]
    return samples, windows


def write_wav(path: Path, samples: list[float]) -> None:
    import numpy as np
    import soundfile as sf

    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), np.asarray(samples, dtype="float32"), SR, subtype="PCM_16")


def write_lrc(path: Path, title: str, artist: str, windows: list[dict]) -> None:
    def stamp(ms: int) -> str:
        m, s = divmod(ms / 1000.0, 60)
        return f"[{int(m):02d}:{s:05.2f}]"

    body = "\n".join(f"{stamp(w['offset_ms'])}{w['text']}" for w in windows)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"[ti:{title}]\n[ar:{artist}]\n[re:VocalVerse demo · public-domain melody]\n{body}\n",
        encoding="utf-8",
    )


def main() -> int:
    songs_out = []
    for song in SONGS:
        samples, windows = build_track(song["lines"])
        wav_name = f"song_{song['slug'].replace('-', '_')}.wav"
        write_wav(AUDIO_DIR / wav_name, samples)
        lrc_name = f"{song['slug']}.lrc"
        write_lrc(LRC_DIR / lrc_name, song["title"], song["artist"], windows)
        duration_s = int(round(len(samples) / SR))
        songs_out.append(
            {
                "title": song["title"],
                "artist": song["artist"],
                "level": song["level"],
                "duration_s": duration_s,
                "bpm": song["bpm"],
                "musical_key": song["musical_key"],
                "audio_url": f"/data/audio/{wav_name}",
                "vocal_ref_url": None,
                "lrc_url": f"/data/seed/lrc/{lrc_name}",
                "cover_url": None,
                "interest_tags": json.dumps(song["interest_tags"], ensure_ascii=False),
                "source": "original",
                "status": "published",
                "lines": windows,
            }
        )
        print(f"[assets] {song['title']}: {wav_name} {duration_s}s / {len(windows)} 句")

    SEED_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "note": "演示曲目元数据（旋律/歌词公有领域，演奏为本脚本合成 → source=original）；"
        "音频不入库，由 scripts/setup-assets.py 确定性重建到 data/audio/。",
        "songs": songs_out,
    }
    (SEED_DIR / "songs.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"[assets] 写入 {SEED_DIR / 'songs.json'}（{len(songs_out)} 首）")
    print("[assets] 完成：音频在 data/audio/（gitignored），元数据/lrc 在 data/seed/（入库）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
