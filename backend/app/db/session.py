from typing import Generator, Tuple, Optional
from urllib.parse import urlparse
import re
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from app.core.config import settings

engine = None
SessionLocal = None


def get_connect_args(url: str | None) -> dict:
    """Configure SSL and socket timeouts for remote database connections such as Supabase."""
    if not url:
        return {}
    try:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        connect_args = {}
        if host not in ("localhost", "127.0.0.1", ""):
            if "pg8000" in url:
                connect_args["ssl_context"] = True
                connect_args["timeout"] = 10  # 10s socket timeout to avoid 'timeout is None' InterfaceError
            elif "sslmode" not in url:
                connect_args["sslmode"] = "require"
                connect_args["connect_timeout"] = 10
        return connect_args
    except Exception:
        return {}


if settings.DATABASE_URL:
    try:
        connect_args = get_connect_args(settings.DATABASE_URL)
        engine = create_engine(
            settings.DATABASE_URL,
            pool_pre_ping=True,
            pool_size=20,
            max_overflow=10,
            pool_timeout=30,
            pool_recycle=300,
            connect_args=connect_args,
            future=True,
        )
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    except Exception:
        # Fallback to prevent startup crash if URL format is invalid
        engine = None
        SessionLocal = None


def sanitize_db_error(error_str: str) -> str:
    """Remove user credentials, tokens, or passwords from error strings before logging or API display."""
    if not error_str:
        return "Unknown database error"
    # Redact :password@ or user.project:password@
    sanitized = re.sub(r":([^:@/]+)@", ":****@", str(error_str))
    # Redact sensitive parameters
    sanitized = re.sub(r"password=[^&\s]+", "password=****", sanitized)
    return sanitized


def verify_db_connection() -> Tuple[bool, Optional[str]]:
    """Actively verify database connectivity by running a test query.
    
    Returns:
        (is_connected, error_message_or_none)
    """
    if engine is None or SessionLocal is None:
        return False, "Database engine not initialized (DATABASE_URL missing or invalid)"
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            return True, None
    except Exception as exc:
        sanitized = sanitize_db_error(str(exc))
        return False, f"Database connectivity check failed: {sanitized}"


def get_db() -> Generator[Session | None, None, None]:
    """Dependency yielding a database session if configured."""
    if SessionLocal is None:
        yield None
        return
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

