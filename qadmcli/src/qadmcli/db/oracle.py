"""Oracle database operations."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Optional

logger = logging.getLogger(__name__)


class OracleError(Exception):
    """Oracle operation error."""

    pass


class OracleConnection:
    """Oracle database connection manager (Thin Mode)."""

    def __init__(self, config: Any):
        self.config = config
        self._connection: Optional[oracledb.Connection] = None

    def connect(self) -> oracledb.Connection:
        """Establish Oracle connection using Thin mode."""
        import oracledb
        try:
            self._connection = oracledb.connect(
                user=self.config.username,
                password=self.config.password,
                host=self.config.host,
                port=self.config.port,
                service_name=self.config.service_name
            )
            logger.info(f"Connected to Oracle: {self.config.host}:{self.config.port}")
            return self._connection
        except Exception as e:
            raise OracleError(f"Failed to connect to Oracle: {e}")

    def disconnect(self):
        """Close connection."""
        if self._connection:
            self._connection.close()
            self._connection = None
            logger.info("Oracle connection closed")

    def is_connected(self) -> bool:
        """Check if connection is active."""
        if not self._connection:
            return False
        try:
            self._connection.ping()
            return True
        except Exception:
            return False

    def __enter__(self) -> "OracleConnection":
        """Context manager entry - connect to database."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - disconnect from database."""
        self.disconnect()
        return False

    @contextmanager
    def get_cursor(self):
        """Get database cursor as context manager."""
        if not self._connection:
            self.connect()

        cursor = self._connection.cursor()
        try:
            yield cursor
        except Exception as e:
            raise OracleError(f"Database operation failed: {e}")
        finally:
            cursor.close()


class OracleSchema:
    """Oracle schema operations."""

    def __init__(self, connection: OracleConnection):
        self.connection = connection

    def table_exists(self, table_name: str, schema: str) -> bool:
        """Check if table exists."""
        with self.connection.get_cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*) FROM ALL_TABLES
                WHERE OWNER = :owner AND TABLE_NAME = :table_name
            """, owner=schema.upper(), table_name=table_name.upper())
            result = cursor.fetchone()
            return result[0] > 0

    def get_columns(self, table_name: str, schema: str) -> list[dict]:
        """Get table column information."""
        with self.connection.get_cursor() as cursor:
            # Query column definition details from ALL_TAB_COLS
            cursor.execute("""
                SELECT
                    COLUMN_NAME,
                    DATA_TYPE,
                    DATA_LENGTH,
                    DATA_PRECISION,
                    DATA_SCALE,
                    NULLABLE,
                    DATA_DEFAULT,
                    IDENTITY_COLUMN
                FROM ALL_TAB_COLS
                WHERE OWNER = :owner AND TABLE_NAME = :table_name
                ORDER BY COLUMN_ID
            """, owner=schema.upper(), table_name=table_name.upper())

            columns = []
            for row in cursor.fetchall():
                col_info = {
                    "name": row[0],
                    "type": row[1].upper(),
                    "length": row[2],
                    "precision": row[3],
                    "scale": row[4],
                    "nullable": row[5] == "Y",
                    "default": str(row[6]).strip() if row[6] is not None else None,
                    "identity": row[7] == "YES" if len(row) > 7 else False,
                }
                columns.append(col_info)

            return columns

    def get_primary_key(self, table_name: str, schema: str) -> Optional[list[str]]:
        """Get primary key columns."""
        with self.connection.get_cursor() as cursor:
            cursor.execute("""
                SELECT cols.column_name
                FROM all_constraints cons
                JOIN all_cons_columns cols
                  ON cons.constraint_name = cols.constraint_name
                  AND cons.owner = cols.owner
                WHERE cons.constraint_type = 'P'
                  AND cons.owner = :owner
                  AND cons.table_name = :table_name
                ORDER BY cols.position
            """, owner=schema.upper(), table_name=table_name.upper())

            result = cursor.fetchall()
            if result:
                return [row[0] for row in result]
            return None

    def get_row_count(self, table_name: str, schema: str) -> int:
        """Get table row count."""
        with self.connection.get_cursor() as cursor:
            cursor.execute(f'SELECT COUNT(*) FROM "{schema.upper()}"."{table_name.upper()}"')
            result = cursor.fetchone()
            return result[0]


class OracleManager:
    """High-level Oracle operations."""

    def __init__(self, connection: OracleConnection):
        self.connection = connection
        self.schema = OracleSchema(connection)

    def test_connection(self) -> dict:
        """Test connection and return server info."""
        try:
            with self.connection.get_cursor() as cursor:
                cursor.execute("SELECT version FROM product_component_version WHERE product LIKE '%Database%'")
                row = cursor.fetchone()
                version = row[0] if row else "Unknown"
                
                cursor.execute("SELECT sys_context('USERENV', 'DB_NAME') FROM dual")
                db_row = cursor.fetchone()
                db_name = db_row[0] if db_row else "Unknown"
                
                return {
                    "connected": True,
                    "version": version,
                    "database": db_name,
                    "server": self.connection.config.host,
                }
        except Exception as e:
            return {
                "connected": False,
                "error": str(e),
            }
