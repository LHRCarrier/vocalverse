"""酒馆状态服务：事实/任务/线索/实体/事件/消息的**唯一写入口**（迁移自 ai4u TrpgStateService）。

纪律：
- 所有写路径收敛于此：LLM 提取（``upsert_facts``）/ 规则直写（``apply_dice_delta``）/
  DM 场景切换（``set_scene``）/ 用户编辑删除（``edit_fact`` / ``delete_fact``）；
- 读路径墓碑过滤统一：``user_deleted_at IS NULL``（P2-35 防提取复活）；
- 实体注册（P2-42，2026-09-22 修订）：LLM 发现未知实体 → **直接 active**（pending=False，
  docs/57 §3.1）；``pending`` 仅作为未来确认流/立绘任务的预留标志（当前无生产者）；
- 骰子直写（P2-41）：任一 delta 落表失败抛错——调用方转错误文本，杜绝「文本成功但 HP 未落表」；
- 叙事摘要（P2-45）：由结构化状态模板渲染（非对话压缩），永远与事实表一致。

多用户口径：campaign 归属用户，所有入口先经 :func:`get_campaign_owned` 校验（越权按不存在）。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select

from app.db import get_session_factory
from app.models.base import TrpgFactKinds, TrpgMessageKinds, TrpgTaskStatuses
from app.models.trpg import (
    TrpgCampaign,
    TrpgClue,
    TrpgEntity,
    TrpgEvent,
    TrpgFact,
    TrpgMessage,
    TrpgTask,
)
from app.trpg import progress as progress_rules
from app.trpg.constants import DOMAIN_ENTITY_KIND, STATE_DOMAINS
from app.trpg.dice import DiceResult, delta_value
from app.trpg.encounter import format_state_change, state_key_label
from app.trpg.facts import Adjudication, FactOp, FactRowLike, adjudicate_upsert, parse_key
from app.trpg.snapshot import (
    SnapshotClue,
    SnapshotFact,
    SnapshotInput,
    SnapshotTask,
    build_state_snapshot,
)

logger = logging.getLogger("vocalverse")

_VALID_TASK_STATUSES = (
    TrpgTaskStatuses.ACTIVE,
    TrpgTaskStatuses.DONE,
    TrpgTaskStatuses.FAILED,
)


# ---------------------------------------------------------------------------
# Campaign（剧本实例 CRUD；用户私有）
# ---------------------------------------------------------------------------
def create_campaign(user_id: int, name: str) -> TrpgCampaign:
    db = get_session_factory()()
    try:
        row = TrpgCampaign(user_id=user_id, name=(name or "").strip()[:60] or "未命名剧本")
        db.add(row)
        db.commit()
        db.refresh(row)
        return row
    finally:
        db.close()


def list_campaigns(user_id: int) -> list[TrpgCampaign]:
    db = get_session_factory()()
    try:
        return list(
            db.execute(
                select(TrpgCampaign)
                .where(TrpgCampaign.user_id == user_id)
                .order_by(TrpgCampaign.last_active_at.desc(), TrpgCampaign.id.desc())
            )
            .scalars()
            .all()
        )
    finally:
        db.close()


def get_campaign_owned(campaign_id: int, user_id: int) -> TrpgCampaign | None:
    db = get_session_factory()()
    try:
        return db.execute(
            select(TrpgCampaign).where(
                TrpgCampaign.id == campaign_id, TrpgCampaign.user_id == user_id
            )
        ).scalar_one_or_none()
    finally:
        db.close()


def touch_campaign(campaign_id: int) -> None:
    db = get_session_factory()()
    try:
        row = db.get(TrpgCampaign, campaign_id)
        if row is not None:
            row.last_active_at = datetime.now(UTC)
            db.commit()
    finally:
        db.close()


def has_messages(campaign_id: int) -> bool:
    db = get_session_factory()()
    try:
        return (
            db.execute(
                select(TrpgMessage.id).where(TrpgMessage.campaign_id == campaign_id).limit(1)
            ).first()
            is not None
        )
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 实体注册（P2-42）
# ---------------------------------------------------------------------------
def ensure_entity(campaign_id: int, kind: str, name: str, pending: bool = False) -> int:
    """实体注册：已存在刷新 last_mentioned_at；不存在则创建（缺省 active，pending=False）。"""
    db = get_session_factory()()
    try:
        row = db.execute(
            select(TrpgEntity).where(
                TrpgEntity.campaign_id == campaign_id,
                TrpgEntity.kind == kind,
                TrpgEntity.name == name,
            )
        ).scalar_one_or_none()
        now = datetime.now(UTC)
        if row is not None:
            row.last_mentioned_at = now
            db.commit()
            return row.id
        created = TrpgEntity(
            campaign_id=campaign_id, kind=kind, name=name, pending=pending, last_mentioned_at=now
        )
        db.add(created)
        db.commit()
        db.refresh(created)
        logger.info("酒馆实体注册：%s/%s（pending=%s）", kind, name, pending)
        return created.id
    finally:
        db.close()


def find_entity(campaign_id: int, name: str, kinds: tuple[str, ...] = ("npc", "pc")) -> dict | None:
    """按名字查实体（限 kinds；重名取最近提及）→ :func:`_entity_dict` 形状 / None。

    读实体场景用（如 show_portrait 的立绘展示校验）；写路径一律走 :func:`ensure_entity`。
    """
    db = get_session_factory()()
    try:
        row = (
            db.execute(
                select(TrpgEntity)
                .where(
                    TrpgEntity.campaign_id == campaign_id,
                    TrpgEntity.name == name,
                    TrpgEntity.kind.in_(kinds),
                )
                .order_by(TrpgEntity.last_mentioned_at.desc())
            )
            .scalars()
            .first()
        )
        return _entity_dict(row) if row is not None else None
    finally:
        db.close()


def cleanup_idle_entities(campaign_id: int, idle_ms: float) -> int:
    """待确认实体懒清理（P2-42 预留路径）：超窗未提及 → cleared（防积压）。

    2026-09-22 起（docs/57 §3.1）不再有正常的 ``pending=True`` 生产者（发现即 active），
    本函数保留给未来的「未知实体确认流」；当前调用即空转（返回 0），无副作用。
    """
    db = get_session_factory()()
    try:
        cutoff = datetime.now(UTC) - timedelta(milliseconds=idle_ms)
        rows = (
            db.execute(
                select(TrpgEntity).where(
                    TrpgEntity.campaign_id == campaign_id,
                    TrpgEntity.pending.is_(True),
                    TrpgEntity.last_mentioned_at < cutoff,
                    TrpgEntity.status == "active",
                )
            )
            .scalars()
            .all()
        )
        for row in rows:
            row.status = "cleared"
            row.pending = False
        if rows:
            db.commit()
            logger.info("酒馆待确认实体清理 %s 个（campaign=%s）", len(rows), campaign_id)
        return len(rows)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 事实写路径（P2-24/26/27/35 裁决）
# ---------------------------------------------------------------------------
def _fact_dict(row: TrpgFact) -> dict:
    return {
        "id": row.id,
        "key": row.fact_key,
        "value": row.value,
        "kind": row.kind,
        "modality": row.modality,
        "speaker": row.speaker,
        "importance": row.importance,
        "user_touched_at": row.user_touched_at,
        "user_deleted_at": row.user_deleted_at,
        "version": row.version,
        "source_message_id": row.source_message_id,
    }


def list_facts(campaign_id: int, include_deleted: bool = False) -> list[dict]:
    db = get_session_factory()()
    try:
        stmt = select(TrpgFact).where(TrpgFact.campaign_id == campaign_id)
        if not include_deleted:
            stmt = stmt.where(TrpgFact.user_deleted_at.is_(None))
        rows = (
            db.execute(stmt.order_by(TrpgFact.importance.desc(), TrpgFact.id.asc())).scalars().all()
        )
        return [_fact_dict(r) for r in rows]
    finally:
        db.close()


def upsert_facts(
    campaign_id: int, ops: list[FactOp], source_message_id: int | None = None
) -> list[dict]:
    """事实 upsert（LLM 提取 + 系统直写共用）：逐条裁决、逐条隔离失败（红线 8）。

    返回逐条结果 ``[{op, action, reason}]``，供调用方记录/观测。
    """
    if not ops:
        return []
    db = get_session_factory()()
    results: list[dict] = []
    try:
        rows = (
            db.execute(select(TrpgFact).where(TrpgFact.campaign_id == campaign_id)).scalars().all()
        )
        entities = set(
            db.execute(select(TrpgEntity.name).where(TrpgEntity.campaign_id == campaign_id))
            .scalars()
            .all()
        )
        tombstones = {r.fact_key for r in rows if r.user_deleted_at is not None}
        existing = [
            FactRowLike(
                id=r.id,
                key=r.fact_key,
                value=r.value,
                kind=r.kind,
                modality=r.modality,
                speaker=r.speaker,
                importance=r.importance,
                user_touched_at=r.user_touched_at,
                user_deleted_at=r.user_deleted_at,
                version=r.version,
            )
            for r in rows
            if r.user_deleted_at is None
        ]
        by_key = {r.fact_key: r for r in rows if r.user_deleted_at is None}

        for op in ops:
            try:
                decision: Adjudication = adjudicate_upsert(op, existing, entities, tombstones)
                if decision.action == "reject":
                    results.append({"op": op, "action": "reject", "reason": decision.reason})
                    continue
                parsed = parse_key(op.key)
                if decision.action == "update":
                    row = by_key.get(op.key)
                    if row is None:
                        results.append({"op": op, "action": "reject", "reason": "db-error"})
                        continue
                    row.value = op.value
                    if op.modality:
                        row.modality = op.modality
                    if op.speaker:
                        row.speaker = op.speaker
                    if op.importance is not None:
                        row.importance = op.importance
                    if source_message_id is not None:
                        row.source_message_id = source_message_id
                    row.version = (row.version or 1) + 1
                    results.append({"op": op, "action": "update"})
                else:
                    if decision.register_entity and parsed is not None and parsed.entity:
                        kind = DOMAIN_ENTITY_KIND.get(parsed.domain, "npc")
                        _register_entity_in_db(db, campaign_id, kind, parsed.entity)
                        entities.add(parsed.entity)
                    kind = (
                        TrpgFactKinds.STATE
                        if parsed is not None and parsed.domain in STATE_DOMAINS
                        else TrpgFactKinds.FACT
                    )
                    db.add(
                        TrpgFact(
                            campaign_id=campaign_id,
                            kind=kind,
                            fact_key=op.key,
                            value=op.value,
                            modality=op.modality or "fact",
                            speaker=op.speaker,
                            importance=op.importance if op.importance is not None else 0.5,
                            source_message_id=source_message_id,
                        )
                    )
                    results.append({"op": op, "action": "create"})
                _sync_task_clue_from_op(db, campaign_id, op)
                db.commit()
            except Exception as exc:  # noqa: BLE001 - 逐条隔离：单条失败不拖垮整批
                db.rollback()
                logger.warning("酒馆事实 upsert 失败（%s）：%s", op.key, exc)
                results.append({"op": op, "action": "reject", "reason": "db-error"})
        return results
    finally:
        db.close()


def _register_entity_in_db(db, campaign_id: int, kind: str, name: str) -> None:
    row = db.execute(
        select(TrpgEntity).where(
            TrpgEntity.campaign_id == campaign_id,
            TrpgEntity.kind == kind,
            TrpgEntity.name == name,
        )
    ).scalar_one_or_none()
    now = datetime.now(UTC)
    if row is not None:
        row.last_mentioned_at = now
        return
    db.add(
        TrpgEntity(
            campaign_id=campaign_id, kind=kind, name=name, pending=False, last_mentioned_at=now
        )
    )


def _sync_task_clue_from_op(db, campaign_id: int, op: FactOp) -> None:
    """quest./clue. 事实写 → 同步任务/线索行（快照与面板的结构化消费源）。"""
    parsed = parse_key(op.key)
    if parsed is None or parsed.entity is None:
        return
    now = datetime.now(UTC)
    if parsed.domain == "quest":
        row = db.execute(
            select(TrpgTask).where(
                TrpgTask.campaign_id == campaign_id, TrpgTask.title == parsed.entity
            )
        ).scalar_one_or_none()
        status = op.value if op.value in _VALID_TASK_STATUSES else None
        if row is not None:
            if status:
                row.status = status
            row.last_mentioned_at = now
        else:
            db.add(
                TrpgTask(
                    campaign_id=campaign_id,
                    title=parsed.entity,
                    status=status or TrpgTaskStatuses.ACTIVE,
                    last_mentioned_at=now,
                )
            )
    elif parsed.domain == "clue":
        row = db.execute(
            select(TrpgClue).where(
                TrpgClue.campaign_id == campaign_id, TrpgClue.title == parsed.entity
            )
        ).scalar_one_or_none()
        found = True if op.value == "found" else (False if op.value == "lost" else None)
        if row is not None:
            if found is not None:
                row.found = found
            row.last_mentioned_at = now
        else:
            db.add(
                TrpgClue(
                    campaign_id=campaign_id,
                    title=parsed.entity,
                    content=op.value,
                    found=found if found is not None else True,
                    last_mentioned_at=now,
                )
            )


# ---------------------------------------------------------------------------
# 规则直写（P2-41/44）
# ---------------------------------------------------------------------------
def apply_dice_delta(campaign_id: int, dice: DiceResult) -> str:
    """骰子结果落表：逐 delta 增量写 State 行 + 落一条事件日志；失败抛错（调用方转错误文本）。

    摘要用**展示名**（``主角 HP 7（-5）``，docs/57 §3.1：判定卡不再暴露内部键）。
    """
    db = get_session_factory()()
    try:
        applied: list[str] = []
        missing: list[str] = []
        for d in dice.deltas:
            row = db.execute(
                select(TrpgFact).where(
                    TrpgFact.campaign_id == campaign_id,
                    TrpgFact.fact_key == d.key,
                    TrpgFact.user_deleted_at.is_(None),
                )
            ).scalar_one_or_none()
            next_value = delta_value(row.value if row is not None else None, d.delta)
            if next_value is None:
                missing.append(d.key)
                continue
            if row is not None:
                row.value = next_value
                row.version = (row.version or 1) + 1
            else:
                db.add(
                    TrpgFact(
                        campaign_id=campaign_id,
                        kind=TrpgFactKinds.STATE,
                        fact_key=d.key,
                        value=next_value,
                        modality="fact",
                    )
                )
            applied.append(format_state_change(d.key, next_value, d.delta))

        round_no = (
            int(
                db.execute(
                    select(func.count())
                    .select_from(TrpgEvent)
                    .where(TrpgEvent.campaign_id == campaign_id)
                ).scalar_one()
            )
            + 1
        )
        missing_note = (
            f"（未建行跳过：{'，'.join(state_key_label(key) for key in missing)}）"
            if missing
            else ""
        )
        vs_note = ""
        if dice.vs is not None:
            outcome = "成功" if dice.outcome == "success" else "失败"
            vs_note = f"（骰 {dice.total} 对抗 {dice.vs} {outcome}）"
        summary = f"第 {round_no} 回合：{'；'.join(applied) or '无状态变化'}{missing_note}{vs_note}"
        db.add(TrpgEvent(campaign_id=campaign_id, round=round_no, summary=summary))
        db.commit()
        return summary
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def count_events(campaign_id: int) -> int:
    db = get_session_factory()()
    try:
        return int(
            db.execute(
                select(func.count())
                .select_from(TrpgEvent)
                .where(TrpgEvent.campaign_id == campaign_id)
            ).scalar_one()
        )
    finally:
        db.close()


def log_event(campaign_id: int, summary: str) -> None:
    db = get_session_factory()()
    try:
        round_no = (
            int(
                db.execute(
                    select(func.count())
                    .select_from(TrpgEvent)
                    .where(TrpgEvent.campaign_id == campaign_id)
                ).scalar_one()
            )
            + 1
        )
        db.add(TrpgEvent(campaign_id=campaign_id, round=round_no, summary=summary[:300]))
        db.commit()
    finally:
        db.close()


def list_events(campaign_id: int, limit: int = 30) -> list[dict]:
    db = get_session_factory()()
    try:
        rows = (
            db.execute(
                select(TrpgEvent)
                .where(TrpgEvent.campaign_id == campaign_id)
                .order_by(TrpgEvent.round.desc())
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return [
            {"id": r.id, "round": r.round, "summary": r.summary, "created_at": r.created_at}
            for r in rows
        ]
    finally:
        db.close()


def get_scene(campaign_id: int) -> str | None:
    db = get_session_factory()()
    try:
        return db.execute(
            select(TrpgFact.value).where(
                TrpgFact.campaign_id == campaign_id,
                TrpgFact.fact_key == "scene.current",
                TrpgFact.user_deleted_at.is_(None),
            )
        ).scalar_one_or_none()
    finally:
        db.close()


def set_scene(campaign_id: int, scene: str) -> None:
    """场景切换（P2-43：DM 显式动作，用户权威——覆盖旧值与墓碑，不走 LLM 裁决）。"""
    db = get_session_factory()()
    try:
        row = db.execute(
            select(TrpgFact).where(
                TrpgFact.campaign_id == campaign_id, TrpgFact.fact_key == "scene.current"
            )
        ).scalar_one_or_none()
        if row is not None:
            row.value = scene
            row.user_deleted_at = None
            row.version = (row.version or 1) + 1
        else:
            db.add(
                TrpgFact(
                    campaign_id=campaign_id,
                    kind=TrpgFactKinds.STATE,
                    fact_key="scene.current",
                    value=scene,
                    modality="fact",
                )
            )
        db.commit()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 闭环适配（docs/56 §B：quest 进度 / 实体在场 / 道具 / 遭遇 / 立绘 / 收尾）
#
# 纪律：本段只做「读事实 → 形状转换 → 起事务落库」，不做任何规则算术（算术/判定在
# progress.py / encounter.py / items.py 纯模块）；写入一律经 upsert_facts(writer="system")。
# ---------------------------------------------------------------------------
_QUEST_PROPS: tuple[str, ...] = ("progress", "kind", "stage", "status")
_ITEM_PROPS: tuple[str, ...] = ("qty", "owner", "effect", "consumable")


def get_fact_value(campaign_id: int, key: str) -> str | None:
    """按 key 读单条事实值（墓碑过滤与读路径一致）。"""
    db = get_session_factory()()
    try:
        return db.execute(
            select(TrpgFact.value).where(
                TrpgFact.campaign_id == campaign_id,
                TrpgFact.fact_key == key,
                TrpgFact.user_deleted_at.is_(None),
            )
        ).scalar_one_or_none()
    finally:
        db.close()


def _fact_values_by_prefix(campaign_id: int, prefix: str) -> dict[str, str]:
    db = get_session_factory()()
    try:
        rows = db.execute(
            select(TrpgFact.fact_key, TrpgFact.value).where(
                TrpgFact.campaign_id == campaign_id,
                TrpgFact.fact_key.like(f"{prefix}%"),
                TrpgFact.user_deleted_at.is_(None),
            )
        ).all()
        return {key: value for key, value in rows}
    finally:
        db.close()


def _upsert_system_values(campaign_id: int, values: dict[str, str | None]) -> None:
    ops = [
        FactOp(op="create", key=key, value=str(value), writer="system")
        for key, value in values.items()
        if value is not None
    ]
    if ops:
        upsert_facts(campaign_id, ops)


def portrait_view(media_id: str | None) -> dict | None:
    """立绘视图（``{media_id, url}``，未挂图 → None）；URL 口径 docs/56 §4。"""
    if not media_id:
        return None
    from app.core.config import get_settings

    return {"media_id": media_id, "url": f"{get_settings().media_url_prefix}{media_id}"}


def get_quest_state(campaign_id: int, quest: str) -> dict:
    """读任务闭环字段（progress/kind/stage/status；缺省 None，由工具补默认值）。"""
    values = _fact_values_by_prefix(campaign_id, f"quest.{quest}.")
    return {prop: values.get(f"quest.{quest}.{prop}") for prop in _QUEST_PROPS}


def set_quest_facts(
    campaign_id: int,
    quest: str,
    *,
    progress: str | None = None,
    kind: str | None = None,
    stage: str | None = None,
    status: str | None = None,
) -> None:
    """写任务闭环事实（系统写者；status 会经 ``_sync_task_clue_from_op`` 同步任务行）。"""
    _upsert_system_values(
        campaign_id,
        {
            f"quest.{quest}.progress": progress,
            f"quest.{quest}.kind": kind,
            f"quest.{quest}.stage": stage,
            f"quest.{quest}.status": status,
        },
    )


def get_item_state(campaign_id: int, name: str) -> dict:
    """读道具条目（qty/owner/effect/consumable；无事实即 None 值）。"""
    values = _fact_values_by_prefix(campaign_id, f"item.{name}.")
    return {prop: values.get(f"item.{name}.{prop}") for prop in _ITEM_PROPS}


def set_item_facts(
    campaign_id: int,
    name: str,
    *,
    qty: int | str | None = None,
    owner: str | None = None,
    effect: str | None = None,
    consumable: bool | None = None,
) -> None:
    """写道具事实（数量/持有者/效果/是否消耗；None 字段不动）。"""
    _upsert_system_values(
        campaign_id,
        {
            f"item.{name}.qty": None if qty is None else str(int(qty)),
            f"item.{name}.owner": owner,
            f"item.{name}.effect": effect,
            f"item.{name}.consumable": (
                None if consumable is None else ("true" if consumable else "false")
            ),
        },
    )


def default_item_owner(campaign_id: int) -> str | None:
    """道具默认持有者：最早登记的 PC 实体；无 PC 实体时取唯一的 ``pc.*`` 事实主体。

    （grant_item 缺省 owner 来源；``pc.名`` 与 item.owner 契约一致。）
    """
    db = get_session_factory()()
    try:
        row = (
            db.execute(
                select(TrpgEntity)
                .where(TrpgEntity.campaign_id == campaign_id, TrpgEntity.kind == "pc")
                .order_by(TrpgEntity.id.asc())
                .limit(1)
            )
            .scalars()
            .first()
        )
        if row is not None:
            return f"pc.{row.name}"
        keys = (
            db.execute(
                select(TrpgFact.fact_key).where(
                    TrpgFact.campaign_id == campaign_id,
                    TrpgFact.fact_key.like("pc.%"),
                    TrpgFact.user_deleted_at.is_(None),
                )
            )
            .scalars()
            .all()
        )
    finally:
        db.close()
    names: set[str] = set()
    for key in keys:
        parts = str(key).split(".")
        if len(parts) == 3 and parts[0] == "pc" and parts[1]:
            names.add(parts[1])
    if len(names) == 1:
        return f"pc.{names.pop()}"
    return None


def get_encounter(campaign_id: int, encounter_id: str = "main") -> dict:
    """读遭遇事实（status/order/turn/round；order 在此解码为列表，工具不经手 JSON）。"""
    from app.trpg.encounter import decode_order

    prefix = f"encounter.{encounter_id}."
    values = _fact_values_by_prefix(campaign_id, prefix)
    return {
        "id": encounter_id,
        "status": values.get(f"{prefix}status"),
        "order": decode_order(values.get(f"{prefix}order")),
        "turn": _int_or_none(values.get(f"{prefix}turn")),
        "round": _int_or_none(values.get(f"{prefix}round")),
    }


def set_encounter_facts(
    campaign_id: int,
    encounter_id: str,
    *,
    status: str | None = None,
    order: list[str] | None = None,
    turn: int | None = None,
    round_no: int | None = None,
) -> None:
    """写遭遇事实（order 由系统编码为 JSON 数组字符串，LLM 禁写）。"""
    from app.trpg.encounter import encode_order

    prefix = f"encounter.{encounter_id}."
    _upsert_system_values(
        campaign_id,
        {
            f"{prefix}status": status,
            f"{prefix}order": None if order is None else encode_order(order),
            f"{prefix}turn": None if turn is None else str(int(turn)),
            f"{prefix}round": None if round_no is None else str(int(round_no)),
        },
    )


def get_active_encounter(campaign_id: int) -> dict | None:
    """当前进行中的遭遇（``encounter.{id}.status == active`` 中最近写入的一条）。"""
    db = get_session_factory()()
    try:
        row = (
            db.execute(
                select(TrpgFact)
                .where(
                    TrpgFact.campaign_id == campaign_id,
                    TrpgFact.fact_key.like("encounter.%.status"),
                    TrpgFact.value == "active",
                    TrpgFact.user_deleted_at.is_(None),
                )
                .order_by(TrpgFact.id.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )
    finally:
        db.close()
    if row is None:
        return None
    encounter_id = row.fact_key[len("encounter.") : -len(".status")]
    if not encounter_id:
        return None
    return get_encounter(campaign_id, encounter_id)


def _int_or_none(value: str | None) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _entity_dict(row: TrpgEntity) -> dict:
    return {
        "id": row.id,
        "kind": row.kind,
        "name": row.name,
        "status": row.status,
        "pending": row.pending,
        "portrait_media_id": row.portrait_media_id,
        "portrait": portrait_view(row.portrait_media_id),
    }


def get_entity(campaign_id: int, entity_id: int) -> dict | None:
    """按 id 读实体（立绘挂载端点用）。"""
    db = get_session_factory()()
    try:
        row = db.execute(
            select(TrpgEntity).where(
                TrpgEntity.id == entity_id, TrpgEntity.campaign_id == campaign_id
            )
        ).scalar_one_or_none()
        return _entity_dict(row) if row is not None else None
    finally:
        db.close()


def find_pc_entity(campaign_id: int) -> dict | None:
    """最近提及的 PC 实体（attack 默认攻击者来源）；无 PC 实体 → None。"""
    db = get_session_factory()()
    try:
        row = (
            db.execute(
                select(TrpgEntity)
                .where(TrpgEntity.campaign_id == campaign_id, TrpgEntity.kind == "pc")
                .order_by(TrpgEntity.last_mentioned_at.desc(), TrpgEntity.id.desc())
            )
            .scalars()
            .first()
        )
        return _entity_dict(row) if row is not None else None
    finally:
        db.close()


def set_entity_presence(
    campaign_id: int,
    kind: str,
    name: str,
    *,
    pending: bool | None = None,
    status: str | None = None,
) -> bool:
    """实体在场状态适配（docs/56 §B 映射：arriving↔pending=true / departed↔status=cleared）。"""
    db = get_session_factory()()
    try:
        row = db.execute(
            select(TrpgEntity).where(
                TrpgEntity.campaign_id == campaign_id,
                TrpgEntity.kind == kind,
                TrpgEntity.name == name,
            )
        ).scalar_one_or_none()
        if row is None:
            return False
        if pending is not None:
            row.pending = pending
        if status is not None:
            row.status = status
        row.last_mentioned_at = datetime.now(UTC)
        db.commit()
        return True
    finally:
        db.close()


def mark_entity_arriving(campaign_id: int, kind: str, name: str) -> None:
    """登场中（**预留**）：注册并标记 pending=True——「正在赶来」只留给未来的立绘任务。

    2026-09-22 起正常登场路径不再调用本函数（enter_character 直接 active，docs/57 §3.1）。
    """
    ensure_entity(campaign_id, kind, name, pending=True)
    set_entity_presence(campaign_id, kind, name, pending=True, status="active")


def mark_entity_departed(campaign_id: int, name: str) -> dict | None:
    """离场：``status=cleared`` + ``pending=False``；实体不存在 → None。"""
    entity = find_entity(campaign_id, name)
    if entity is None:
        return None
    set_entity_presence(campaign_id, str(entity["kind"]), name, pending=False, status="cleared")
    return find_entity(campaign_id, name)


def set_entity_portrait(campaign_id: int, entity_id: int, media_id: str | None) -> bool:
    """挂/卸实体立绘（media_id=None 为卸下）；实体不存在返回 False。"""
    db = get_session_factory()()
    try:
        row = db.execute(
            select(TrpgEntity).where(
                TrpgEntity.id == entity_id, TrpgEntity.campaign_id == campaign_id
            )
        ).scalar_one_or_none()
        if row is None:
            return False
        row.portrait_media_id = media_id
        row.last_mentioned_at = datetime.now(UTC)
        db.commit()
        return True
    finally:
        db.close()


def get_entity_portrait(
    campaign_id: int, name: str, kinds: tuple[str, ...] = ("npc", "pc")
) -> str | None:
    """按名字取实体立绘 media_id（重名取最近提及；无 → None）。"""
    db = get_session_factory()()
    try:
        return (
            db.execute(
                select(TrpgEntity.portrait_media_id)
                .where(
                    TrpgEntity.campaign_id == campaign_id,
                    TrpgEntity.name == name,
                    TrpgEntity.kind.in_(kinds),
                )
                .order_by(TrpgEntity.last_mentioned_at.desc())
            )
            .scalars()
            .first()
        )
    finally:
        db.close()


def mark_campaign_finished(campaign_id: int) -> None:
    """一局收尾标记（complete_quest 结算后调用；finished_at 为归档/新篇章判据）。"""
    db = get_session_factory()()
    try:
        row = db.get(TrpgCampaign, campaign_id)
        if row is not None:
            row.finished_at = datetime.now(UTC)
            db.commit()
    finally:
        db.close()


def campaign_finished_at(campaign_id: int) -> datetime | None:
    """一局收尾时间（None=尚在冒险中；GET state 的 finished/finished_at 数据源）。"""
    db = get_session_factory()()
    try:
        row = db.get(TrpgCampaign, campaign_id)
        return row.finished_at if row is not None else None
    finally:
        db.close()


def get_ending_payload(campaign_id: int, quest: str) -> dict | None:
    """读已落库的结局系统卡 payload（幂等结算返回「既有结局」的数据源）。

    返回 ``{quest, outcome, title, text, epilogue}``（剥掉 trpg_sys）；无卡/字段残缺 → None。
    """
    db = get_session_factory()()
    try:
        rows = (
            db.execute(
                select(TrpgMessage)
                .where(
                    TrpgMessage.campaign_id == campaign_id,
                    TrpgMessage.kind == "system",
                )
                .order_by(TrpgMessage.id.desc())
            )
            .scalars()
            .all()
        )
    finally:
        db.close()
    for row in rows:
        payload = row.payload if isinstance(row.payload, dict) else {}
        if payload.get("trpg_sys") != "ending" or payload.get("quest") != quest:
            continue
        ending = {
            key: payload.get(key) for key in ("quest", "outcome", "title", "text", "epilogue")
        }
        if not all(isinstance(ending[key], str) and ending[key] for key in ending):
            return None
        return ending
    return None


def persist_system_card(campaign_id: int, trpg_sys: str, payload: dict) -> None:
    """系统卡落库（kind=system + payload.trpg_sys；与 service._post_system_row 同协议）。"""
    add_message(
        campaign_id,
        "assistant",
        "",
        kind="system",
        payload={"trpg_sys": trpg_sys, **payload},
        meta={"trpg_sys": trpg_sys},
    )


def settle_quest(campaign_id: int, quest: str, outcome: str | None = None) -> dict:
    """确定性结算门面（complete_quest 工具与 settle 路由共用；docs/57 §3.1）。

    规则算术在 :mod:`app.trpg.progress`（纯函数），此处只做「读状态 → 落表 → 组装返回」：
    - 未结算：判定档位（显式 outcome 优先，否则按进度/威胁钟自动）→ ``quest.status`` 落表
      → 营地 ``finished_at`` 置位；
    - 已 done/failed：**幂等**——已有结局卡则原样返回其 payload；无卡（如提取器直接置 done）
      则补渲染一张（``existing=False``，由调用方决定落卡）。
    返回 ``{quest, outcome, status, title, text, epilogue, settled, existing, finished}``。
    """
    state = get_quest_state(campaign_id, quest)
    status = state.get("status")
    if status in ("done", "failed"):
        existing = get_ending_payload(campaign_id, quest)
        finished = campaign_finished_at(campaign_id) is not None
        if not finished:
            # 收敛：已结算但收尾标记缺失（历史数据/异常路径）→ 补置位，保证 finished 语义可信
            mark_campaign_finished(campaign_id)
            finished = True
        if existing is not None:
            return {
                "quest": quest,
                "status": status,
                "settled": False,
                "existing": True,
                "finished": finished,
                **existing,
            }
        plan = progress_rules.plan_settlement(
            quest,
            progress=state.get("progress"),
            kind=state.get("kind"),
            stage=state.get("stage"),
            status=status,
        )
        return {
            "quest": quest,
            "settled": False,
            "existing": False,
            "finished": finished,
            "outcome": plan.outcome,
            "status": plan.status,
            "title": plan.title,
            "text": plan.text,
            "epilogue": plan.epilogue,
        }

    plan = progress_rules.plan_settlement(
        quest,
        requested=outcome,
        progress=state.get("progress"),
        kind=state.get("kind"),
        stage=state.get("stage"),
    )
    set_quest_facts(campaign_id, quest, status=plan.status)
    mark_campaign_finished(campaign_id)
    return {
        "quest": quest,
        "settled": True,
        "existing": False,
        "finished": True,
        "outcome": plan.outcome,
        "status": plan.status,
        "title": plan.title,
        "text": plan.text,
        "epilogue": plan.epilogue,
    }


# ---------------------------------------------------------------------------
# 用户编辑/删除（P2-26/35 用户路径）
# ---------------------------------------------------------------------------
def edit_fact(campaign_id: int, key: str, value: str) -> bool:
    """用户编辑事实：写 user_touched_at（此后 LLM 提取拒写）。"""
    parsed = parse_key(key)
    if parsed is None:
        return False
    db = get_session_factory()()
    try:
        row = db.execute(
            select(TrpgFact).where(
                TrpgFact.campaign_id == campaign_id,
                TrpgFact.fact_key == key,
                TrpgFact.user_deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        now = datetime.now(UTC)
        if row is None:
            db.add(
                TrpgFact(
                    campaign_id=campaign_id,
                    kind=TrpgFactKinds.STATE
                    if parsed.domain in STATE_DOMAINS
                    else TrpgFactKinds.FACT,
                    fact_key=key,
                    value=value,
                    modality="fact",
                    user_touched_at=now,
                )
            )
        else:
            row.value = value
            row.user_touched_at = now
            row.version = (row.version or 1) + 1
        db.commit()
        return True
    finally:
        db.close()


def delete_fact(campaign_id: int, key: str) -> bool:
    """用户删除事实：写墓碑（P2-35；行保留供溯源，读路径过滤，提取永不复活）。"""
    db = get_session_factory()()
    try:
        row = db.execute(
            select(TrpgFact).where(
                TrpgFact.campaign_id == campaign_id,
                TrpgFact.fact_key == key,
                TrpgFact.user_deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            return False
        row.user_deleted_at = datetime.now(UTC)
        db.commit()
        return True
    finally:
        db.close()


def restore_fact(campaign_id: int, key: str, value: str) -> bool:
    """用户恢复：清墓碑 + 置 user_touched_at——只有用户路径能清（P2-35 单向）。"""
    db = get_session_factory()()
    try:
        row = db.execute(
            select(TrpgFact).where(
                TrpgFact.campaign_id == campaign_id,
                TrpgFact.fact_key == key,
                TrpgFact.user_deleted_at.is_not(None),
            )
        ).scalar_one_or_none()
        if row is None:
            return False
        row.value = value
        row.user_deleted_at = None
        row.user_touched_at = datetime.now(UTC)
        db.commit()
        return True
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 叙事摘要（P2-45：状态渲染，非对话压缩）
# ---------------------------------------------------------------------------
def render_narrative_summary(campaign_id: int) -> str:
    """由结构化状态渲染叙事摘要 + 最近 3 条事件尾部；写回 campaign.narrative_summary。"""
    db = get_session_factory()()
    try:
        facts = (
            db.execute(
                select(TrpgFact)
                .where(TrpgFact.campaign_id == campaign_id, TrpgFact.user_deleted_at.is_(None))
                .order_by(TrpgFact.importance.desc())
            )
            .scalars()
            .all()
        )
        tasks = (
            db.execute(select(TrpgTask).where(TrpgTask.campaign_id == campaign_id)).scalars().all()
        )
        clues = (
            db.execute(select(TrpgClue).where(TrpgClue.campaign_id == campaign_id)).scalars().all()
        )
        events = (
            db.execute(
                select(TrpgEvent)
                .where(TrpgEvent.campaign_id == campaign_id)
                .order_by(TrpgEvent.round.desc())
                .limit(3)
            )
            .scalars()
            .all()
        )
        scene_row = next((f for f in facts if f.fact_key == "scene.current"), None)
        snapshot = build_state_snapshot(
            SnapshotInput(
                facts=[
                    SnapshotFact(
                        key=f.fact_key,
                        kind=f.kind,
                        value=f.value,
                        modality=f.modality,
                        speaker=f.speaker,
                        importance=f.importance,
                    )
                    for f in facts
                ],
                tasks=[SnapshotTask(title=t.title, status=t.status) for t in tasks],
                clues=[
                    SnapshotClue(
                        title=c.title,
                        content=c.content,
                        scene=c.scene,
                        found=c.found,
                        recovered=c.recovered,
                        last_mentioned_at=c.last_mentioned_at,
                    )
                    for c in clues
                ],
                scene=scene_row.value if scene_row is not None else None,
            )
        )
        event_tail = "\n".join(f"• {e.summary}" for e in reversed(events))
        summary = "\n\n".join(
            part for part in (snapshot, f"最近事件：\n{event_tail}" if event_tail else "") if part
        )
        row = db.get(TrpgCampaign, campaign_id)
        if row is not None:
            row.narrative_summary = summary or None
        db.commit()
        return summary
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 任务 / 线索 / 实体 / 消息（面板与快照消费）
# ---------------------------------------------------------------------------
def list_tasks(campaign_id: int) -> list[dict]:
    db = get_session_factory()()
    try:
        rows = (
            db.execute(
                select(TrpgTask)
                .where(TrpgTask.campaign_id == campaign_id)
                .order_by(TrpgTask.status.asc(), TrpgTask.last_mentioned_at.desc())
            )
            .scalars()
            .all()
        )
        return [
            {
                "id": r.id,
                "title": r.title,
                "status": r.status,
                "scene": r.scene,
                "last_mentioned_at": r.last_mentioned_at,
            }
            for r in rows
        ]
    finally:
        db.close()


def list_clues(campaign_id: int) -> list[dict]:
    db = get_session_factory()()
    try:
        rows = (
            db.execute(
                select(TrpgClue)
                .where(TrpgClue.campaign_id == campaign_id)
                .order_by(TrpgClue.last_mentioned_at.desc())
            )
            .scalars()
            .all()
        )
        return [
            {
                "id": r.id,
                "title": r.title,
                "content": r.content,
                "scene": r.scene,
                "found": r.found,
                "recovered": r.recovered,
                "last_mentioned_at": r.last_mentioned_at,
            }
            for r in rows
        ]
    finally:
        db.close()


def list_entities(campaign_id: int) -> list[dict]:
    db = get_session_factory()()
    try:
        rows = (
            db.execute(select(TrpgEntity).where(TrpgEntity.campaign_id == campaign_id))
            .scalars()
            .all()
        )
        return [
            {
                "id": r.id,
                "kind": r.kind,
                "name": r.name,
                "status": r.status,
                "pending": r.pending,
                "portrait_media_id": r.portrait_media_id,
                "portrait": portrait_view(r.portrait_media_id),
            }
            for r in rows
        ]
    finally:
        db.close()


def create_task(campaign_id: int, title: str, scene: str | None = None) -> bool:
    """主持台建任务：任务行 + 同步 quest 事实（立即进快照）。"""
    t = (title or "").strip()[:60]
    if not t:
        return False
    db = get_session_factory()()
    try:
        db.add(
            TrpgTask(
                campaign_id=campaign_id,
                title=t,
                status=TrpgTaskStatuses.ACTIVE,
                scene=(scene or None),
                last_mentioned_at=datetime.now(UTC),
            )
        )
        db.commit()
    finally:
        db.close()
    upsert_facts(
        campaign_id,
        [FactOp(op="create", key=f"quest.{t}.status", value="active", writer="system")],
    )
    return True


def set_task_status(campaign_id: int, task_id: int, status: str) -> bool:
    if status not in _VALID_TASK_STATUSES:
        return False
    db = get_session_factory()()
    try:
        row = db.execute(
            select(TrpgTask).where(TrpgTask.id == task_id, TrpgTask.campaign_id == campaign_id)
        ).scalar_one_or_none()
        if row is None:
            return False
        row.status = status
        row.last_mentioned_at = datetime.now(UTC)
        row.user_touched_at = datetime.now(UTC)
        db.commit()
        title = row.title
    finally:
        db.close()
    upsert_facts(
        campaign_id,
        [FactOp(op="update", key=f"quest.{title}.status", value=status, writer="system")],
    )
    return True


def create_clue(
    campaign_id: int, title: str, content: str | None = None, scene: str | None = None
) -> bool:
    t = (title or "").strip()[:60]
    if not t:
        return False
    db = get_session_factory()()
    try:
        db.add(
            TrpgClue(
                campaign_id=campaign_id,
                title=t,
                content=(content or None),
                scene=(scene or None),
                found=True,
                recovered=False,
                last_mentioned_at=datetime.now(UTC),
            )
        )
        db.commit()
        return True
    finally:
        db.close()


def set_clue_recovered(campaign_id: int, clue_id: int, recovered: bool) -> bool:
    db = get_session_factory()()
    try:
        row = db.execute(
            select(TrpgClue).where(TrpgClue.id == clue_id, TrpgClue.campaign_id == campaign_id)
        ).scalar_one_or_none()
        if row is None:
            return False
        row.recovered = recovered
        row.last_mentioned_at = datetime.now(UTC)
        db.commit()
        return True
    finally:
        db.close()


def add_message(
    campaign_id: int,
    role: str,
    content: str,
    *,
    kind: str = TrpgMessageKinds.TEXT,
    payload: dict | None = None,
    meta: dict | None = None,
    usage: dict | None = None,
    audio_url: str | None = None,
) -> TrpgMessage:
    db = get_session_factory()()
    try:
        row = TrpgMessage(
            campaign_id=campaign_id,
            role=role,
            kind=kind,
            content=content,
            payload=payload,
            meta=meta,
            usage=usage,
            audio_url=audio_url,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row
    finally:
        db.close()


def list_messages(campaign_id: int, limit: int = 200) -> list[dict]:
    """最近 limit 条消息（按 id 升序返回；系统卡与文本消息同流）。"""
    db = get_session_factory()()
    try:
        rows = (
            db.execute(
                select(TrpgMessage)
                .where(TrpgMessage.campaign_id == campaign_id)
                .order_by(TrpgMessage.id.desc())
                .limit(limit)
            )
            .scalars()
            .all()
        )
        out = []
        for r in reversed(rows):
            out.append(
                {
                    "id": r.id,
                    "role": r.role,
                    "kind": r.kind,
                    "content": r.content,
                    "payload": r.payload,
                    "meta": r.meta,
                    "audio_url": r.audio_url,
                    "created_at": r.created_at,
                }
            )
        return out
    finally:
        db.close()


def clear_messages(campaign_id: int) -> int:
    """清空对话流水（重开剧本用；事实/任务/线索保留）。"""
    db = get_session_factory()()
    try:
        result = db.execute(delete(TrpgMessage).where(TrpgMessage.campaign_id == campaign_id))
        db.commit()
        return int(result.rowcount or 0)
    finally:
        db.close()


def campaign_state(campaign_id: int) -> dict[str, Any]:
    """全量状态（主持台一次拉全：事实/任务/线索/实体/事件/快照/校验）。"""
    from app.trpg.constants import DANGLING_WINDOW_MS
    from app.trpg.verify import (
        build_missing_patch,
        detect_contradiction,
        detect_dangling,
        verify_gap,
    )

    db = get_session_factory()()
    try:
        campaign = db.get(TrpgCampaign, campaign_id)
        narrative_summary = (campaign.narrative_summary if campaign is not None else "") or ""
    finally:
        db.close()
    facts = list_facts(campaign_id)
    tasks = list_tasks(campaign_id)
    clues = list_clues(campaign_id)
    entities = list_entities(campaign_id)
    events = list_events(campaign_id)
    scene = get_scene(campaign_id)
    snapshot = build_state_snapshot(
        SnapshotInput(
            facts=[
                SnapshotFact(
                    key=f["key"],
                    kind=f["kind"],
                    value=f["value"],
                    modality=f["modality"],
                    speaker=f["speaker"],
                    importance=f["importance"],
                )
                for f in facts
            ],
            tasks=[SnapshotTask(title=t["title"], status=t["status"]) for t in tasks],
            clues=[
                SnapshotClue(
                    title=c["title"],
                    content=c["content"],
                    scene=c["scene"],
                    found=c["found"],
                    recovered=c["recovered"],
                    last_mentioned_at=c["last_mentioned_at"],
                )
                for c in clues
            ],
            scene=scene,
        )
    )
    dangling = detect_dangling(tasks, clues, datetime.now(UTC), DANGLING_WINDOW_MS)
    gap, missing = verify_gap(dangling, narrative_summary)
    contradiction = detect_contradiction(narrative_summary, facts)
    return {
        "facts": facts,
        "tasks": tasks,
        "clues": clues,
        "entities": entities,
        "events": events,
        "scene": scene,
        "snapshot": snapshot,
        "narrative_summary": narrative_summary,
        "verify": {
            "dangling": [
                {
                    "type": d.type,
                    "id": d.id,
                    "title": d.title,
                    "last_mentioned_at": d.last_mentioned_at,
                }
                for d in dangling
            ],
            "gap": gap,
            "missing": [{"type": m.type, "id": m.id, "title": m.title} for m in missing],
            "patch_text": build_missing_patch(missing),
            "contradiction": contradiction,
        },
    }
