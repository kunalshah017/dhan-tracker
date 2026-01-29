"""Database module for storing API keys, tokens, and order triggers."""

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

# Order triggers tracking table
CREATE_ORDER_TRIGGERS_TABLE = """
CREATE TABLE IF NOT EXISTS order_triggers (
    id SERIAL PRIMARY KEY,
    order_id VARCHAR(100) NOT NULL,
    trading_symbol VARCHAR(50) NOT NULL,
    isin VARCHAR(20),
    security_id VARCHAR(50),
    transaction_type VARCHAR(10) NOT NULL,
    quantity INTEGER NOT NULL,
    trigger_price DECIMAL(12, 2) NOT NULL,
    executed_price DECIMAL(12, 2),
    order_type VARCHAR(30),
    order_status VARCHAR(30) NOT NULL,
    trigger_type VARCHAR(30) DEFAULT 'STOP_LOSS',
    cost_price DECIMAL(12, 2),
    pnl_amount DECIMAL(12, 2),
    pnl_percent DECIMAL(8, 4),
    protection_tier VARCHAR(50),
    triggered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    email_sent BOOLEAN DEFAULT FALSE,
    email_sent_at TIMESTAMP,
    metadata JSONB
);

CREATE INDEX IF NOT EXISTS idx_order_triggers_order_id ON order_triggers(order_id);
CREATE INDEX IF NOT EXISTS idx_order_triggers_symbol ON order_triggers(trading_symbol);
CREATE INDEX IF NOT EXISTS idx_order_triggers_triggered_at ON order_triggers(triggered_at);
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
                cur.execute(CREATE_ORDER_TRIGGERS_TABLE)
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


# ==================== Order Triggers tracking ====================

def save_order_trigger(
    order_id: str,
    trading_symbol: str,
    transaction_type: str,
    quantity: int,
    trigger_price: float,
    order_status: str,
    isin: Optional[str] = None,
    security_id: Optional[str] = None,
    executed_price: Optional[float] = None,
    order_type: str = "STOP_LOSS_MARKET",
    trigger_type: str = "STOP_LOSS",
    cost_price: Optional[float] = None,
    pnl_amount: Optional[float] = None,
    pnl_percent: Optional[float] = None,
    protection_tier: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> bool:
    """
    Save an order trigger event to the database.

    Args:
        order_id: Dhan order ID
        trading_symbol: Stock/ETF symbol
        transaction_type: SELL (for SL triggers)
        quantity: Number of units
        trigger_price: SL trigger price
        order_status: TRADED, REJECTED, etc.
        isin: ISIN code
        security_id: Dhan security ID
        executed_price: Actual execution price
        order_type: STOP_LOSS, STOP_LOSS_MARKET
        trigger_type: STOP_LOSS, TRAILING_SL, etc.
        cost_price: Original cost price
        pnl_amount: P&L in rupees
        pnl_percent: P&L percentage
        protection_tier: Which protection tier triggered
        metadata: Additional JSON data

    Returns:
        True if saved successfully
    """
    if not is_database_available():
        logger.warning("Database not available - trigger not saved")
        return False

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO order_triggers (
                        order_id, trading_symbol, isin, security_id,
                        transaction_type, quantity, trigger_price, executed_price,
                        order_type, order_status, trigger_type,
                        cost_price, pnl_amount, pnl_percent, protection_tier,
                        metadata
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    order_id, trading_symbol, isin, security_id,
                    transaction_type, quantity, trigger_price, executed_price,
                    order_type, order_status, trigger_type,
                    cost_price, pnl_amount, pnl_percent, protection_tier,
                    psycopg2.extras.Json(metadata) if metadata else None,
                ))

        logger.info(
            f"Order trigger saved: {trading_symbol} @ ₹{trigger_price}")
        return True
    except Exception as e:
        logger.error(f"Failed to save order trigger: {e}")
        return False


def get_order_triggers(
    limit: int = 50,
    symbol: Optional[str] = None,
    days: Optional[int] = None,
) -> list[dict]:
    """
    Get order trigger history from the database.

    Args:
        limit: Maximum number of records to return
        symbol: Filter by trading symbol
        days: Filter to last N days

    Returns:
        List of trigger records
    """
    if not is_database_available():
        return []

    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = "SELECT * FROM order_triggers WHERE 1=1"
                params = []

                if symbol:
                    query += " AND trading_symbol = %s"
                    params.append(symbol)

                if days:
                    query += " AND triggered_at >= CURRENT_TIMESTAMP - INTERVAL '%s days'"
                    params.append(days)

                query += " ORDER BY triggered_at DESC LIMIT %s"
                params.append(limit)

                cur.execute(query, params)
                rows = cur.fetchall()
                return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Failed to get order triggers: {e}")
        return []


def mark_trigger_email_sent(order_id: str) -> bool:
    """
    Mark an order trigger as having email notification sent.

    Args:
        order_id: The order ID to update

    Returns:
        True if updated successfully
    """
    if not is_database_available():
        return False

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE order_triggers 
                    SET email_sent = TRUE, email_sent_at = CURRENT_TIMESTAMP
                    WHERE order_id = %s
                """, (order_id,))
                return cur.rowcount > 0
    except Exception as e:
        logger.error(f"Failed to mark email sent for {order_id}: {e}")
        return False


def get_pending_email_triggers() -> list[dict]:
    """
    Get order triggers that need email notifications.

    Returns:
        List of triggers where email_sent = FALSE
    """
    if not is_database_available():
        return []

    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM order_triggers 
                    WHERE email_sent = FALSE
                    ORDER BY triggered_at DESC
                """)
                rows = cur.fetchall()
                return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Failed to get pending email triggers: {e}")
        return []
