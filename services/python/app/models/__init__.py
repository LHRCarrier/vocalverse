"""SQLAlchemy 模型包（schema 唯一真源入口，docs/06 §10）。

- Alembic autogenerate 依赖本包：``from app import models`` 即注册全部表；
- 写归属与字段说明见 ``docs/10-数据库设计.md``；
- Java JPA 按本包做纯映射（``ddl-auto=none``），禁止在 Java 侧重复定义约束/FK。
"""

from __future__ import annotations

from .analytics import Event, Report
from .base import Base, jsonb
from .community import (
    DirectMessage,
    DmReadState,
    Follow,
    Post,
    PostComment,
    PostInteraction,
    PostLike,
)
from .console_moderation import ModerationCase, ModerationReport
from .console_rbac import (
    AdminAuditLog,
    AdminLoginAttempt,
    AdminPermission,
    AdminRole,
    AdminRolePermission,
    AdminSession,
    AdminUser,
)
from .console_telemetry import (
    LlmSpan,
    LlmSpanContent,
    LlmTrace,
    OpsAlertEvent,
    OpsAlertRule,
    OpsMetricSample,
)
from .content import (
    ListeningMaterial,
    Lrc,
    PitchExtractJob,
    PlacementQuestion,
    Scenario,
    ScenarioMessage,
    ShadowMaterial,
    Song,
    SongPitchRef,
)
from .defense import DefenseProfile
from .difficulty import MaterialDifficulty
from .mastery import UserCorpusMastery, UserMastery
from .media import MediaAsset, MediaKinds, MediaStatus
from .practice import Attempt, Score, Session, SingAttempt, SongFavorite
from .reading import (
    Book,
    BookChapter,
    DictionaryEntry,
    DictionaryForm,
    ReadingAnnotation,
    TtsTask,
    UserReadingProgress,
    UserVocabulary,
)
from .skill import UserSkillState
from .tickets import Ticket
from .usage import UsageLog
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
    "ShadowMaterial",
    "Song",
    "Lrc",
    "SongPitchRef",
    "PitchExtractJob",
    "ListeningMaterial",
    "PlacementQuestion",
    # 练习域
    "Session",
    "Attempt",
    "Score",
    "SingAttempt",
    "SongFavorite",
    # 读书域（docs/45 · Python 写方；Java 零改动）
    "Book",
    "BookChapter",
    "DictionaryEntry",
    "DictionaryForm",
    "UserReadingProgress",
    "UserVocabulary",
    "ReadingAnnotation",
    "TtsTask",
    # 社区域（Java 写方 · Python 只读映射，docs/37 §3）
    "Post",
    "PostComment",
    "PostLike",
    "PostInteraction",
    "Follow",
    # 私信域（Java 写方 · Python 只读映射，docs/49 §1 · 迁移 0012）
    "DirectMessage",
    "DmReadState",
    # 管理端控制台 RBAC 域（Java 写方 · Python 只读映射，docs/50 §5.3.1~§5.3.7 · 迁移 0013）
    "AdminUser",
    "AdminRole",
    "AdminPermission",
    "AdminRolePermission",
    "AdminSession",
    "AdminLoginAttempt",
    "AdminAuditLog",
    # 管理端控制台审核域（Java 写方 · Python 只读映射，docs/50 §5.3.8~§5.3.9）
    "ModerationCase",
    "ModerationReport",
    # 管理端控制台运维遥测 / LLM Trace 域（Python 写方，docs/50 §5.3.10~§5.3.15）
    "OpsMetricSample",
    "OpsAlertRule",
    "OpsAlertEvent",
    "LlmTrace",
    "LlmSpan",
    "LlmSpanContent",
    # 媒体域（社区 S3 · Python 写方，docs/47 §3.1）
    "MediaAsset",
    "MediaKinds",
    "MediaStatus",
    # 答辩域
    "DefenseProfile",
    # 推荐域（local/31 §2，2026-09-02 设计）
    "UserSkillState",
    "MaterialDifficulty",
    "UserMastery",
    "UserCorpusMastery",
    # LLM 框架域（docs/26 §10.3，迁移 0004）
    "UsageLog",
    # 分析/支持域
    "Event",
    "Report",
    "Ticket",
]
