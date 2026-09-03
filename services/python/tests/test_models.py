"""模型/迁移一致性冒烟（docs/06 §6 + docs/10 §8 验证项）。

- SQLite create_all 兼容（JSONB with_variant 声明，docs/09 4.3）；
- 关键约束与索引在 SQLite 单测同样生效（CHECK / 表达式唯一索引 / 幂等键唯一）；
- alembic 单头断言 + PG 方言离线 SQL 渲染（无需真库，验证迁移文件对 PG 可编译）。
注：正式 schema 以 PG 为准（docker-compose postgres:16），`alembic check` 待 M2 接 PG 后启用。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from alembic.script import ScriptDirectory
from app.models import Base, Event, User
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

SERVICE_ROOT = Path(__file__).resolve().parents[1]

EXPECTED_TABLES = {
    "users",
    "user_profiles",
    "placements",
    "placement_questions",
    "refresh_tokens",
    "scenarios",
    "scenario_messages",
    "sessions",
    "attempts",
    "scores",
    "songs",
    "lrc",
    "song_pitch_refs",
    "sing_attempts",
    "events",
    "reports",
    "tickets",
    "listening_materials",
    "post_likes",
    "defense_profiles",
    "usage_log",
}


@pytest.fixture()
def sqlite_engine():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


def _alembic_config() -> Config:
    # alembic.ini 在 services/python 根；路径须绝对化（Windows 下 cwd 依赖不可靠）
    cfg = Config(str(SERVICE_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(SERVICE_ROOT / "alembic"))
    return cfg


def test_create_all_sqlite_tables(sqlite_engine):
    """docs/09 4.3：JSONB 字段经 with_variant 声明，SQLite 单测 create_all 不炸。"""
    names = set(inspect(sqlite_engine).get_table_names())
    assert names >= EXPECTED_TABLES, f"缺表: {EXPECTED_TABLES - names}"


def test_check_constraint_enforced(sqlite_engine):
    """维度枚举落在 CHECK 上（VARCHAR+CHECK 而非 PG ENUM），SQLite 单测同样校验。"""
    with Session(sqlite_engine) as session, pytest.raises(IntegrityError):
        session.add(
            User(username="alice", email=None, password_hash="x", nickname="A", role="sudo")
        )
        session.commit()


def test_username_case_insensitive_unique(sqlite_engine):
    """写归属约定：用户名大小写不敏感唯一（lower() 表达式唯一索引）。"""
    with Session(sqlite_engine) as session:
        session.add(User(username="Alice", email=None, password_hash="x", nickname="A"))
        session.commit()
    with Session(sqlite_engine) as session, pytest.raises(IntegrityError):
        session.add(User(username="alice", email=None, password_hash="x", nickname="A2"))
        session.commit()


def test_event_client_event_id_unique(sqlite_engine):
    """埋点幂等键：同 client_event_id 重传必须冲突（服务端去重前置）。"""
    import datetime

    ts = datetime.datetime.now(datetime.UTC)
    with Session(sqlite_engine) as session:
        session.add(Event(event_type="page_view", client_event_id="evt-1", occurred_at=ts))
        session.commit()
    with Session(sqlite_engine) as session, pytest.raises(IntegrityError):
        session.add(Event(event_type="page_view", client_event_id="evt-1", occurred_at=ts))
        session.commit()


def test_event_channel_check_enforced(sqlite_engine):
    """渠道枚举落在 CHECK（docs/11 Q-B16）；SQLite 同样校验。"""
    import datetime

    ts = datetime.datetime.now(datetime.UTC)
    with Session(sqlite_engine) as session, pytest.raises(IntegrityError):
        session.add(
            Event(
                event_type="page_view", client_event_id="evt-bad", occurred_at=ts, channel="wechat"
            )
        )
        session.commit()


def test_event_origin_tightened_check(sqlite_engine):
    """场景消息 origin 仅 user 行可带（docs/11 Q-B04）：assistant 行带 origin 违反 CHECK。"""
    from app import models as m

    with Session(sqlite_engine) as session:
        user = m.User(username="bob", email=None, password_hash="x", nickname="B")
        session.add(user)
        session.flush()
        sess = m.Session(user_id=user.id, kind="dialog")
        session.add(sess)
        session.flush()
        session.add(
            m.ScenarioMessage(
                session_id=sess.id,
                seq=1,
                role="assistant",
                origin="proactive",  # 非法：assistant 行不得带 origin
                content="hello",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_alembic_single_head():
    """CI 同款单头断言：迁移历史必须线性单头。"""
    heads = ScriptDirectory.from_config(_alembic_config()).get_heads()
    assert len(heads) == 1, f"alembic 多头：{heads}"


def test_alembic_offline_pg_render(capsys, monkeypatch):
    """PG 方言离线渲染：迁移文件对 PG16 可编译，产出全部业务表且带 JSONB/IDENTITY。

    断言用 EXPECTED_TABLES 推导（docs/11 Q-A12：不硬编码表数）。
    """
    monkeypatch.setenv(
        "APP_DATABASE_URL",
        "postgresql+psycopg://vocalverse:vocalverse-dev@localhost:5432/vocalverse",
    )
    result = alembic_command.upgrade(_alembic_config(), "head", sql=True)
    captured = capsys.readouterr()
    out = result if isinstance(result, str) else (captured.out + captured.err)
    assert not out.startswith("Traceback"), out[:2000]
    # 19 业务表 + alembic_version + （可选）版本表重复声明，故用 >=
    assert out.count("CREATE TABLE") >= len(EXPECTED_TABLES) + 1, out[:2000]
    assert "JSONB" in out
    assert "GENERATED BY DEFAULT AS IDENTITY" in out
    # 表达式唯一索引已人工补回（docs/11 Q-A05）
    assert "lower(username)" in out


def test_alembic_offline_pg_downgrade(capsys, monkeypatch):
    """PG 方言离线渲染 downgrade：head→base 全路径逆序可编译（docs/10 §7.1 幂等逆序，FK 依赖安全）。

    覆盖 0002（含 CHECK 反转 + defense_profiles 回退），与 alembic 单头策略一致。
    """
    monkeypatch.setenv(
        "APP_DATABASE_URL",
        "postgresql+psycopg://vocalverse:vocalverse-dev@localhost:5432/vocalverse",
    )
    result = alembic_command.downgrade(_alembic_config(), "head:base", sql=True)
    captured = capsys.readouterr()
    out = result if isinstance(result, str) else (captured.out + captured.err)
    assert not out.startswith("Traceback"), out[:2000]
    assert out.count("DROP TABLE") >= len(EXPECTED_TABLES), out[:2000]
