#!/usr/bin/env python3
"""ISE 评分健康检查脚本（对应审计项 ISE-A01 可用性 / ISE-A02 响应时延 / ISE-A04 评分一致性）。

用法:
    python check_ise.py [--url http://127.0.0.1:8000/api/v1/score] [--audio test.wav] [--reference 你好世界]

检查内容:
    1. HTTP 状态码（期望 200）
    2. 总耗时
    3. 契约校验：envelope code == 0 且 data.overall 在 0-100 之间
       （项目契约见 app/api/routes/audio.py L50-59：POST /api/v1/score →
        {code, message, data: ScoreResult{overall, pronunciation, fluency, ...}}；
        兼容历史字段名 overall_score/total_score/score 的返回）

要求: httpx 库（services/python 已依赖，用项目环境执行无需单独安装）；超时 5 秒；音频为 16k PCM（wav）。
退出码: 0 = 通过；1 = 不通过（供 CI / cron 调度）。

2026-09-02 契约对齐修订（PR#23 审核意见 B3）：
- 端点默认值由占位符 http://x.x.x.x:8082/ise 改为 http://127.0.0.1:8000/api/v1/score
  （仓库真实拓扑：python:8000 的 /api/v1/score，nginx 同源 /api/v1/score；8082 全仓不存在）；
- 字段名按契约修正为 data.overall（原文档串「overall_score / attempts.overall_score 口径」与实际不符）；
- HTTP 客户端由 requests 改为 httpx（对齐项目依赖，见 services/python/pyproject.toml）。
"""

import argparse
import os
import sys
import time

import httpx

try:  # Windows 审计机 cp936 控制台：确保中文输出可读（失败不影响运行）
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DEFAULT_URL = "http://127.0.0.1:8000/api/v1/score"
DEFAULT_AUDIO = "test.wav"
DEFAULT_REFERENCE = "你好世界"
TIMEOUT = 5  # 秒（连接 + 读取）
SCORE_MIN, SCORE_MAX = 0.0, 100.0


def envelope_code(resp: httpx.Response):
    """提取 envelope 的业务码 code；非 JSON 或不符合契约时返回 None。"""
    try:
        data = resp.json()
    except ValueError:
        return None
    if isinstance(data, dict) and isinstance(data.get("code"), int):
        return data["code"]
    return None


def extract_overall(resp: httpx.Response):
    """从响应中提取总分（契约字段 data.overall；兼容 envelope data 与顶层字段）。"""
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
        for key in ("overall", "overall_score", "total_score", "score"):
            value = cand.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return float(value)
    return None


def verdict(status_code: int, code, score) -> tuple[bool, str]:
    """纯判定函数（不访问网络，供回归测试直接断言）。

    通过口径：HTTP 200 + envelope code==0（若为 envelope）+ 0 <= overall <= 100。
    """
    if status_code != 200:
        return False, f"HTTP {status_code} != 200"
    if code is not None and code != 0:
        return False, f"envelope code={code} != 0"
    if score is None:
        return False, "overall 未找到（检查返回字段名, 契约期望 overall）"
    if not (SCORE_MIN <= score <= SCORE_MAX):
        return False, f"overall={score} 不在区间 [{SCORE_MIN}, {SCORE_MAX}]"
    return True, ""


def main() -> int:
    parser = argparse.ArgumentParser(description="ISE 健康检查")
    parser.add_argument(
        "--url", default=DEFAULT_URL, help=f"评分接口地址（默认 {DEFAULT_URL}）"
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
        # multipart 上传：音频文件 + 参考文本（对齐项目 /api/v1/score 契约）
        resp = httpx.post(
            args.url,
            files={"audio": (os.path.basename(args.audio), audio_bytes, "audio/wav")},
            data={"reference": args.reference},
            timeout=TIMEOUT,
        )
        elapsed = time.perf_counter() - start
    except httpx.TimeoutException:
        print(f"[ISE] 请求超时（>{TIMEOUT}s）")
        return 1
    except httpx.RequestError as exc:
        print(f"[ISE] 连接失败: {exc}")
        return 1

    score = extract_overall(resp)
    code = envelope_code(resp)
    ok, reason = verdict(resp.status_code, code, score)

    print(f"[ISE] HTTP 状态码: {resp.status_code}")
    if code is not None:
        print(f"[ISE] envelope code: {code}（0=成功）")
    print(f"[ISE] 总耗时: {elapsed:.3f}s")
    if score is not None:
        print(
            f"[ISE] overall: {score:.2f}  -> 区间 [{SCORE_MIN}, {SCORE_MAX}]: {'是' if SCORE_MIN <= score <= SCORE_MAX else '否'}"
        )
    else:
        print("[ISE] overall: 未找到（检查返回字段名, 契约期望 data.overall）")
    print(f"[ISE] 判定: {reason if reason else '契约校验通过'}")

    print(f"[ISE] 结果: {'通过' if ok else '不通过'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
