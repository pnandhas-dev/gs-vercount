"""MSSQL database operations."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Optional

from ..models.connection import ConnectionConfig

logger = logging.getLogger(__name__)


class MSSQLError(Exception):
    """MSSQL operation error."""

    pass


class MSSQLConnection:
    """MSSQL database connection manager."""

    def __init__(self, config: ConnectionConfig):
        self.config = config
        self._connection: Optional[pyodbc.Connection] = None

    def connect(self) -> pyodbc.Connection:
        """Establish MSSQL connection."""
        import pyodbc
        try:
            conn_str = self._build_connection_string()
            self._connection = pyodbc.connect(conn_str, timeout=30)
            logger.info(f"Connected to MSSQL: {self.config.host}:{self.config.port}")
            return self._connection
        except pyodbc.Error as e:
            raise MSSQLError(f"Failed to connect to MSSQL: {e}")

    def _build_connection_string(self) -> str:
        """Build ODBC connection string."""
        return self.build_connection_string()
    
    def build_connection_string(self) -> str:
        """Build ODBC connection string (public method)."""
        import pyodbc
        # Try ODBC Driver 18 first (newer), fallback to 17
        drivers = ["ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server"]
        available_drivers = pyodbc.drivers()
        
        selected_driver = None
        for driver in drivers:
            if any(driver in d for d in available_drivers):
                selected_driver = driver
                break
        
        if not selected_driver:
            # Use first available SQL Server driver
            for d in available_drivers:
                if "SQL Server" in d:
                    selected_driver = d
                    break
        
        if not selected_driver:
            selected_driver = "ODBC Driver 18 for SQL Server"  # Default
        
        parts = [
            f"DRIVER={{{selected_driver}}}",
            f"SERVER={self.config.host},{self.config.port}",
            f"DATABASE={self.config.database}",
            f"UID={self.config.username}",
            f"PWD={self.config.password}",
            "TrustServerCertificate=yes",
            "Encrypt=no",
        ]
        return ";".join(parts)

    def disconnect(self):
        """Close connection."""
        if self._connection:
            self._connection.close()
            self._connection = None
            logger.info("MSSQL connection closed")

    def is_connected(self) -> bool:
        """Check if connection is active."""
        if not self._connection:
            return False
        try:
            cursor = self._connection.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            return True
        except pyodbc.Error:
            return False

    def __enter__(self) -> "MSSQLConnection":
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
            self._connection.commit()
        except Exception as e:
            self._connection.rollback()
            raise MSSQLError(f"Database operation failed: {e}")
        finally:
            cursor.close()


class MSSQLSchema:
    """MSSQL schema operations."""

    def __init__(self, connection: MSSQLConnection):
        self.connection = connection

    def table_exists(self, table_name: str, schema: str = "dbo") -> bool:
        """Check if table exists."""
        with self.connection.get_cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ?
            """, (schema, table_name))
            result = cursor.fetchone()
            return result[0] > 0

    def get_columns(self, table_name: str, schema: str = "dbo") -> list[dict]:
        """Get table column information."""
        with self.connection.get_cursor() as cursor:
            cursor.execute("""
                SELECT
                    c.COLUMN_NAME,
                    c.DATA_TYPE,
                    c.CHARACTER_MAXIMUM_LENGTH,
                    c.NUMERIC_PRECISION,
                    c.NUMERIC_SCALE,
                    c.IS_NULLABLE,
                    c.COLUMN_DEFAULT,
                    COLUMNPROPERTY(OBJECT_ID(c.TABLE_SCHEMA + '.' + c.TABLE_NAME),
                                   c.COLUMN_NAME, 'IsIdentity') as IS_IDENTITY
                FROM INFORMATION_SCHEMA.COLUMNS c
                WHERE c.TABLE_SCHEMA = ? AND c.TABLE_NAME = ?
                ORDER BY c.ORDINAL_POSITION
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
                    "identity": bool(row[7]),
                }
                columns.append(col_info)

            return columns

    def get_primary_key(self, table_name: str, schema: str = "dbo") -> Optional[list[str]]:
        """Get primary key columns."""
        with self.connection.get_cursor() as cursor:
            cursor.execute("""
                SELECT kcu.COLUMN_NAME
                FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
                JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
                    ON tc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME
                WHERE tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
                    AND tc.TABLE_SCHEMA = ?
                    AND tc.TABLE_NAME = ?
                ORDER BY kcu.ORDINAL_POSITION
            """, (schema, table_name))

            result = cursor.fetchall()
            if result:
                return [row[0] for row in result]
            return None

    def _build_create_sql(
        self,
        table_name: str,
        columns: list[dict],
        schema: str = "dbo",
        primary_key: Optional[list[str]] = None
    ) -> str:
        """Build CREATE TABLE SQL statement (for preview)."""
        col_defs = []
        for col in columns:
            col_def = self._build_column_definition(col)
            col_defs.append(col_def)

        # Add primary key constraint
        if primary_key:
            pk_cols = ", ".join(f"[{c}]" for c in primary_key)
            col_defs.append(f"CONSTRAINT PK_{table_name} PRIMARY KEY ({pk_cols})")

        sql = f"CREATE TABLE [{schema}].[{table_name}] (\n    "
        sql += ",\n    ".join(col_defs)
        sql += "\n)"

        return sql

    def create_table(
        self,
        table_name: str,
        columns: list[dict],
        schema: str = "dbo",
        primary_key: Optional[list[str]] = None,
        drop_if_exists: bool = False
    ):
        """Create table from column definitions."""
        if drop_if_exists and self.table_exists(table_name, schema):
            self.drop_table(table_name, schema)

        with self.connection.get_cursor() as cursor:
            sql = self._build_create_sql(table_name, columns, schema, primary_key)

            logger.debug(f"Creating table: {sql}")
            cursor.execute(sql)
            logger.info(f"Created table [{schema}].[{table_name}]")

    def _build_column_definition(self, col: dict) -> str:
        """Build column definition SQL."""
        name = col["name"]
        db_type = col["type"].upper()
        length = col.get("length")
        scale = col.get("scale")
        nullable = col.get("nullable", True)
        default = col.get("default")
        identity = col.get("identity", False)

        # Build type definition
        if db_type in ("VARCHAR", "NVARCHAR", "CHAR", "NCHAR", "VARBINARY"):
            if length == "MAX" or length is None or length > 8000:
                type_def = f"{db_type}(MAX)"
            else:
                type_def = f"{db_type}({length})"
        elif db_type in ("DECIMAL", "NUMERIC"):
            precision = col.get("precision", length or 18)
            type_def = f"{db_type}({precision}, {scale or 0})"
        else:
            type_def = db_type

        parts = [f"[{name}]", type_def]

        # Add identity
        if identity:
            seed = col.get("extra", {}).get("seed", 1)
            increment = col.get("extra", {}).get("increment", 1)
            parts.append(f"IDENTITY({seed},{increment})")

        # Add nullability
        parts.append("NULL" if nullable else "NOT NULL")

        # Add default
        if default:
            parts.append(f"DEFAULT {default}")

        return " ".join(parts)

    def drop_table(self, table_name: str, schema: str = "dbo"):
        """Drop table if exists."""
        with self.connection.get_cursor() as cursor:
            cursor.execute(f"""
                IF OBJECT_ID('[{schema}].[{table_name}]', 'U') IS NOT NULL
                    DROP TABLE [{schema}].[{table_name}]
            """)
            logger.info(f"Dropped table [{schema}].[{table_name}]")

    def get_row_count(self, table_name: str, schema: str = "dbo") -> int:
        """Get table row count."""
        with self.connection.get_cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) FROM [{schema}].[{table_name}]")
            result = cursor.fetchone()
            return result[0]


class MSSQLManager:
    """High-level MSSQL operations."""

    def __init__(self, connection: MSSQLConnection):
        self.connection = connection
        self.schema = MSSQLSchema(connection)

    def test_connection(self) -> dict:
        """Test connection and return server info."""
        try:
            with self.connection.get_cursor() as cursor:
                cursor.execute("""
                    SELECT
                        @@VERSION as version,
                        DB_NAME() as db_name,
                        @@SERVERNAME as server
                """)
                row = cursor.fetchone()
                return {
                    "connected": True,
                    "version": row[0][:100] if row[0] else "Unknown",
                    "database": row[1],
                    "server": row[2],
                }
        except MSSQLError as e:
            return {
                "connected": False,
                "error": str(e),
            }
