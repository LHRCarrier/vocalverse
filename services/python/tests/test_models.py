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
from sqlalchemy import UniqueConstraint, create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

SERVICE_ROOT = Path(__file__).resolve().parents[1]

#: 读书域表（docs/45 · 迁移 0010）：离线渲染回归守卫逐表断言 PRIMARY KEY
READING_TABLES = (
    "books",
    "book_chapters",
    "dictionary_entries",
    "dictionary_forms",
    "user_reading_progress",
    "user_vocabulary",
    "reading_annotations",
    "tts_tasks",
)

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
    # 读书域（docs/45 · 迁移 0010；含词形反向索引表）
    "books",
    "book_chapters",
    "dictionary_entries",
    "dictionary_forms",
    "user_reading_progress",
    "user_vocabulary",
    "reading_annotations",
    "tts_tasks",
    # 管理端控制台域（docs/50 §5 · 迁移 0013：RBAC 7 + 审核 2 + 运维遥测/LLM Trace 6）
    "admin_users",
    "admin_roles",
    "admin_permissions",
    "admin_role_permissions",
    "admin_sessions",
    "admin_login_attempts",
    "admin_audit_logs",
    "moderation_cases",
    "moderation_reports",
    "ops_metric_samples",
    "ops_alert_rules",
    "ops_alert_events",
    "llm_traces",
    "llm_spans",
    "llm_span_contents",
    "pitch_extract_jobs",  # 唱歌 P0 迁移 0014（2026-09-09；合并 main 后重排）
    "song_favorites",  # 跟唱收藏 迁移 0015（2026-09-10；合并 main 后重排）
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


# ---------------------------------------------------------------------------
# 唱歌 P0（迁移 0014 · 2026-09-09）：pitch_extract_jobs / sing_attempts 版本列 / songs.vocal_ref_url
# ---------------------------------------------------------------------------
def _seed_song_with_lrc(session) -> tuple[int, int]:
    """建 song + 2 行 lrc，返回 (song_id, lrc_id)。"""
    from app import models as m

    song = m.Song(title="Twinkle", level=1, audio_url="/data/audio/twinkle.wav")
    session.add(song)
    session.flush()
    lrc = m.Lrc(
        song_id=song.id,
        seq=1,
        offset_ms=0,
        end_offset_ms=2000,
        line_text="Twinkle twinkle",
    )
    session.add(lrc)
    session.flush()
    return song.id, lrc.id


def test_pitch_job_status_check_enforced(sqlite_engine):
    """pitch_extract_jobs.status 枚举 CHECK（docs/10 · 迁移 0014）：非法状态拒绝。"""
    from app import models as m

    with Session(sqlite_engine) as session, pytest.raises(IntegrityError):
        song_id, lrc_id = _seed_song_with_lrc(session)
        session.add(
            m.PitchExtractJob(song_id=song_id, lrc_id=lrc_id, revision="lrc=1", status="paused")
        )
        session.commit()


def test_pitch_job_partial_unique_active_per_lrc(sqlite_engine):
    """部分唯一索引 uq_pitch_extract_jobs_lrc_active：同一 lrc 只允许一个 queued/running 任务。"""
    from app import models as m

    with Session(sqlite_engine) as session:
        song_id, lrc_id = _seed_song_with_lrc(session)
        session.add(m.PitchExtractJob(song_id=song_id, lrc_id=lrc_id, revision="lrc=1"))
        session.commit()
    # 第二个 queued 任务 → 唯一索引冲突（SQLite 同样生效，docs/10 §7 双方言）
    with Session(sqlite_engine) as session, pytest.raises(IntegrityError):
        session.add(m.PitchExtractJob(song_id=song_id, lrc_id=lrc_id, revision="lrc=1"))
        session.commit()


def test_pitch_job_done_then_new_active_allowed(sqlite_engine):
    """done 后的任务不再占用部分唯一索引：LRC 重写 → 旧任务 done → 新任务可建（世代重建）。"""
    from app import models as m

    with Session(sqlite_engine) as session:
        song_id, lrc_id = _seed_song_with_lrc(session)
        session.add(
            m.PitchExtractJob(song_id=song_id, lrc_id=lrc_id, revision="lrc=1", status="done")
        )
        session.commit()
    with Session(sqlite_engine) as session:
        session.add(m.PitchExtractJob(song_id=song_id, lrc_id=lrc_id, revision="lrc=2"))
        session.commit()


def test_sing_attempts_scoring_version_default(sqlite_engine):
    """sing_attempts.scoring_version 默认 'v1'（迁移 0014 · D10 可追溯快照）。"""
    from app import models as m

    with Session(sqlite_engine) as session:
        song_id, _ = _seed_song_with_lrc(session)
        attempt = m.SingAttempt(user_id=1, song_id=song_id, duration_s=90, lines=[], alignment={})
        session.add(attempt)
        session.commit()
        assert attempt.scoring_version == "v1"
        assert attempt.ref_version is None


