"""Alembic 迁移环境 —— 唯一 schema 真源（docs/06 第 10 章）。

- 连接串：环境变量 DATABASE_URL（Pydantic Settings 同源）
- Java 侧 JPA `ddl-auto=none`，只映射不建表
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from app.core.config import get_settings
from sqlalchemy import engine_from_config, pool

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()
config.set_main_option("sqlalchemy.url", os.environ.get("DATABASE_URL", settings.database_url))

target_metadata = None  # M2 起挂 Base.metadata（app/models/）


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
