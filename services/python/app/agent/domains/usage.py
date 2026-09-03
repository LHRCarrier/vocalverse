"""LLM 用量记账（docs/26 §10.3②：对照 ai4u usage_log，表格已在迁移 0004）。

- 收集点：turn（回合流，含 META 补偿）、summary（滚动摘要）、conclude（收尾总结）；
- usage 形如 {"prompt_tokens": n, "completion_tokens": n, "model": "..."}（llm 客户端给）；
- 单条落库失败仅告警（记账不阻塞回合）。
"""

from __future__ import annotations

import json
import logging

from app.models import UsageLog

logger = logging.getLogger("vocalverse")


def log_usage(source: str, usage: dict | None, meta: dict | None = None) -> None:
    """写一条 usage_log（幂等无害；失败静默）。"""
    try:
        from app.db import get_session_factory

        if not usage:
            return
        db = get_session_factory()()
        try:
            db.add(
                UsageLog(
                    source=source,
                    model=str(usage.get("model") or ""),
                    prompt_tokens=int(usage.get("prompt_tokens") or 0),
                    completion_tokens=int(usage.get("completion_tokens") or 0),
                    meta=json.dumps(meta or {}, ensure_ascii=False),
                )
            )
            db.commit()
        finally:
            db.close()
    except Exception as exc:  # 记账失败不阻塞回合
        logger.warning("usage log skipped source=%s: %s", source, exc)


__all__ = ["log_usage"]
