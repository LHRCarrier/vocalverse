#!/usr/bin/env python3
"""TTS 健康检查脚本（对应审计项 TTS-A01 可用性 / TTS-A02 响应时延 / TTS-A05 合成 RTF）。

用法:
    python check_tts.py [--url http://127.0.0.1:8000/api/v1/tts] [--text 你好世界]

检查内容:
    1. HTTP 状态码（期望 200）
    2. 契约校验：envelope code == 0，data.audio_bytes（hex）解码非空，且长度与 data.length 一致
    3. 实时率 RTF：仅当音频可解析出时长时计算（RIFF/WAV 头）；MP3（edge-tts 真实输出）无
       stdlib 解析器，跳过并显式提示，不因此判定失败

要求: httpx 库（services/python 已依赖，用项目环境执行无需单独安装）；超时 5 秒。
退出码: 0 = 通过；1 = 不通过（供 CI / cron 调度）。

2026-09-02 契约对齐修订（PR#23 审核意见 B1/B3）：
- 端点默认值由占位符 http://x.x.x.x:8081/tts 改为 http://127.0.0.1:8000/api/v1/tts
  （仓库真实拓扑：python:8000 的 /api/v1/tts，nginx 同源 /api/v1/tts；8081 全仓不存在）；
- 判定口径由「Content-Type: audio/wav + 响应体原始音频」改为「Envelope JSON + audio_bytes 的 hex」
  （app/api/routes/audio.py L62-70：POST /api/v1/tts → {code, message:"ok", data:{audio_bytes:<hex>, length}};
   原脚本期望原始 WAV 字节，在健康服务上必然报「不通过」；
   另注意真实 edge-tts 输出为 MP3（app/practice/orchestrator.py 落盘 .mp3）,RTF 仅 WAV 可算，跳过不判失败）；
- 契约变更预留：M2 若按 docs/06 §8 改为二进制/URL 响应，需同步更新 parse_tts_payload 与判定。
"""

import argparse
import io
import sys
import time
import wave

import httpx

try:  # Windows 审计机 cp936 控制台：确保中文输出可读（失败不影响运行）
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DEFAULT_URL = "http://127.0.0.1:8000/api/v1/tts"
DEFAULT_TEXT = "你好世界"
TIMEOUT = 5  # 秒（连接 + 读取）


def envelope_code(resp: httpx.Response):
    """提取 envelope 的业务码 code；非 JSON 或不符合契约时返回 None。"""
    try:
        data = resp.json()
    except ValueError:
        return None
    if isinstance(data, dict) and isinstance(data.get("code"), int):
        return data["code"]
    return None


def parse_tts_payload(resp: httpx.Response) -> tuple[bytes | None, int | None, str | None]:
    """从 envelope 响应解析音频字节与声明长度：{code, message, data: {audio_bytes: hex, length}}。

    返回 (audio_bytes, declared_length, error)；非 envelope/解码失败时 error 给出原因。
    """
    try:
        data = resp.json()
    except ValueError:
        return None, None, "响应非 JSON（期望 Envelope 契约）"
    if not isinstance(data, dict):
        return None, None, "响应非 JSON 对象"
    payload = data.get("data")
    if not isinstance(payload, dict):
        return None, None, f"data 非对象：{data!r}"
    hex_str = payload.get("audio_bytes")
    if not isinstance(hex_str, str) or not hex_str:
        return None, None, "data.audio_bytes 缺失或为空（M2 改二进制/URL 契约时需同步本脚本）"
    try:
        audio = bytes.fromhex(hex_str)
    except ValueError:
        return None, None, "data.audio_bytes 不是合法 hex"
    length = payload.get("length")
    if not isinstance(length, int):
        length = None
    return audio, length, None


def wav_duration(data: bytes):
    """解析 WAV 头得到音频时长（秒）；非标准 WAV 返回 None。"""
    try:
        with wave.open(io.BytesIO(data), "rb") as w:
            frames = w.getnframes()
            rate = w.getframerate()
            return frames / rate if rate else None
    except (wave.Error, EOFError):
        return None


def verdict(
    status_code: int, code, audio: bytes | None, declared_len: int | None
) -> tuple[bool, str]:
    """纯判定函数（不访问网络，供回归测试直接断言）。

    通过口径：HTTP 200 + envelope code==0（若为 envelope）+ 音频字节非空 + 长度一致（若声明）。
    """
    if status_code != 200:
        return False, f"HTTP {status_code} != 200"
    if code is not None and code != 0:
        return False, f"envelope code={code} != 0"
    if not audio:
        return False, "音频数据为空"
    if declared_len is not None and len(audio) != declared_len:
        return False, f"长度不一致：实际 {len(audio)} != 声明 {declared_len}"
    return True, ""


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
        # 表单提交 text 字段（对齐项目 /api/v1/tts 契约；voice/rate 走服务端默认）
        resp = httpx.post(
            args.url,
            data={"text": args.text},
            timeout=TIMEOUT,
        )
        elapsed = time.perf_counter() - start
    except httpx.TimeoutException:
        print(f"[TTS] 请求超时（>{TIMEOUT}s）")
        return 1
    except httpx.RequestError as exc:
        print(f"[TTS] 连接失败: {exc}")
        return 1

    code = envelope_code(resp)
    audio, declared_len, parse_err = parse_tts_payload(resp)
    ok, reason = verdict(resp.status_code, code, audio, declared_len)

    print(f"[TTS] HTTP 状态码: {resp.status_code}")
    print(f"[TTS] Content-Type: {resp.headers.get('Content-Type', '(无)')}（仅提示，不作判定）")
    if code is not None:
        print(f"[TTS] envelope code: {code}（0=成功）")
    if parse_err:
        print(f"[TTS] 契约解析: 失败 - {parse_err}")
    else:
        print(f"[TTS] 音频大小: {len(audio)} bytes（契约声明 {declared_len}）")
    print(f"[TTS] 总耗时: {elapsed:.3f}s")
    if not parse_err:
        duration = wav_duration(audio)
        if duration is not None:
            rtf = elapsed / duration
            print(f"[TTS] 音频时长: {duration:.3f}s")
            print(
                f"[TTS] 实时率 RTF = {elapsed:.3f} / {duration:.3f} = {rtf:.3f} "
                + ("（快于实时, 合成速度达标）" if rtf <= 1 else "（慢于实时, 建议排查）")
            )
        else:
            print("[TTS] 音频时长: 未知（非 RIFF/WAV；edge-tts 真实输出为 MP3，RTF 跳过计算，不作判定）")
    print(f"[TTS] 判定: {reason if reason else '契约校验通过'}")

    print(f"[TTS] 结果: {'通过' if ok else '不通过'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
