from __future__ import annotations

from logging.config import fileConfig
import importlib.util
import os
from pathlib import Path
import sys

from alembic import context
from sqlalchemy import engine_from_config, pool


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

database_url = os.getenv("DATABASE_URL", "").strip()
if database_url:
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))

from database import Base  # noqa: E402

legacy_model_file = os.getenv("ALEMBIC_LEGACY_MODEL_FILE", "").strip()
if legacy_model_file:
    spec = importlib.util.spec_from_file_location(
        "blue_album_legacy_models",
        legacy_model_file,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load legacy model metadata")
    legacy_models = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(legacy_models)
else:
    import models  # noqa: F401,E402

target_metadata = Base.metadata

RETIRED_WEBSITE_TABLES = {
    "backup_jobs",
    "backup_files",
    "restore_jobs",
    "frp_operation_logs",
}


def include_object(object_, name, type_, reflected, compare_to):
    """Keep retired website tables intact while they remain in old databases."""

    if type_ == "table" and reflected and name in RETIRED_WEBSITE_TABLES:
        return False
    return True


def migration_options() -> dict:
    url = config.get_main_option("sqlalchemy.url")
    return {
        "target_metadata": target_metadata,
        "include_object": include_object,
        "compare_type": True,
        "render_as_batch": url.startswith("sqlite"),
    }


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **migration_options(),
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
        context.configure(connection=connection, **migration_options())
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
