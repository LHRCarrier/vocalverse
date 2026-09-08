"""参考旋律提取单元测试（docs/06 §9.4 + 唱歌 P0 D1/D6；CI 零真 Key/零模型）。

覆盖：FakePitchExtractor 结构 / slice_window 窗口切片与全清音 / 路径归一（A-G7 三义性）/
音名换算；jobs 层（任务状态机、委托 camelCase、失败重试、补偿）见 test_pitch_jobs.py。
"""

from __future__ import annotations

import math
import wave
from pathlib import Path

from app.audio.pitch import (
    EXTRACTOR_VERSION,
    FakePitchExtractor,
    _midi_to_name,
    resolve_audio_path,
    slice_window,
)


def _make_wav(path: Path, duration_s: float = 1.0, sr: int = 16000) -> Path:
    import numpy as np

    t = np.linspace(0, duration_s, int(sr * duration_s), endpoint=False)
    data = (0.5 * np.sin(2 * math.pi * 440 * t) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(data.tobytes())
    return path


def test_fake_extractor_track_structure(tmp_path):
    wav = _make_wav(tmp_path / "tone.wav")
    track = FakePitchExtractor().extract_track(str(wav))
    assert track.sr == 16000
    assert len(track.f0) == len(track.names) == len(track.midi) == len(track.times_ms)
    assert all(v == 440.0 for v in track.f0)
    assert track.names[0] == "A4"


def test_slice_window_keeps_frames_and_marks_unvoiced_boundaries(tmp_path):
    # 构造 0(清音) + 440Hz 帧序列：窗口应只含窗口内帧
    from app.audio.pitch import TrackF0

    sr = 16000
    hop = 512
    n = 50
    track = TrackF0(
        sr=sr,
        hop_ms=1000.0 * hop / sr,
        times_ms=[i * 1000.0 * hop / sr for i in range(n)],
        f0=[0.0] * 5 + [440.0] * (n - 5),
        midi=[None] * 5 + [69] * (n - 5),
        names=[None] * 5 + ["A4"] * (n - 5),
        duration_ms=n * 1000.0 * hop / sr,
    )
    start = 3 * hop / sr * 1000  # 第 3 帧起
    end = 10 * hop / sr * 1000  # 第 10 帧止
    payload = slice_window(track, start, end)
    assert payload["start_ms"] == int(start)
    assert payload["end_ms"] == int(end)
    # 窗口保留框定帧（含清音帧——评分层按 D5 缺失降权，提取层不做掩盖）
    assert len(payload["f0s"]) == 7  # 帧 3..9
    assert sum(1 for v in payload["f0s"] if v == 440.0) == 5  # 帧 5..9 有声
    # 纯内容窗口 → 全 voiced
    voiced = slice_window(track, 6 * hop / sr * 1000, 10 * hop / sr * 1000)
    assert all(v == 440.0 for v in voiced["f0s"])
    # 全清音窗口 → f0s 全 0（评分层按缺失降权 D5，不伪造）
    silent = slice_window(track, 0.0, 2 * hop / sr * 1000)
    assert all(v == 0.0 for v in silent["f0s"])


def test_resolve_audio_path_precedence(tmp_path):
    # ① 原样存在 → 用之
    direct = tmp_path / "twinkle.wav"
    direct.write_bytes(b"x")
    assert resolve_audio_path(str(direct), str(tmp_path)) == str(direct)
    # ② 共享卷路径（/data/audio/xxx）→ audio_dir/<basename>
    (tmp_path / "moon.wav").write_bytes(b"x")
    assert resolve_audio_path("/data/audio/moon.wav", str(tmp_path)) == str(tmp_path / "moon.wav")
    # ③ 远程 URL（D1 不引下载）与不存在 → None
    assert resolve_audio_path("https://cdn.example.com/song.wav", str(tmp_path)) is None
    assert resolve_audio_path("/data/audio/nope.wav", str(tmp_path)) is None
    assert resolve_audio_path(None, str(tmp_path)) is None


def test_midi_to_name():
    assert _midi_to_name(60) == "C4"  # 中央 C
    assert _midi_to_name(69) == "A4"
    assert _midi_to_name(61) == "C#4"


def test_extractor_version_stable():
    assert EXTRACTOR_VERSION == "pyin-v1"
