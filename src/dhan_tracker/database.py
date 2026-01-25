"""Database module for storing API keys and tokens."""

import logging
import os
from datetime import datetime
from typing import Optional
from contextlib import contextmanager

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False

logger = logging.getLogger(__name__)

# Table creation SQL
CREATE_API_KEYS_TABLE = """
CREATE TABLE IF NOT EXISTS api_keys (
    id SERIAL PRIMARY KEY,
    key_name VARCHAR(100) UNIQUE NOT NULL,
    key_value TEXT NOT NULL,
    client_id VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    metadata JSONB
);

CREATE INDEX IF NOT EXISTS idx_api_keys_key_name ON api_keys(key_name);
"""


def get_connection_string() -> Optional[str]:
    """Get PostgreSQL connection string from environment."""
    return os.getenv("PG_DB_CONNECTION_STRING")


def is_database_available() -> bool:
    """Check if database is configured and available."""
    if not HAS_PSYCOPG2:
        logger.warning("psycopg2 not installed - database features disabled")
        return False

    conn_str = get_connection_string()
    if not conn_str:
        logger.debug("PG_DB_CONNECTION_STRING not set - using env vars only")
        return False

    return True


@contextmanager
def get_db_connection():
    """Get a database connection context manager."""
    if not HAS_PSYCOPG2:
        raise RuntimeError("psycopg2 is not installed")

    conn_str = get_connection_string()
    if not conn_str:
        raise RuntimeError("PG_DB_CONNECTION_STRING not configured")

    conn = psycopg2.connect(conn_str)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_database() -> bool:
    """Initialize the database schema. Creates tables if they don't exist."""
    if not is_database_available():
        return False

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(CREATE_API_KEYS_TABLE)
        logger.info("Database initialized successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        return False


def get_api_key(key_name: str) -> Optional[dict]:
    """
    Get an API key from the database.

    Args:
        key_name: The name/identifier of the key (e.g., 'dhan_access_token')

    Returns:
        Dict with key details or None if not found
    """
    if not is_database_available():
        return None

    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM api_keys WHERE key_name = %s",
                    (key_name,)
                )
                row = cur.fetchone()
                return dict(row) if row else None
    except Exception as e:
        logger.error(f"Failed to get API key '{key_name}': {e}")
        return None


def save_api_key(
    key_name: str,
    key_value: str,
    client_id: Optional[str] = None,
    expires_at: Optional[datetime] = None,
    metadata: Optional[dict] = None
) -> bool:
    """
    Save or update an API key in the database.

    Args:
        key_name: The name/identifier of the key
        key_value: The actual key/token value
        client_id: Optional client ID associated with the key
        expires_at: Optional expiration timestamp
        metadata: Optional additional metadata as JSON

    Returns:
        True if saved successfully, False otherwise
    """
    if not is_database_available():
        return False

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Use upsert (INSERT ... ON CONFLICT UPDATE)
                cur.execute("""
                    INSERT INTO api_keys (key_name, key_value, client_id, expires_at, metadata, updated_at)
                    VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (key_name) 
                    DO UPDATE SET 
                        key_value = EXCLUDED.key_value,
                        client_id = EXCLUDED.client_id,
                        expires_at = EXCLUDED.expires_at,
                        metadata = EXCLUDED.metadata,
                        updated_at = CURRENT_TIMESTAMP
                """, (key_name, key_value, client_id, expires_at,
                      psycopg2.extras.Json(metadata) if metadata else None))

        logger.info(f"API key '{key_name}' saved successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to save API key '{key_name}': {e}")
        return False


def delete_api_key(key_name: str) -> bool:
    """
    Delete an API key from the database.

    Args:
        key_name: The name/identifier of the key to delete

    Returns:
        True if deleted, False otherwise
    """
    if not is_database_available():
        return False

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM api_keys WHERE key_name = %s",
                    (key_name,)
                )
                deleted = cur.rowcount > 0

        if deleted:
            logger.info(f"API key '{key_name}' deleted")
        return deleted
    except Exception as e:
        logger.error(f"Failed to delete API key '{key_name}': {e}")
        return False


# ==================== Dhan-specific helpers ====================

DHAN_TOKEN_KEY = "dhan_access_token"


def get_dhan_token() -> Optional[str]:
    """
    Get the Dhan access token from the database.

    Returns:
        The access token string or None if not found
    """
    key_data = get_api_key(DHAN_TOKEN_KEY)
    if key_data:
        return key_data.get("key_value")
    return None


def save_dhan_token(
    access_token: str,
    client_id: str,
    expires_at: Optional[datetime] = None
) -> bool:
    """
    Save the Dhan access token to the database.

    Args:
        access_token: The new access token
        client_id: The Dhan client ID
        expires_at: When the token expires (typically 24 hours from now)

    Returns:
        True if saved successfully
    """
    return save_api_key(
        key_name=DHAN_TOKEN_KEY,
        key_value=access_token,
        client_id=client_id,
        expires_at=expires_at,
        metadata={"source": "refresh",
                  "refreshed_at": datetime.utcnow().isoformat()}
    )


def get_dhan_token_info() -> Optional[dict]:
    """
    Get full information about the stored Dhan token.

    Returns:
        Dict with token details including expiry, or None
    """
    return get_api_key(DHAN_TOKEN_KEY)
