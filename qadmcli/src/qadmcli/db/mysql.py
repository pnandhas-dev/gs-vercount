"""MySQL database operations."""

import logging
from contextlib import contextmanager
from typing import Any, Optional

import pymysql

logger = logging.getLogger(__name__)


class MySQLError(Exception):
    """MySQL operation error."""

    pass


class MySQLConnection:
    """MySQL database connection manager."""

    def __init__(self, config: Any):
        self.config = config
        self._connection: Optional[pymysql.Connection] = None

    def connect(self) -> pymysql.Connection:
        """Establish MySQL connection."""
        try:
            self._connection = pymysql.connect(
                host=self.config.host,
                port=self.config.port,
                user=self.config.username,
                password=self.config.password,
                database=self.config.database,
                connect_timeout=10,
                autocommit=True
            )
            logger.info(f"Connected to MySQL: {self.config.host}:{self.config.port}")
            return self._connection
        except Exception as e:
            raise MySQLError(f"Failed to connect to MySQL: {e}")

    def disconnect(self):
        """Close connection."""
        if self._connection:
            self._connection.close()
            self._connection = None
            logger.info("MySQL connection closed")

    def is_connected(self) -> bool:
        """Check if connection is active."""
        if not self._connection:
            return False
        try:
            self._connection.ping(reconnect=True)
            return True
        except Exception:
            return False

    def __enter__(self) -> "MySQLConnection":
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
            raise MySQLError(f"Database operation failed: {e}")
        finally:
            cursor.close()


class MySQLSchema:
    """MySQL schema operations."""

    def __init__(self, connection: MySQLConnection):
        self.connection = connection

    def table_exists(self, table_name: str, schema: str) -> bool:
        """Check if table exists."""
        with self.connection.get_cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
            """, (schema, table_name))
            result = cursor.fetchone()
            return result[0] > 0

    def get_columns(self, table_name: str, schema: str) -> list[dict]:
        """Get table column information."""
        with self.connection.get_cursor() as cursor:
            cursor.execute("""
                SELECT
                    COLUMN_NAME,
                    DATA_TYPE,
                    CHARACTER_MAXIMUM_LENGTH,
                    NUMERIC_PRECISION,
                    NUMERIC_SCALE,
                    IS_NULLABLE,
                    COLUMN_DEFAULT,
                    EXTRA
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
                ORDER BY ORDINAL_POSITION
            """, (schema, table_name))

            columns = []
            for row in cursor.fetchall():
                col_info = {
                    "name": row[0],
                    "type": row[1].upper(),
                    "length": row[2],
                    "precision": row[3],
                    "scale": row[4],
                    "nullable": row[5] == "YES",
                    "default": row[6],
                    "identity": "auto_increment" in str(row[7]).lower(),
                }
                columns.append(col_info)

            return columns

    def get_primary_key(self, table_name: str, schema: str) -> Optional[list[str]]:
        """Get primary key columns."""
        with self.connection.get_cursor() as cursor:
            cursor.execute("""
                SELECT COLUMN_NAME
                FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
                WHERE CONSTRAINT_NAME = 'PRIMARY'
                    AND TABLE_SCHEMA = %s
                    AND TABLE_NAME = %s
                ORDER BY ORDINAL_POSITION
            """, (schema, table_name))

            result = cursor.fetchall()
            if result:
                return [row[0] for row in result]
            return None

    def get_row_count(self, table_name: str, schema: str) -> int:
        """Get table row count."""
        with self.connection.get_cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) FROM `{schema}`.`{table_name}`")
            result = cursor.fetchone()
            return result[0]


class MySQLManager:
    """High-level MySQL operations."""

    def __init__(self, connection: MySQLConnection):
        self.connection = connection
        self.schema = MySQLSchema(connection)

    def test_connection(self) -> dict:
        """Test connection and return server info."""
        try:
            with self.connection.get_cursor() as cursor:
                cursor.execute("SELECT VERSION(), DATABASE()")
                row = cursor.fetchone()
                return {
                    "connected": True,
                    "version": row[0],
                    "database": row[1],
                    "server": self.connection.config.host,
                }
        except Exception as e:
            return {
                "connected": False,
                "error": str(e),
            }
