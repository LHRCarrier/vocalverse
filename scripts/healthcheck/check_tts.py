#!/usr/bin/env python3
"""TTS 健康检查脚本（对应审计项 TTS-A01 可用性 / TTS-A02 响应时延 / TTS-A05 合成 RTF）。

用法:
    python check_tts.py [--url http://x.x.x.x:8081/tts] [--text 你好世界]

检查内容:
    1. HTTP 状态码（期望 200）
    2. 返回头 Content-Type 是否为 audio/wav
    3. 实时率 RTF = 总耗时 / 音频时长（RTF < 1 表示快于实时，合成速度达标）

要求: requests 库；超时 5 秒；音频时长从 WAV 头解析，无 ffprobe 依赖。
退出码: 0 = 通过；1 = 不通过（供 CI / cron 调度）。
"""

import argparse
import io
import sys
import time
import wave

import requests

DEFAULT_URL = "http://x.x.x.x:8081/tts"
DEFAULT_TEXT = "你好世界"
TIMEOUT = 5  # 秒（连接 + 读取）


def wav_duration(data: bytes):
    """解析 WAV 头得到音频时长（秒）；非标准 WAV 返回 None。"""
    try:
        with wave.open(io.BytesIO(data), "rb") as w:
            frames = w.getnframes()
            rate = w.getframerate()
            return frames / rate if rate else None
    except (wave.Error, EOFError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="TTS 健康检查")
    parser.add_argument(
        "--url", default=DEFAULT_URL, help=f"TTS 接口地址（默认 {DEFAULT_URL}）"
    )
    parser.add_argument(
        "--text", default=DEFAULT_TEXT, help=f"测试文本（默认 {DEFAULT_TEXT}）"
    )
    args = parser.parse_args()

    print(f"[TTS] 目标: {args.url}")
    print(f"[TTS] 测试文本: {args.text}")

    try:
        start = time.perf_counter()
        # 表单提交 text 字段（对齐项目 /tts 契约），响应体为音频字节
        resp = requests.post(
            args.url,
            data={"text": args.text},
            timeout=TIMEOUT,
        )
        elapsed = time.perf_counter() - start
    except requests.Timeout:
        print(f"[TTS] 请求超时（>{TIMEOUT}s）")
        return 1
    except requests.ConnectionError as exc:
        print(f"[TTS] 连接失败: {exc}")
        return 1

    content_type = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
    is_wav = content_type == "audio/wav"
    duration = wav_duration(resp.content)

    print(f"[TTS] HTTP 状态码: {resp.status_code}")
    print(
        f"[TTS] Content-Type: {resp.headers.get('Content-Type', '(无)')}  -> audio/wav: {'是' if is_wav else '否'}"
    )
    print(f"[TTS] 音频大小: {len(resp.content)} bytes")
    print(f"[TTS] 总耗时: {elapsed:.3f}s")
    if duration is not None:
        rtf = elapsed / duration
        print(f"[TTS] 音频时长: {duration:.3f}s")
        print(
            f"[TTS] 实时率 RTF = {elapsed:.3f} / {duration:.3f} = {rtf:.3f} "
            + ("（快于实时, 合成速度达标）" if rtf <= 1 else "（慢于实时, 建议排查）")
        )
    else:
        print("[TTS] 音频时长: 未知（非标准 WAV 头, 跳过 RTF 计算）")

    ok = resp.status_code == 200 and is_wav
    print(f"[TTS] 结果: {'通过' if ok else '不通过'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
