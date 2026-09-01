"""DB 接入：engine / Session 工厂 / 依赖（docs/18 §3-J2）。

约定（docs/06 §10 · docs/10 §7）：
- Alembic 唯一 schema 真源；本模块不做任何 DDL（测试用 create_all 除外）；
- 默认 sqlite 文件库（本地零配置）；PG 由 APP_DATABASE_URL 覆盖（compose 内 postgres:16）；
- 写后提交纪律：本次 M2 仅 Python 写方（sessions/attempts/events/defense_profiles/placements）。
"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

_engine = None
_session_factory: sessionmaker[Session] | None = None


def get_engine():
    """惰性单例 engine（SQLite 需 check_same_thread=False 便于测试/多线程）。"""
    global _engine
    if _engine is None:
        url = get_settings().database_url
        kwargs: dict = {"pool_pre_ping": True}
        if url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False}
            if ":memory:" in url:
                from sqlalchemy.pool import StaticPool

                kwargs["poolclass"] = StaticPool  # 内存库须单连接共享（测试）
        _engine = create_engine(url, **kwargs)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _session_factory


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖：每请求一个 Session。"""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def create_all_for_tests() -> None:
    """单测专用：SQLite create_all（与 Alembic 解耦；生产一律走迁移）。"""
    from app.models import Base

    Base.metadata.create_all(get_engine())


def reset_engine() -> None:
    """测试专用：重置单例（每次环境变量/URL 变更后调用）。"""
    global _engine, _session_factory
    _engine = None
    _session_factory = None
