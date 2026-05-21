from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from backend.core.config import get_settings
from backend.database.models import ArcProgress, CanonEntry, Character, LoreFact, MagicRule, Project, Relationship, Scene, TimelineEvent, User
from backend.database.session import Base


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)


# Ensure model imports are retained for Alembic metadata discovery.
_ = (User, Project, Character, Scene, LoreFact, TimelineEvent, Relationship, CanonEntry, MagicRule, ArcProgress)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()