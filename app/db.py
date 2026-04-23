"""
Database connection pool using asyncpg + SQLAlchemy async engine.
"""
import os
from typing import AsyncGenerator

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text

log = structlog.get_logger()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://si_user:si_pass@localhost:5432/store_intelligence",
)

# Convert postgres:// → postgresql+asyncpg://
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)

_is_sqlite = DATABASE_URL.startswith("sqlite")
_engine_kwargs: dict = {"echo": False, "pool_pre_ping": not _is_sqlite}
if not _is_sqlite:
    _engine_kwargs["pool_size"] = 10
    _engine_kwargs["max_overflow"] = 20

engine = create_async_engine(DATABASE_URL, **_engine_kwargs)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


class Base(DeclarativeBase):
    pass


_SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id    TEXT    NOT NULL UNIQUE,
    store_id    TEXT    NOT NULL,
    camera_id   TEXT    NOT NULL DEFAULT '',
    visitor_id  TEXT    NOT NULL,
    event_type  TEXT    NOT NULL,
    timestamp   TEXT    NOT NULL,
    zone_id     TEXT,
    dwell_ms    INTEGER NOT NULL DEFAULT 0,
    is_staff    INTEGER NOT NULL DEFAULT 0,
    confidence  REAL    NOT NULL DEFAULT 1.0,
    queue_depth INTEGER,
    sku_zone    TEXT,
    session_seq INTEGER,
    raw_payload TEXT    NOT NULL DEFAULT '{}',
    ingested_at TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS visitor_sessions (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id     TEXT    NOT NULL DEFAULT (lower(hex(randomblob(16)))),
    store_id       TEXT    NOT NULL,
    visitor_id     TEXT    NOT NULL,
    entry_time     TEXT,
    exit_time      TEXT,
    is_converted   INTEGER NOT NULL DEFAULT 0,
    transaction_id TEXT,
    zones_visited  TEXT,
    was_in_billing INTEGER NOT NULL DEFAULT 0,
    reentry_count  INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at     TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS pos_transactions (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    store_id       TEXT    NOT NULL,
    transaction_id TEXT    NOT NULL UNIQUE,
    timestamp      TEXT    NOT NULL,
    basket_value   REAL,
    matched_session TEXT
);
CREATE TABLE IF NOT EXISTS anomalies (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    anomaly_id       TEXT    NOT NULL DEFAULT (lower(hex(randomblob(16)))),
    store_id         TEXT    NOT NULL,
    anomaly_type     TEXT    NOT NULL,
    severity         TEXT    NOT NULL,
    detected_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    resolved_at      TEXT,
    description      TEXT,
    suggested_action TEXT,
    metadata         TEXT
);
"""


async def init_db() -> None:
    """Verify DB connectivity on startup. For SQLite, also create tables."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        log.info("database_connected", url=DATABASE_URL.split("@")[-1])
        if _is_sqlite:
            async with engine.begin() as conn:
                for stmt in _SQLITE_SCHEMA.strip().split(";"):
                    stmt = stmt.strip()
                    if stmt:
                        await conn.execute(text(stmt))
            log.info("sqlite_tables_ready")
    except Exception as exc:
        log.error("database_connection_failed", error=str(exc))
        raise


async def close_db() -> None:
    await engine.dispose()
    log.info("database_pool_closed")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yields an async DB session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def check_db_health() -> bool:
    """Returns True if DB is reachable."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
