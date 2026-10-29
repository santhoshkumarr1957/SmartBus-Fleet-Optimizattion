import os
import sys
from logging.config import fileConfig
from urllib.parse import urlparse

from sqlalchemy import create_engine, engine_from_config, pool

from alembic import context

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Ensure pure Python mode for SQLAlchemy if needed
os.environ.setdefault("DISABLE_SQLALCHEMY_CEXT", "1")

from app.core.config import settings
from app.db.base import Base

# Import all models so Base.metadata knows about them
import app.models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Dynamically set DB URL from environment settings if defined.
# Escape '%' as '%%' so ConfigParser interpolation doesn't choke on percent-encoded characters (such as %40).
if settings.DATABASE_URL:
    config.set_main_option("sqlalchemy.url", settings.DATABASE_URL.replace("%", "%%"))

target_metadata = Base.metadata


def get_connect_args(url: str | None) -> dict:
    """Build connection args ensuring SSL for remote hosts like Supabase."""
    if not url:
        return {}
    try:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        connect_args = {}
        if host not in ("localhost", "127.0.0.1", ""):
            if "pg8000" in url:
                connect_args["ssl_context"] = True
                connect_args["timeout"] = 10
            elif "sslmode" not in url:
                connect_args["sslmode"] = "require"
                connect_args["connect_timeout"] = 10
        return connect_args
    except Exception:
        return {}


def run_migrations_offline() -> None:
    url = settings.DATABASE_URL or config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    db_url = settings.DATABASE_URL or config.get_main_option("sqlalchemy.url")
    connect_args = get_connect_args(db_url)

    if settings.DATABASE_URL:
        connectable = create_engine(
            settings.DATABASE_URL,
            poolclass=pool.NullPool,
            connect_args=connect_args,
        )
    else:
        configuration = config.get_section(config.config_ini_section, {})
        connectable = engine_from_config(
            configuration,
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
            connect_args=connect_args,
        )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
