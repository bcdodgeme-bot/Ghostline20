# modules/core/database.py
"""
Database connection manager for Syntax Prime V2.
Handles async PostgreSQL connections with pooling, retry logic, and transactions.

This is the FOUNDATION module - all other modules should import from here:
    from modules.core.database import get_db_manager
    
    db = await get_db_manager()
    result = await db.fetch_one("SELECT * FROM table WHERE id = $1", some_id)

Updated: 2025 - Added retry logic for transient failures, transaction context manager
Updated: Session 19 - Added __all__ exports, get_db_manager() getter
"""

import asyncio
import asyncpg
import logging
from contextlib import asynccontextmanager
from typing import Optional, List, Any

from config.settings import settings

logger = logging.getLogger(__name__)

__all__ = [
    'DatabaseManager',
    'db_manager',
    'get_db_manager',
]

# Retry configuration
MAX_RETRIES = 3
RETRY_DELAY_BASE = 0.1  # Base delay in seconds (exponential backoff)

# Transient errors that should trigger retry
TRANSIENT_ERRORS = (
    asyncpg.PostgresConnectionError,
    asyncpg.InterfaceError,
    asyncpg.InternalClientError,
    ConnectionResetError,
    ConnectionRefusedError,
    TimeoutError,
)


class DatabaseManager:
    """
    Manages database connection pool and operations.
    
    This is a singleton - use get_db_manager() to access.
    Never create direct asyncpg connections; always use this manager.
    """
    
    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None
        self._connecting: bool = False
    
    async def connect(self) -> None:
        """Initialize database connection pool."""
        if self.pool is not None:
            return
            
        # Prevent multiple simultaneous connection attempts
        if self._connecting:
            # Wait for existing connection attempt
            while self._connecting:
                await asyncio.sleep(0.1)
            return
        
        self._connecting = True
        try:
            self.pool = await asyncpg.create_pool(
                settings.database_url,
                min_size=2,
                max_size=10,
                command_timeout=60
            )
            logger.info("✅ Database connection pool established")
        except Exception as e:
            logger.error(f"❌ Failed to create database pool: {e}")
            raise
        finally:
            self._connecting = False

    async def disconnect(self) -> None:
        """Close database connection pool."""
        if self.pool:
            await self.pool.close()
            self.pool = None
            logger.info("🔌 Database connection pool closed")
    
    async def get_connection(self) -> asyncpg.Connection:
        """Get database connection from pool."""
        if not self.pool:
            await self.connect()
        return await self.pool.acquire()
    
    async def release_connection(self, conn: asyncpg.Connection) -> None:
        """Release connection back to pool."""
        if self.pool:
            await self.pool.release(conn)

    # =========================================================================
    # Query Execution with Retry Logic
    # =========================================================================
    
    async def _execute_with_retry(
        self,
        operation: str,
        query: str,
        args: tuple,
        fetch_method: str
    ) -> Any:
        """
        Execute a database operation with automatic retry on transient failures.
        
        Args:
            operation: Description for logging (e.g., "fetch_one", "execute")
            query: SQL query string
            args: Query parameters
            fetch_method: Method to call on connection ("fetch", "fetchrow", "execute")
        
        Returns:
            Query results
        """
        last_error = None
        
        for attempt in range(MAX_RETRIES):
            conn = None
            try:
                conn = await self.get_connection()
                
                if fetch_method == "fetch":
                    result = await conn.fetch(query, *args)
                elif fetch_method == "fetchrow":
                    result = await conn.fetchrow(query, *args)
                elif fetch_method == "execute":
                    result = await conn.execute(query, *args)
                else:
                    raise ValueError(f"Unknown fetch method: {fetch_method}")
                
                return result
                
            except TRANSIENT_ERRORS as e:
                last_error = e
                
                if attempt < MAX_RETRIES - 1:
                    delay = RETRY_DELAY_BASE * (2 ** attempt)  # Exponential backoff
                    logger.warning(
                        f"⚠️ Database {operation} failed (attempt {attempt + 1}/{MAX_RETRIES}), "
                        f"retrying in {delay:.2f}s: {e}"
                    )
                    await asyncio.sleep(delay)
                    
                    # Reset pool on connection errors
                    if isinstance(e, (asyncpg.PostgresConnectionError, ConnectionResetError)):
                        await self._reset_pool()
                else:
                    logger.error(f"❌ Database {operation} failed after {MAX_RETRIES} attempts: {e}")
                    
            except Exception as e:
                # Non-transient error - don't retry
                logger.error(f"❌ Database {operation} error: {e}")
                raise
                
            finally:
                if conn:
                    await self.release_connection(conn)
        
        # All retries exhausted
        raise last_error
    
    async def _reset_pool(self) -> None:
        """Reset the connection pool after connection failures."""
        logger.info("🔄 Resetting database connection pool...")
        try:
            if self.pool:
                await self.pool.close()
                self.pool = None
            await self.connect()
        except Exception as e:
            logger.error(f"❌ Failed to reset pool: {e}")

    async def fetch_one(self, query: str, *args) -> Optional[asyncpg.Record]:
        """Fetch single row from query."""
        return await self._execute_with_retry("fetch_one", query, args, "fetchrow")
    
    async def fetch_all(self, query: str, *args) -> List[asyncpg.Record]:
        """Fetch all rows from query."""
        return await self._execute_with_retry("fetch_all", query, args, "fetch")
    
    async def execute(self, query: str, *args) -> str:
        """Execute query without returning results."""
        return await self._execute_with_retry("execute", query, args, "execute")
    
    async def execute_query(self, query: str, *args) -> List[asyncpg.Record]:
        """
        Execute query and return results.
        
        Note: This is an alias for fetch_all() for backwards compatibility.
        Prefer using fetch_all() for clarity.
        """
        return await self.fetch_all(query, *args)

    # =========================================================================
    # Transaction Support
    # =========================================================================
    
    @asynccontextmanager
    async def transaction(self):
        """
        Context manager for database transactions.
        
        Usage:
            async with db_manager.transaction() as conn:
                await conn.execute("INSERT INTO table1 ...")
                await conn.execute("INSERT INTO table2 ...")
                # Both succeed or both rollback on error
        
        Features:
            - Automatic commit on success
            - Automatic rollback on exception
            - Connection is properly released after use
        """
        conn = await self.get_connection()
        tx = conn.transaction()
        
        try:
            await tx.start()
            logger.debug("🔒 Transaction started")
            yield conn
            await tx.commit()
            logger.debug("✅ Transaction committed")
            
        except Exception as e:
            await tx.rollback()
            logger.warning(f"↩️ Transaction rolled back: {e}")
            raise
            
        finally:
            await self.release_connection(conn)
    
    @asynccontextmanager
    async def transaction_with_retry(self, max_retries: int = MAX_RETRIES):
        """
        Transaction context manager with retry logic for transient failures.
        
        Use this for critical operations that should retry on connection issues.
        Note: Only retries on connection errors, not on constraint violations etc.
        
        Usage:
            async with db_manager.transaction_with_retry() as conn:
                await conn.execute("INSERT INTO table1 ...")
                await conn.execute("INSERT INTO table2 ...")
        """
        last_error = None
        
        for attempt in range(max_retries):
            try:
                async with self.transaction() as conn:
                    yield conn
                    return  # Success - exit retry loop
                    
            except TRANSIENT_ERRORS as e:
                last_error = e
                
                if attempt < max_retries - 1:
                    delay = RETRY_DELAY_BASE * (2 ** attempt)
                    logger.warning(
                        f"⚠️ Transaction failed (attempt {attempt + 1}/{max_retries}), "
                        f"retrying in {delay:.2f}s: {e}"
                    )
                    await asyncio.sleep(delay)
                    await self._reset_pool()
                else:
                    logger.error(f"❌ Transaction failed after {max_retries} attempts: {e}")
                    raise
                    
            except Exception:
                # Non-transient error - don't retry
                raise
        
        if last_error:
            raise last_error

    # =========================================================================
    # Health Check
    # =========================================================================
    
    async def health_check(self) -> dict:
        """
        Check database connectivity and pool status.
        
        Returns:
            dict with status, pool_size, and any error info
        """
        try:
            result = await self.fetch_one("SELECT 1 as ok, NOW() as server_time")
            
            pool_info = {}
            if self.pool:
                pool_info = {
                    "pool_size": self.pool.get_size(),
                    "pool_free": self.pool.get_idle_size(),
                    "pool_used": self.pool.get_size() - self.pool.get_idle_size(),
                    "pool_min": self.pool.get_min_size(),
                    "pool_max": self.pool.get_max_size(),
                }
            
            return {
                "status": "healthy",
                "connected": True,
                "server_time": result["server_time"].isoformat() if result else None,
                **pool_info
            }
            
        except Exception as e:
            logger.error(f"❌ Database health check failed: {e}")
            return {
                "status": "unhealthy",
                "connected": False,
                "error": str(e)
            }


# =============================================================================
# Global Instance & Getter
# =============================================================================

# Global database manager instance
db_manager = DatabaseManager()


async def get_db_manager() -> DatabaseManager:
    """
    Get the singleton database manager instance, ensuring it's connected.
    
    This is the preferred way to access the database manager:
        db = await get_db_manager()
        result = await db.fetch_one("SELECT * FROM users WHERE id = $1", user_id)
    
    Returns:
        DatabaseManager: The connected singleton instance
    """
    if not db_manager.pool:
        await db_manager.connect()
    return db_manager
