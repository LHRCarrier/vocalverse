#!/usr/bin/env python3
"""ASR 健康检查脚本（对应审计项 ASR-A01 可用性 / ASR-A02 时延 / ASR-A04 识别质量）。

用法:
    python check_asr.py [--url http://x.x.x.x:8080/asr] [--audio test.wav]

检查内容:
    1. HTTP 状态码（期望 200）
    2. 总耗时（端到端响应时间）
    3. 返回文本是否包含关键字 "成功"
    （若返回符合项目 envelope 契约 {code, message, data}，同时校验 code == 0）

要求: requests 库；超时 5 秒；音频为 16k PCM（wav）。
退出码: 0 = 通过；1 = 不通过（供 CI / cron 调度）。
"""

import argparse
import json
import os
import sys
import time

import requests

DEFAULT_URL = "http://x.x.x.x:8080/asr"
DEFAULT_AUDIO = "test.wav"
TIMEOUT = 5  # 秒（连接 + 读取）
KEYWORD = "成功"


def envelope_code(resp: requests.Response):
    """提取 envelope 的业务码 code；非 JSON 或不符合契约时返回 None。"""
    try:
        data = resp.json()
    except ValueError:
        return None
    if isinstance(data, dict) and isinstance(data.get("code"), int):
        return data["code"]
    return None


def extract_text(resp: requests.Response) -> str:
    """从响应中提取识别文本，兼容 envelope 与裸文本两种返回。"""
    try:
        data = resp.json()
    except ValueError:
        return resp.text
    payload = data.get("data") if isinstance(data, dict) else None
    if isinstance(payload, dict):
        for key in ("text", "transcript", "result"):
            value = payload.get(key)
            if isinstance(value, str):
                return value
        return json.dumps(payload, ensure_ascii=False)
    if isinstance(payload, str):
        return payload
    return json.dumps(data, ensure_ascii=False)


def main() -> int:
    parser = argparse.ArgumentParser(description="ASR 健康检查（16k PCM）")
    parser.add_argument(
        "--url", default=DEFAULT_URL, help=f"ASR 接口地址（默认 {DEFAULT_URL}）"
    )
    parser.add_argument(
        "--audio",
        default=DEFAULT_AUDIO,
        help=f"16k PCM 测试音频（默认 {DEFAULT_AUDIO}）",
    )
    args = parser.parse_args()

    try:
        with open(args.audio, "rb") as f:
            audio_bytes = f.read()
    except OSError as exc:
        print(f"[ASR] 无法读取测试音频 {args.audio}: {exc}")
        return 1

    print(f"[ASR] 目标: {args.url}")
    print(f"[ASR] 测试音频: {args.audio}（{len(audio_bytes)} bytes, 16k PCM）")

    try:
        start = time.perf_counter()
        # multipart 上传（对齐项目 /asr 契约: audio 文件字段）
        resp = requests.post(
            args.url,
            files={"audio": (os.path.basename(args.audio), audio_bytes, "audio/wav")},
            timeout=TIMEOUT,
        )
        elapsed = time.perf_counter() - start
    except requests.Timeout:
        print(f"[ASR] 请求超时（>{TIMEOUT}s）")
        return 1
    except requests.ConnectionError as exc:
        print(f"[ASR] 连接失败: {exc}")
        return 1

    text = extract_text(resp)
    hit = KEYWORD in text
    code = envelope_code(resp)
    business_ok = code is None or code == 0

    print(f"[ASR] HTTP 状态码: {resp.status_code}")
    if code is not None:
        print(f"[ASR] envelope code: {code}（0=成功）")
    print(f"[ASR] 总耗时: {elapsed:.3f}s")
    print(f"[ASR] 返回文本: {text[:200]}")
    print(f'[ASR] 包含关键字 "{KEYWORD}": {"是" if hit else "否"}')

    ok = resp.status_code == 200 and business_ok and hit
    print(f"[ASR] 结果: {'通过' if ok else '不通过'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
