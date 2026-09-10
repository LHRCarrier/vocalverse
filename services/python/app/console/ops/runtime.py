"""采集运行时单例（lifespan 启停；路由层读取自监控计数）。

单例而不是 ``app.state``：``/ops/overview`` 要在**不持有 request.app 引用**的
辅助函数里读 collector 状态，模块级单例是仓库既有口径（``core/redis_client.py``、
``audio/base.py`` 的 LLM 客户端缓存同款）。
"""

from __future__ import annotations

from app.console.ops.collector import OpsCollector

_collector: OpsCollector | None = None


def get_collector() -> OpsCollector | None:
    return _collector


def set_collector(collector: OpsCollector | None) -> None:
    global _collector
    _collector = collector


async def start_collector() -> OpsCollector | None:
    """lifespan 启动：功能位关闭时返回 None（不启动任务、不播种规则）。"""
    global _collector
    from app.console.ops.collector import telemetry_enabled

    if not telemetry_enabled():
        return None
    _collector = OpsCollector()
    await _collector.start()
    return _collector


async def stop_collector() -> None:
    global _collector
    if _collector is not None:
        await _collector.stop()
        _collector = None


__all__ = ["get_collector", "set_collector", "start_collector", "stop_collector"]
