"""PR#25 复审补测（评审者提交）：sessions/attempts 模型与迁移 0003 同步性回归。

背景（docs/10 §7.1：Alembic 唯一 schema 真源，模型 ↔ 迁移零漂移）：
迁移 0003 为 sessions 增加 ``shadow_material_id`` 列、kind CHECK 扩 ``shadow``，
attempts.kind CHECK 扩 ``shadow_speech``——但 ``app/models/practice.py`` 未同步：
- 测试库（create_all 按模型建 CHECK）写 kind='shadow' 直接 IntegrityError；
- ``mastery/service.update_session_mastery`` 引用 ``session.shadow_material_id``（模型无此
  字段）→ 无 scenario_id 的会话（shadow/sing/defense）收尾挂钩抛 AttributeError，
  被 ``_post_session_skills`` 的 try/except 吞掉：动态水平与掌握度整段静默跳过。

本文件两用例在模型同步修复前必红（``pr #25 复审 2026-09-02``）。
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from app.db import get_session_factory
from app.mastery.service import update_session_mastery
from app.models import Attempt, ShadowMaterial, User
from app.models import Session as DbSession
from app.models.base import AttemptKinds, SessionKinds, SessionStatus


def _mk_user() -> int:
    db = get_session_factory()()
    try:
        u = User(username=f"u{uuid4().hex[:8]}", nickname="t", password_hash="x")
        db.add(u)
        db.flush()
        db.commit()
        return int(u.id)
    finally:
        db.close()


def test_shadow_session_orm_roundtrip() -> None:
    """影子会话可经 ORM 落库：kind='shadow' + shadow_material_id 双向可达。

    修复前必红：``DbSession(shadow_material_id=...)`` 是未映射属性（TypeError）或
    kind='shadow' 违反模型侧 CHECK ``ck_sessions_kind``（IntegrityError）——
    迁移 0003 已扩这两个能力，模型必须同步（docs/10 §7.1）。
    """
    uid = _mk_user()
    db = get_session_factory()()
    try:
        m = ShadowMaterial(
            title="shadow-model-sync",
            level=2,
            text_content="hello",
            audio_url="/demo/audio/shadow/model-sync.mp3",
            status="published",
        )
        db.add(m)
        db.flush()
        mid = int(m.id)
        s = DbSession(
            user_id=uid,
            kind=SessionKinds.SHADOW,
            scenario_id=None,
            shadow_material_id=mid,
            status=SessionStatus.ACTIVE,
        )
        db.add(s)
        db.flush()
        assert s.shadow_material_id == mid
    finally:
        db.close()


def test_mastery_hook_survives_materialless_session() -> None:
    """收尾挂钩 update_session_mastery 对无 scenario_id 的会话不抛 AttributeError。

    修复前必红：``session.scenario_id or session.shadow_material_id`` 访问未映射属性 →
    AttributeError（''Session'' object has no attribute ''shadow_material_id''）。
    该异常被 complete_session 的 _post_session_skills try/except 吞掉，动态水平与掌握度
    对这类会话永不更新（仅一条 warning 日志）。
    """
    uid = _mk_user()
    db = get_session_factory()()
    try:
        s = DbSession(user_id=uid, kind=SessionKinds.SING, status=SessionStatus.COMPLETED)
        db.add(s)
        db.flush()
        db.add(
            Attempt(
                user_id=uid,
                session_id=s.id,
                kind=AttemptKinds.FREE_PRACTICE,
                pron_score=Decimal("80"),
                flu_score=Decimal("80"),
            )
        )
        db.commit()
        update_session_mastery(db, int(s.id))  # 应不抛异常（影子会话同路径）
    finally:
        db.close()
