"""ffmpeg 工具层（性能拷问 va-01 / py-09：统一二进制探测 + 时长探测 + 转码护栏）。

从 asr/ise 各自内联的实现收拢为单一真源：
- ``ffmpeg_bin``：env FFMPEG_BIN → PATH → imageio-ffmpeg 兜底（免管理员）；
- ``probe_duration_seconds``：ffprobe 优先（JSON 输出），回退 ffmpeg -i stderr 解析
  （「Duration: HH:MM:SS.xx」），失败/超时一律 None —— 绝不抛错、绝不阻塞路径；
- ``run_ffmpeg``：async 子进程 + 超时 kill + 非零退出上抛（asr/ise 共用同一护栏）。
"""

from __future__ import annotations

import asyncio
import re

_DURATION_RE = re.compile(r"Duration:\s*(\d{2}):(\d{2}):(\d{2})\.(\d{2})")


def ffmpeg_bin() -> str:
    """ffmpeg 路径：① env FFMPEG_BIN → ② PATH 中 ffmpeg → ③ imageio-ffmpeg 自带二进制
    （pip/uv 附带、免管理员，README 登记）→ ④ 兜底 "ffmpeg"（让 subprocess 报可读错误）。"""
    import os
    import shutil

    if os.environ.get("FFMPEG_BIN"):
        return os.environ["FFMPEG_BIN"]
    if shutil.which("ffmpeg"):
        return "ffmpeg"
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def ffprobe_bin() -> str | None:
    """ffprobe 路径（env FFPROBE_BIN → PATH）；无则 None（回退 ffmpeg -i 解析）。"""
    import os
    import shutil

    if os.environ.get("FFPROBE_BIN"):
        return os.environ["FFPROBE_BIN"]
    return shutil.which("ffprobe")


def parse_duration_from_stderr(text: str) -> float | None:
    """从 ffmpeg -i 的 stderr 提取时长（秒）；未匹配 → None（纯函数，可单测）。"""
    m = _DURATION_RE.search(text or "")
    if not m:
        return None
    h, mnt, s, cs = (int(g) for g in m.groups())
    return float(h * 3600 + mnt * 60 + s) + float(cs) / 100.0


async def run_ffmpeg(args: list[str], timeout_s: float = 15.0) -> bytes:
    """执行 ffmpeg（args 不含二进制），返回 stderr 字节；超时 kill + 非零 exit 上抛。

    ⚠️ 2026-09-07 部署坑（Windows + uvicorn --reload）：``asyncio.create_subprocess_exec``
    在 SelectorEventLoop 上抛 NotImplementedError（uvicorn loops/asyncio.py：win32 且
    use_subprocess=True（--reload）时选 Selector；Selector 不支持子进程）+ 事件循环会被
    平台策略钉死（模块 import 时 loop 已创建，运行时改策略无效）。
    → 实现改 ``asyncio.to_thread(subprocess.run(..., timeout=...))``：任何 loop 类型可用
    （to_thread 基于线程池，不依赖 loop 子进程传输），仍满足 P0-2（重活不进事件循环，超时
    由 subprocess.run 自动 kill+wait）。语义与旧实现一致：超时/非零 → RuntimeError。
    """
    import subprocess

    def _run_sync() -> bytes:
        try:
            proc = subprocess.run(
                [ffmpeg_bin(), *args],
                capture_output=True,
                timeout=timeout_s,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"ffmpeg 超时（{timeout_s}s）: {' '.join(args[:2])}") from exc
        except FileNotFoundError as exc:
            raise RuntimeError(f"ffmpeg 未找到: {ffmpeg_bin()}") from exc
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg 失败（exit={proc.returncode}）: {proc.stderr or b''}")
        return proc.stderr or b""

    return await asyncio.to_thread(_run_sync)


async def probe_duration_seconds(path: str, timeout_s: float = 5.0) -> float | None:
    """音频时长探测（秒，va-02 依赖：热度上限按端点生效）。绝不抛错 → None。

    策略：ffprobe -show_entries format=duration -of json（快且准）；缺 ffprobe 时
    回退 ``ffmpeg -i`` 的 stderr Duration 解析（不解码，仅头探测）。
    实现同样走 ``asyncio.to_thread(subprocess.run)``（run_ffmpeg 同因：
    SelectorEventLoop 下 create_subprocess_exec 不可用，见 run_ffmpeg 注释）。
    """
    import json as _json
    import subprocess

    def _ffprobe() -> float | None:
        probe = ffprobe_bin()
        if probe is None:
            return None
        try:
            proc = subprocess.run(
                [probe, "-v", "error", "-show_entries", "format=duration", "-of", "json", path],
                capture_output=True,
                timeout=timeout_s,
                check=False,
            )
            if proc.returncode == 0 and proc.stdout:
                data = _json.loads(proc.stdout.decode("utf-8", "replace") or "{}")
                dur = float(data.get("format", {}).get("duration") or 0.0)
                return dur if dur > 0 else None
        except Exception:
            pass
        return None

    def _ffmpeg_fallback() -> float | None:
        try:
            proc = subprocess.run(
                [ffmpeg_bin(), "-i", path],
                capture_output=True,
                timeout=timeout_s,
                check=False,
            )
            # ffmpeg -i 无输出参数时以 exit 1 结束，但头信息仍完整打在 stderr —— 忽略退出码
            return parse_duration_from_stderr((proc.stderr or b"").decode("utf-8", "replace"))
        except Exception:
            return None

    dur = await asyncio.to_thread(_ffprobe)
    if dur is not None:
        return dur
    return await asyncio.to_thread(_ffmpeg_fallback)
