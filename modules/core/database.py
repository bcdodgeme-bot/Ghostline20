"""
Database connection manager for Syntax Prime V2.
Handles async PostgreSQL connections with pooling.
"""

import asyncpg
from typing import Optional
from config.settings import settings

#-- Section 1: Database Manager Class - 9/23/25
class DatabaseManager:
    """Manages database connection pool and operations."""
    
    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None
    
    async def connect(self) -> None:
        """Initialize database connection pool."""
        if self.pool is None:
            self.pool = await asyncpg.create_pool(
                settings.database_url,
                min_size=2,
                max_size=10,
                command_timeout=60
            )

#-- Section 2: Connection Management - 9/23/25    
    async def disconnect(self) -> None:
        """Close database connection pool."""
        if self.pool:
            await self.pool.close()
            self.pool = None
    
    async def get_connection(self) -> asyncpg.Connection:
        """Get database connection from pool."""
        if not self.pool:
            await self.connect()
        return await self.pool.acquire()
    
    async def release_connection(self, conn: asyncpg.Connection) -> None:
        """Release connection back to pool."""
        if self.pool:
            await self.pool.release(conn)

#-- Section 3: Query Execution Interface - 9/23/25
#-- Section 3: Query Execution Interface - 9/23/25
    async def execute_query(self, query: str, *args) -> list:
        """Execute query and return results."""
        conn = await self.get_connection()
        try:
            return await conn.fetch(query, *args)
        finally:
            await self.release_connection(conn)
    
    async def fetch_one(self, query: str, *args):
        """Fetch single row from query."""
        conn = await self.get_connection()
        try:
            return await conn.fetchrow(query, *args)
        finally:
            await self.release_connection(conn)
    
    async def fetch_all(self, query: str, *args):
        """Fetch all rows from query."""
        conn = await self.get_connection()
        try:
            return await conn.fetch(query, *args)
        finally:
            await self.release_connection(conn)
    
    async def execute(self, query: str, *args):
        """Execute query without returning results."""
        conn = await self.get_connection()
        try:
            return await conn.execute(query, *args)
        finally:
            await self.release_connection(conn)

#-- Section 4: Global Instance - 9/23/25
# Global database manager instance
db_manager = DatabaseManager()
