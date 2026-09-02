#!/usr/bin/env python3
"""ISE 健康检查脚本（对应审计项 ISE-A01 可用性 / ISE-A02 响应时延 / ISE-A04 评分一致性）。

用法:
    python check_ise.py [--url http://x.x.x.x:8082/ise] [--audio test.wav] [--reference 你好世界]

检查内容:
    1. HTTP 状态码（期望 200）
    2. 总耗时
    3. 校验返回的 overall_score 是否在 0-100 之间（项目 attempts.overall_score 口径）
    （若返回符合项目 envelope 契约 {code, message, data}，同时校验 code == 0）

要求: requests 库；超时 5 秒；音频为 16k PCM（wav）。
退出码: 0 = 通过；1 = 不通过（供 CI / cron 调度）。
"""

import argparse
import os
import sys
import time

import requests

DEFAULT_URL = "http://x.x.x.x:8082/ise"
DEFAULT_AUDIO = "test.wav"
DEFAULT_REFERENCE = "你好世界"
TIMEOUT = 5  # 秒（连接 + 读取）
SCORE_MIN, SCORE_MAX = 0.0, 100.0


def envelope_code(resp: requests.Response):
    """提取 envelope 的业务码 code；非 JSON 或不符合契约时返回 None。"""
    try:
        data = resp.json()
    except ValueError:
        return None
    if isinstance(data, dict) and isinstance(data.get("code"), int):
        return data["code"]
    return None


def extract_overall_score(resp: requests.Response):
    """从响应中提取 overall_score（兼容 envelope data 与顶层字段）。"""
    try:
        data = resp.json()
    except ValueError:
        return None
    payload = data.get("data") if isinstance(data, dict) else None
    candidates = []
    if isinstance(payload, dict):
        candidates.append(payload)
    if isinstance(data, dict):
        candidates.append(data)
    for cand in candidates:
        for key in ("overall_score", "overall", "total_score", "score"):
            value = cand.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return float(value)
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="ISE 健康检查")
    parser.add_argument(
        "--url", default=DEFAULT_URL, help=f"ISE 接口地址（默认 {DEFAULT_URL}）"
    )
    parser.add_argument(
        "--audio",
        default=DEFAULT_AUDIO,
        help=f"16k PCM 测试音频（默认 {DEFAULT_AUDIO}）",
    )
    parser.add_argument(
        "--reference",
        default=DEFAULT_REFERENCE,
        help=f"参考文本（默认 {DEFAULT_REFERENCE}）",
    )
    args = parser.parse_args()

    try:
        with open(args.audio, "rb") as f:
            audio_bytes = f.read()
    except OSError as exc:
        print(f"[ISE] 无法读取测试音频 {args.audio}: {exc}")
        return 1

    print(f"[ISE] 目标: {args.url}")
    print(f"[ISE] 测试音频: {args.audio}（{len(audio_bytes)} bytes, 16k PCM）")
    print(f"[ISE] 参考文本: {args.reference}")

    try:
        start = time.perf_counter()
        # multipart 上传：音频文件 + 参考文本（对齐项目 /score 契约）
        resp = requests.post(
            args.url,
            files={"audio": (os.path.basename(args.audio), audio_bytes, "audio/wav")},
            data={"reference": args.reference},
            timeout=TIMEOUT,
        )
        elapsed = time.perf_counter() - start
    except requests.Timeout:
        print(f"[ISE] 请求超时（>{TIMEOUT}s）")
        return 1
    except requests.ConnectionError as exc:
        print(f"[ISE] 连接失败: {exc}")
        return 1

    score = extract_overall_score(resp)
    code = envelope_code(resp)
    business_ok = code is None or code == 0
    score_ok = score is not None and SCORE_MIN <= score <= SCORE_MAX

    print(f"[ISE] HTTP 状态码: {resp.status_code}")
    if code is not None:
        print(f"[ISE] envelope code: {code}（0=成功）")
    print(f"[ISE] 总耗时: {elapsed:.3f}s")
    if score is not None:
        print(
            f"[ISE] overall_score: {score:.2f}  -> 区间 [{SCORE_MIN}, {SCORE_MAX}]: {'是' if score_ok else '否'}"
        )
    else:
        print(
            "[ISE] overall_score: 未找到（检查返回字段名, 期望 overall_score/overall/total_score/score）"
        )

    ok = resp.status_code == 200 and business_ok and score_ok
    print(f"[ISE] 结果: {'通过' if ok else '不通过'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
