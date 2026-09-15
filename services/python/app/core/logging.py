"""日志配置（docs/47 §7 · 修复 docs/48 B4：`vocalverse` logger 无 handler → 日志零输出）。

现状问题：全仓没有任何 `basicConfig`/`dictConfig`，uvicorn 只配置 `uvicorn.*` 三个 logger，
于是 `logging.getLogger("vocalverse").info(...)` 既不进 handler、也不带格式 ——
设计稿里所有 `logger.info` 都是纸面设计（实测 `root handlers=[]`）。

本模块在 `app.main` 导入时调用一次 `configure_logging()`：
- 给 `vocalverse` 根 logger 挂 console handler + `%(request_id)s` 格式；
- `app.*` 子 logger 用 propagate=True 冒泡到 `vocalverse`（子 logger 自身不挂 filter，
  因为 filter 只在记录来源 logger 上执行，冒泡不触发祖先 filter —— 这正是
  「只给 vocalverse 挂 RequestIdLogFilter」时子 logger 拿不到 request_id 的原因）；
- 级别取 `APP_LOG_LEVEL`（此前是死配置，无消费者）；
- testing 档默认 WARNING，避免 CI 噪声。
"""

from __future__ import annotations

import logging
import logging.config

from app.core.trace import RequestIdLogFilter

_FORMAT = "%(asctime)s %(levelname)-5s [%(request_id)s] %(name)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def configure_logging(level: str | None = None, *, testing: bool | None = None) -> None:
    """幂等配置日志（重复调用无副作用：dictConfig 以 disable_existing_loggers=False 重建）。"""
    from app.core.config import get_settings

    settings = get_settings()
    resolved = (level or settings.log_level or "INFO").upper()
    if testing is None:
        testing = settings.testing
    if testing and level is None:
        resolved = "WARNING"

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "filters": {
                "request_id": {"()": RequestIdLogFilter},
            },
            "formatters": {
                "standard": {"format": _FORMAT, "datefmt": _DATE_FORMAT},
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "standard",
                    "filters": ["request_id"],
                    "stream": "ext://sys.stderr",
                },
            },
            "loggers": {
                # 应用根 logger：所有 app.* / vocalverse.* 都冒泡到这里
                "vocalverse": {
                    "handlers": ["console"],
                    "level": resolved,
                    "propagate": False,
                },
                "app": {
                    "handlers": ["console"],
                    "level": resolved,
                    "propagate": False,
                },
            },
        }
    )


def get_logger(name: str) -> logging.Logger:
    """取应用 logger（统一命名空间 `vocalverse.<module>`，便于按前缀调级别）。"""
    return logging.getLogger(name if name.startswith("vocalverse") else f"vocalverse.{name}")
