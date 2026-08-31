"""Alembic 迁移环境 —— 唯一 schema 真源（docs/06 第 10 章 / docs/10 数据库设计）。

- 连接串：环境变量 APP_DATABASE_URL（优先，与 pydantic settings 同源）→ settings.database_url；
- target_metadata：app.models.Base.metadata（全部表，见 docs/10 §2）；
- 约定：
  * naming_convention 与模型层一致（约束名确定，autogenerate/check 稳定）；
  * compare_type=True：模型与迁移逐字段比对；
  * compare_server_default=自定义比较器（docs/11 Q-A06）：过滤两类已知噪音
    （PG 反射 JSONB 默认带 ``::jsonb`` 后缀；now()/CURRENT_TIMESTAMP 等价写法），
    其余默认值漂移照常报警——不做整体关闭；
  * render_as_batch=True：SQLite 下 ALTER 走 batch（若单测改跑 alembic 亦兼容）；
  * Java 侧 JPA `ddl-auto=none`，只映射不建表（见 services/java/application.yml）。
"""

from __future__ import annotations

import os
import re
from logging.config import fileConfig

from alembic import context
from app.core.config import get_settings
from app.models import Base
from sqlalchemy import engine_from_config, pool

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()
# 统一用 APP_DATABASE_URL（与 pydantic settings 同源；docs/11 Q-A03）：
# config 层 env_prefix=APP_，compose/.env 注入的必须是 APP_DATABASE_URL，
# 否则 M2 接真引擎时 Python 服务会落到默认 SQLite 而迁移跑在 PG 上（schema 分裂）。
config.set_main_option("sqlalchemy.url", os.environ.get("APP_DATABASE_URL", settings.database_url))

target_metadata = Base.metadata


def _normalize_default(value: str | None) -> str:
    """默认值归一（docs/11 Q-A06）：剥离强转后缀/括号，统一 now()/CURRENT_TIMESTAMP。"""
    if not value:
        return ""
    v = value.strip().strip("()").strip()
    v = re.sub(r"::\w+\s*$", "", v).strip()
    v = v.lower()
    return "now()" if v in {"now()", "current_timestamp"} else v


def _compare_server_default(
    context,  # noqa: ANN001
    metadata_column,  # noqa: ANN001
    metadata_default,  # noqa: ANN001
    rendered_metadata_default,  # noqa: ANN001
    conn_column,  # noqa: ANN001
    conn_default,  # noqa: ANN001
    rendered_conn_default,  # noqa: ANN001
) -> bool:
    """自定义 server_default 比较：过滤已知噪音，其余照常报警（不整体关闭）。"""
    return _normalize_default(rendered_metadata_default) != _normalize_default(
        rendered_conn_default
    )


def run_migrations_offline() -> None:
    """离线模式：不连库，直接生成 SQL（`alembic upgrade head --sql`）。"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=_compare_server_default,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式：连库执行（PG 16，见 docker-compose.yml）。"""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=_compare_server_default,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
