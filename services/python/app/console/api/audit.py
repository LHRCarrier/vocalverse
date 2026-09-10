"""trace 内容读取审计（best-effort）。

**为什么不是 ``admin_audit_logs``**：该表归 **Java 写方**（docs/50 §5.1 写方矩阵），
Python 侧写它 = 破坏单写方矩阵（``scripts/check_single_writer.py`` 会红）。
但"看别人的 prompt 是留痕行为"（docs/50 §7.5）又是硬要求，所以本模块做两件事：

1. 往 ``llm_traces.attrs.content_reads`` 追加一条环形记录（最多 10 条，含 admin id/时间/jti），
   **与 trace 同生命周期**，控制台详情页可直接看到"谁在什么时候看过这份内容"；
2. 打一条 WARNING 日志（含 admin id + trace_id + request_id），交给既有日志采集面留存。

**已知缺口（如实登记）**：这不是合规意义上的不可篡改审计（attrs 可被后续写入覆盖）。
真正的 ``admin_audit_logs(action='ops.trace.content.read')`` 落库需 Java 侧提供内部接口，
属跨服务改造，本 PR 不做。"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger("vocalverse.console.audit")

#: attrs.content_reads 环形长度（控体积；trace 的 attrs 是 jsonb，不是审计真源）
MAX_READ_RECORDS = 10

ACTION = "ops.trace.content.read"


def record_content_read(db, trace, admin) -> dict[str, Any]:
    """记录一次内容读取（best-effort：任何异常都不阻断读取本身）。"""
    entry = {
        "action": ACTION,
        "admin_id": getattr(admin, "admin_id", None),
        "admin_username": getattr(admin, "username", None),
        "at": datetime.now(UTC).isoformat(),
    }
    try:
        from app.core.trace import get_request_id

        rid = get_request_id()
        if rid and rid != "-":
            entry["request_id"] = rid
    except Exception:  # noqa: BLE001
        pass

    try:
        attrs = dict(trace.attrs or {})
        reads = list(attrs.get("content_reads") or [])
        reads.append(entry)
        attrs["content_reads"] = reads[-MAX_READ_RECORDS:]
        trace.attrs = attrs  # 重新赋值：JSON 列原地修改不会被 SQLAlchemy 检测到
    except Exception:  # noqa: BLE001 - 审计失败不得阻断读取
        logger.warning("trace 内容读取审计写入 attrs 失败", exc_info=True)

    logger.warning(
        "trace 内容读取审计 action=%s trace_id=%s admin_id=%s admin=%s",
        ACTION,
        getattr(trace, "trace_id", "?"),
        entry["admin_id"],
        entry["admin_username"] or "-",
    )
    return entry


__all__ = ["ACTION", "MAX_READ_RECORDS", "record_content_read"]
