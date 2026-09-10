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
    PyinPitchExtractor,
    _midi_to_name,
    apply_voicing_gate,
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
    assert track.onsets_ms == []  # 假提取器不产 onset（真实 BPM 走时长比回退，口径 v3 item7）


def test_slice_window_keeps_frames_and_marks_unvoiced_boundaries(tmp_path):
    # 构造 0(清音) + 440Hz 帧序列：窗口应只含窗口内帧
    from app.audio.pitch import TrackF0

    sr = 16000
    hop = 512
    n = 50
    hop_ms = 1000.0 * hop / sr
    track = TrackF0(
        sr=sr,
        hop_ms=hop_ms,
        times_ms=[i * hop_ms for i in range(n)],
        f0=[0.0] * 5 + [440.0] * (n - 5),
        midi=[None] * 5 + [69] * (n - 5),
        names=[None] * 5 + ["A4"] * (n - 5),
        duration_ms=n * hop_ms,
        # 参考音符级 onset（pyin-v2）：100 / 300 / 900ms —— 窗口切片应只保留窗口内的
        onsets_ms=[100.0, 300.0, 900.0],
    )
    start = 3 * hop / sr * 1000  # 第 3 帧起（96ms）
    end = 10 * hop / sr * 1000  # 第 10 帧止（320ms）
    payload = slice_window(track, start, end)
    assert payload["start_ms"] == int(start)
    assert payload["end_ms"] == int(end)
    # 窗口保留框定帧（含清音帧——评分层按 D5 缺失降权，提取层不做掩盖）
    assert len(payload["f0s"]) == 7  # 帧 3..9
    assert sum(1 for v in payload["f0s"] if v == 440.0) == 5  # 帧 5..9 有声
    # pyin-v2 契约：窗口内参考 onset（100/300 落入 [96,320)；900 在窗外）
    assert payload["onsets_ms"] == [100.0, 300.0]
    # 纯内容窗口 → 全 voiced
    voiced = slice_window(track, 6 * hop / sr * 1000, 10 * hop / sr * 1000)
    assert all(v == 440.0 for v in voiced["f0s"])
    # 全清音窗口 → f0s 全 0（评分层按缺失降权 D5，不伪造）
    silent = slice_window(track, 0.0, 2 * hop / sr * 1000)
    assert all(v == 0.0 for v in silent["f0s"])
    assert silent["onsets_ms"] == []  # 窗外 onset 不入窗口（无窗内起音）


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
    """提取器世代：**pyin-v2** 起 pitch_ref 含参考音符级 onset（docs/06 §9.4 口径 v3 item7；
    BUG-1 修复）。世代升级 → jobs 扫描自动判定「世代旧」并重建（app/sing/jobs.py:_refs_ready）。"""
    assert EXTRACTOR_VERSION == "pyin-v2"


# ---------------------------------------------------------------------------
# 清浊门限（2026-09-09 真机回归：真人歌声 voicing prob 偏低，叠加门限会误杀整句）
# ---------------------------------------------------------------------------
def test_apply_voicing_gate_default_keeps_viterbi_flag():
    """默认门限 0：只信 librosa voiced_flag（viterbi 判决），低 vprob 帧必须保留。"""
    import numpy as np

    flag = np.array([True, True, False, True])
    prob = np.array([0.05, 0.55, 0.9, 0.01])  # 真人歌声的典型低 vprob
    out = apply_voicing_gate(flag, prob, threshold=0.0)
    assert list(out) == [True, True, False, True], "低 vprob 有声帧被误杀（回归：全句 no_pitch）"


def test_apply_voicing_gate_optional_threshold_filters():
    """显式调高门限（如 0.5）时叠加过滤——仅在需要更激进剔除静音时使用。"""
    import numpy as np

    flag = np.array([True, True, True])
    prob = np.array([0.05, 0.55, 0.9])
    assert list(apply_voicing_gate(flag, prob, threshold=0.5)) == [False, True, True]


def test_apply_voicing_gate_all_silent():
    """voiced_prob=None（全静音序列）→ 全 False。"""
    import numpy as np

    out = apply_voicing_gate(np.array([True, True]), None, threshold=0.0)
    assert not out.any()


