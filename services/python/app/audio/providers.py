"""内置引擎的一次性登记入口（import 即注册）。

:mod:`app.audio.registry` 只管「有哪些引擎、怎么选」，不 import 任何具体引擎
（否则与 ``base`` → ``registry`` → 引擎 → ``base`` 形成导入环）。本模块是那层
「把内置引擎模块导进来」的胶水：

- 每个引擎模块在模块级 ``register(ProviderSpec(...))``，**声明式、就近可读**；
- 单次执行（``_done`` + 锁）；某个引擎模块导入失败（可选依赖缺失等）只告警跳过，
  不影响其它引擎——这正是「可插拔」要的行为：少一个引擎，服务照常起。

新增一个引擎的完整步骤（三步，编排层零改动）：
1. 写 ``app/audio/xxx.py``，实现 ``ASRClient`` / ``TTSClient`` 子类；
2. 在同模块末尾 ``register(ProviderSpec(name=..., kind=..., factory=...))``；
3. 把模块名加进下边 ``_MODULES``。
"""

from __future__ import annotations

import importlib
import logging
import threading

logger = logging.getLogger("vocalverse.audio.providers")

#: 内置引擎模块（导入副作用 = 注册 ProviderSpec）
_MODULES: tuple[str, ...] = (
    "app.audio.stubs",
    "app.audio.asr",
    "app.audio.asr_sherpa",
    "app.audio.tts",
    "app.audio.tts_local",
    "app.audio.tts_omnivoice",
)

_lock = threading.Lock()
_done = False


def ensure_registered() -> None:
    """导入全部内置引擎模块（幂等、线程安全）。"""
    global _done
    if _done:
        return
    with _lock:
        if _done:
            return
        for name in _MODULES:
            try:
                importlib.import_module(name)
            except Exception as exc:  # noqa: BLE001 — 可选引擎缺失不应拖垮全站
                logger.warning("引擎模块导入失败（跳过）：%s（%s）", name, exc)
        _done = True


def reset_for_tests() -> None:
    """测试专用：允许重新导入（注册表本身不清理，便于打桩覆盖同名 provider）。"""
    global _done
    _done = False


__all__ = ["ensure_registered", "reset_for_tests"]