def _seed_sing_session(session, song_id: int) -> int:
    """建一条 sing 会话（user_id=1 不建真实用户——SQLite 测试库默认不校验 FK，与其他用例同口径）。"""
    from app import models as m

    sess = m.Session(user_id=1, kind="sing", song_id=song_id, assigned_turns=3)
    session.add(sess)
    session.commit()
    return int(sess.id)


# ---------------------------------------------------------------------------
# 跟唱幂等键（迁移 0016 · 2026-09-10 · P1-3；合并 main 后重排编号）：
# sing_attempts UNIQUE(user_id, session_id)
# ---------------------------------------------------------------------------
def test_sing_attempt_unique_per_user_session(sqlite_engine):
    """uq_sing_attempts_user_session：同一 (user, session) 只允许一行
    （幂等重试的地基，docs/10 §4.3）。

    修复前必失败：迁移 0012 之前无该唯一键——并发双击/弱网重传可落两行，
    重复消耗 pyin/DTW CPU 且污染看板（拷问报告 P1-3 / B-F7 / C-#3 / G-#9）。

    语义：`session_id` 可空（会话删除时 SET NULL）——SQL 唯一索引对 NULL 不冲突，
    历史/脱离会话的行不受影响（末尾用例覆盖）。
    """
    from app import models as m

    with Session(sqlite_engine) as session:
        song_id, _ = _seed_song_with_lrc(session)
        session_id = _seed_sing_session(session, song_id)
        session.add(
            m.SingAttempt(user_id=1, session_id=session_id, song_id=song_id, duration_s=3, lines=[])
        )
        session.commit()
    with Session(sqlite_engine) as session, pytest.raises(IntegrityError):
        session.add(
            m.SingAttempt(user_id=1, session_id=session_id, song_id=song_id, duration_s=3, lines=[])
        )
        session.commit()
    # 不同用户 / 不同会话互不冲突（幂等键只锁"同一人的同一会话"）
    with Session(sqlite_engine) as session:
        session.add(
            m.SingAttempt(user_id=2, session_id=session_id, song_id=song_id, duration_s=3, lines=[])
        )
        session.add(
            m.SingAttempt(user_id=1, session_id=None, song_id=song_id, duration_s=3, lines=[])
        )
        session.add(
            m.SingAttempt(user_id=1, session_id=None, song_id=song_id, duration_s=3, lines=[])
        )
        session.commit()


def test_sing_attempt_unique_key_present_in_metadata():
    """模型元数据必须显式声明唯一键（不依赖迁移手写 SQL——`alembic check` 对账靠它）。"""
    from app import models as m

    names = {
        c.name
        for c in m.SingAttempt.__table__.constraints
        if isinstance(c, UniqueConstraint)  # noqa: F821 —— 运行时导入见上
    }
    assert "uq_sing_attempts_user_session" in names, (
        "SingAttempt 缺 UNIQUE(user_id, session_id)：迁移 0012 与模型元数据会漂移"
    )


# ---------------------------------------------------------------------------
# 跟唱收藏（迁移 0015 · 2026-09-10）：song_favorites 唯一键
# ---------------------------------------------------------------------------
def test_song_favorite_unique_per_user_song(sqlite_engine):
    """uq_song_favorites_user_song：同一用户同一首歌只允许一行（幂等收藏的地基，docs/10）。

    修复前必失败：该表/唯一键由迁移 0011 引入，此前不存在。
    """
    from app import models as m

    with Session(sqlite_engine) as session:
        song_id, _ = _seed_song_with_lrc(session)
        session.add(m.SongFavorite(user_id=1, song_id=song_id))
        session.commit()
    with Session(sqlite_engine) as session, pytest.raises(IntegrityError):
        session.add(m.SongFavorite(user_id=1, song_id=song_id))
        session.commit()
    # 不同用户互不冲突（收藏按用户隔离）
    with Session(sqlite_engine) as session:
        session.add(m.SongFavorite(user_id=2, song_id=song_id))
        session.commit()


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
    # 读书域 8 表（docs/45 · 迁移 0010）：每表必须带 PRIMARY KEY ——
    # 2026-09-10 实跑复现：_bigint_pk() 漏 primary_key=True → PG 因 FK 引用列无唯一约束
    # 直接拒绝建表（InvalidForeignKey），离线渲染不校验运行时行为 → 此项为回归守卫。
    for table in READING_TABLES:
        block = _create_table_block(out, table)
        assert block is not None, f"迁移未产出 {table}：{out[:2000]}"
        assert "PRIMARY KEY" in block, f"{table} 缺 PRIMARY KEY：{block}"


def _create_table_block(out: str, table: str) -> str | None:
    """从离线渲染输出抽取单张 CREATE TABLE 块（对齐 alembic 双空格缩进格式）。"""
    start = out.find(f"CREATE TABLE {table} (")
    if start < 0:
        return None
    end = out.find("\n\n", start)
    return out[start : end if end > 0 else len(out)]


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
