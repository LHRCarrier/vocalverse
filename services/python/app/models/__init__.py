"""SQLAlchemy 模型包（schema 唯一真源入口，docs/06 §10）。

- Alembic autogenerate 依赖本包：``from app import models`` 即注册全部表；
- 写归属与字段说明见 ``docs/10-数据库设计.md``；
- Java JPA 按本包做纯映射（``ddl-auto=none``），禁止在 Java 侧重复定义约束/FK。
"""

from __future__ import annotations

from .analytics import Event, Report
from .base import Base, jsonb
from .content import (
    ListeningMaterial,
    Lrc,
    PlacementQuestion,
    Scenario,
    ScenarioMessage,
    Song,
    SongPitchRef,
)
from .practice import Attempt, PostLike, Score, Session, SingAttempt
from .tickets import Ticket
from .user import Placement, RefreshToken, User, UserProfile

__all__ = [
    "Base",
    "jsonb",
    # 账户域
    "User",
    "UserProfile",
    "RefreshToken",
    "Placement",
    # 内容域
    "Scenario",
    "ScenarioMessage",
    "Song",
    "Lrc",
    "SongPitchRef",
    "ListeningMaterial",
    "PlacementQuestion",
    # 练习域
    "Session",
    "Attempt",
    "Score",
    "SingAttempt",
    "PostLike",
    # 分析/支持域
    "Event",
    "Report",
    "Ticket",
]
