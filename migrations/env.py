from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, inspect, pool, text

from finsight.core.config import get_settings
from finsight.infrastructure.database.base import Base
from finsight.infrastructure.database import models  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)
config.set_main_option("sqlalchemy.url", get_settings().database_url.replace("%", "%%"))
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
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
        if connection.dialect.name == "postgresql":
            version_table = inspect(connection)
            if not version_table.has_table("alembic_version"):
                connection.execute(text(
                    "CREATE TABLE alembic_version (version_num VARCHAR(64) NOT NULL, "
                    "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"
                ))
                connection.commit()
            else:
                version_column = next(
                    column for column in version_table.get_columns("alembic_version")
                    if column["name"] == "version_num"
                )
                version_length = getattr(version_column["type"], "length", None)
                if version_length is not None and version_length < 64:
                    connection.execute(text(
                        "ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(64)"
                    ))
                    connection.commit()
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