def test_pyin_extractor_detects_onsets(tmp_path):
    """**口径 v3 item7**：节拍器（0.5s 间隔短脉冲）→ librosa.onset_detect →
    onset 间隔中位 ≈ 500ms（容差 ±100ms）。检测失败会静默回退（时长比），此用例防回退。"""
    import numpy as np
    import soundfile as sf

    sr = 16000
    dur_s = 3.0
    y = np.zeros(int(sr * dur_s), dtype=np.float32)
    for k in range(6):
        i = int(k * 0.5 * sr)
        n = int(0.03 * sr)
        y[i : i + n] += 0.8 * np.sin(2 * np.pi * 1000.0 * np.arange(n) / sr)
    path = tmp_path / "click.wav"
    sf.write(str(path), y, sr)

    track = PyinPitchExtractor().extract_track(str(path))
    assert len(track.onsets_ms) >= 4, f"应检测到 ≥4 个起音（实际 {len(track.onsets_ms)}）"
    diffs = np.diff(sorted(track.onsets_ms))
    keep = diffs[(diffs >= 200) & (diffs <= 3000)]
    assert abs(float(np.median(keep)) - 500.0) < 100.0, (
        f"IOI 应 ≈500ms（实际 {np.median(keep):.0f}ms）"
    )


# ---------------------------------------------------------------------------
# F0 起音（2026-09-10 评估结论：与频谱起音互补，评分层做 BPM 仲裁）
# ---------------------------------------------------------------------------
HOP = 32.0


def test_f0_onsets_staccato_and_legato():
    """换音点必须被检出：断奏（音符间 3 帧静音）与连奏（无静音）都要覆盖。"""
    from app.audio.pitch import f0_onsets_ms

    # 断奏：有声 10 帧 / 静音 3 帧 / 换音（跨短静音桥接）
    staccato = []
    for freq in (440.0, 550.0, 660.0):
        staccato += [freq] * 10 + [0.0] * 3
    ons = f0_onsets_ms(staccato, HOP)
    assert len(ons) >= 3, f"断奏应检出 ≥3 个起音（实际 {ons}）"
    # 连奏：直接换音（无静音）→ 靠音高跳变
    legato = [440.0] * 10 + [550.0] * 10 + [660.0] * 10
    ons2 = f0_onsets_ms(legato, HOP)
    assert len(ons2) >= 3, f"连奏应检出 ≥3 个起音（实际 {ons2}）"


def test_f0_onsets_repeat_note_blind_spot():
    """**记录 F0 起音的固有盲区**：同音重复（音高不变）无跳变 → 只检到段起点 1 个。

    这正是评分层需要 BPM 仲裁（combine_bpm）而非"F0 替换频谱"的原因
    （评估实测：同音重复场景 F0 全漏、频谱倍速，仲裁后误差由 88.3 → 15.8）。
    """
    from app.audio.pitch import f0_onsets_ms

    repeat = ([440.0] * 8 + [0.0] * 3) * 6
    ons = f0_onsets_ms(repeat, HOP)
    assert len(ons) == 1, f"同音重复应只检到 1 个段起点（实际 {ons}）"


def test_f0_onsets_silence_and_short_run():
    """全静音 → 空；过短有声段（<3 帧，噪声）→ 不产出起音。"""
    from app.audio.pitch import f0_onsets_ms

    assert f0_onsets_ms([0.0] * 40, HOP) == []
    assert f0_onsets_ms([0.0] * 10 + [440.0] * 2 + [0.0] * 10, HOP) == []


def test_track_provides_both_onset_channels(tmp_path):
    """提取器同时产出两路 onset（频谱 onsets_ms + F0 f0_onsets_ms）。"""
    track = FakePitchExtractor().extract_track(str(_make_wav(tmp_path / "tone2.wav")))
    assert hasattr(track, "f0_onsets_ms")
    assert isinstance(track.f0_onsets_ms, list)


def test_pyin_extracts_f0_from_noisy_singing_signal(tmp_path):
    """真机回归：带噪声的正弦（模拟真人唱歌的低 voicing prob）必须能提出 F0。

    修复前（清浊叠加门限 0.6）此用例失败：全部帧被判清音 → f0 全 0。
    """
    import numpy as np
    import soundfile as sf

    sr = 16000
    t = np.linspace(0, 2.0, sr * 2, endpoint=False)
    rng = np.random.default_rng(42)
    tone = 0.35 * np.sin(2 * np.pi * 440 * t)
    # 加性噪声 + 颤音（±1.5% 频率调制）→ 贴近真实歌声，voicing prob 显著低于 0.6
    noise = 0.12 * rng.standard_normal(len(t))
    vibrato = 0.015 * np.sin(2 * np.pi * 5.5 * t)
    signal = (tone + vibrato * tone + noise).astype("float32")
    path = tmp_path / "noisy.wav"
    sf.write(str(path), signal, sr)

    track = PyinPitchExtractor().extract_track(str(path))
    voiced = [v for v in track.f0 if v > 0]
    assert len(voiced) > len(track.f0) * 0.3, (
        f"有声帧过少（{len(voiced)}/{len(track.f0)}）——清浊门限误杀回归"
    )
    median = sorted(voiced)[len(voiced) // 2]
    assert 400 < median < 480, f"提取基频偏离 440Hz：{median:.1f}"
