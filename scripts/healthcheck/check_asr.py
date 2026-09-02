#!/usr/bin/env python3
"""ASR 健康检查脚本（对应审计项 ASR-A01 可用性 / ASR-A02 时延 / ASR-A04 识别质量）。

用法:
    python check_asr.py [--url http://127.0.0.1:8000/api/v1/asr] [--audio test.wav]

检查内容:
    1. HTTP 状态码（期望 200）
    2. 总耗时（端到端响应时间）
    3. 契约校验：envelope code == 0 且识别文本非空
       （项目契约见 app/api/routes/audio.py：POST /api/v1/asr → {code, message:"ok", data:{text, ...}}；
       同时兼容裸文本返回）

要求: httpx 库（services/python 已依赖，用项目环境执行无需单独安装）；超时 5 秒；音频为 16k PCM（wav）。
退出码: 0 = 通过；1 = 不通过（供 CI / cron 调度）。

2026-09-02 契约对齐修订（PR#23 审核意见 B2/B3）：
- 端点默认值由占位符 http://x.x.x.x:8080/asr 改为 http://127.0.0.1:8000/api/v1/asr
  （仓库真实拓扑：python:8000 的 /api/v1/asr，nginx 同源 /api/v1/asr；8080 为 Java API，/asr 路径不存在）；
- 判定口径由「返回文本包含关键字『成功』」改为「code == 0 且文本非空」
  （项目响应 message="ok"，识别文本不会出现「成功」，原口径在健康服务上必然误报）；
- HTTP 客户端由 requests 改为 httpx（对齐项目依赖，见 services/python/pyproject.toml）。
"""

import argparse
import json
import os
import sys
import time

import httpx

try:  # Windows 审计机 cp936 控制台：确保中文输出可读（失败不影响运行）
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DEFAULT_URL = "http://127.0.0.1:8000/api/v1/asr"
DEFAULT_AUDIO = "test.wav"
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


def extract_text(resp: httpx.Response) -> str:
    """从响应中提取识别文本，兼容 envelope（data.text）与裸文本两种返回。"""
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


def verdict(status_code: int, code, text: str, keyword: str | None = None) -> tuple[bool, str]:
    """纯判定函数（不访问网络，供回归测试直接断言）。

    通过口径：HTTP 200 + envelope code==0（若为 envelope）+ 识别文本非空；
    --keyword 仅在显式给出时启用（默认 None = 不启用）。
    """
    if status_code != 200:
        return False, f"HTTP {status_code} != 200"
    if code is not None and code != 0:
        return False, f"envelope code={code} != 0"
    if text is None or not text.strip():
        return False, "识别文本为空"
    if keyword and keyword not in text:
        return False, f"未包含关键字 {keyword!r}"
    return True, ""


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
    parser.add_argument(
        "--keyword",
        default=None,
        help="可选：要求识别文本包含指定关键字（默认不启用，契约口径为 code==0 且文本非空）",
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
        # multipart 上传（对齐项目 /api/v1/asr 契约: audio 文件字段, language 走默认 en）
        resp = httpx.post(
            args.url,
            files={"audio": (os.path.basename(args.audio), audio_bytes, "audio/wav")},
            timeout=TIMEOUT,
        )
        elapsed = time.perf_counter() - start
    except httpx.TimeoutException:
        print(f"[ASR] 请求超时（>{TIMEOUT}s）")
        return 1
    except httpx.RequestError as exc:
        print(f"[ASR] 连接失败: {exc}")
        return 1

    text = extract_text(resp)
    code = envelope_code(resp)
    ok, reason = verdict(resp.status_code, code, text, args.keyword)

    print(f"[ASR] HTTP 状态码: {resp.status_code}")
    if code is not None:
        print(f"[ASR] envelope code: {code}（0=成功）")
    print(f"[ASR] 总耗时: {elapsed:.3f}s")
    print(f"[ASR] 返回文本: {text[:200]}")
    print(f"[ASR] 判定: {reason if reason else '契约校验通过'}")

    print(f"[ASR] 结果: {'通过' if ok else '不通过'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
