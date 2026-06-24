"""MSSQL Change Tracking operations."""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from .mssql import MSSQLConnection, MSSQLError

logger = logging.getLogger(__name__)


@dataclass
class CTStatus:
    """Change Tracking status information."""
    database_name: str
    is_enabled_on_database: bool
    table_name: Optional[str] = None
    schema_name: Optional[str] = None
    is_enabled_on_table: Optional[bool] = None
    retention_period_days: Optional[int] = None
    auto_cleanup: Optional[bool] = None


@dataclass
class CTChange:
    """Single Change Tracking change record."""
    sys_change_version: int
    sys_change_operation: str  # I=Insert, U=Update, D=Delete
    sys_change_columns: Optional[str]
    sys_change_context: Optional[str]
    primary_key_values: dict[str, Any]


class MSSQLChangeTracking:
    """MSSQL Change Tracking operations."""

    def __init__(self, connection: MSSQLConnection):
        self.connection = connection

    def get_database_ct_status(self) -> dict[str, Any]:
        """Check if Change Tracking is enabled on the database."""
        with self.connection.get_cursor() as cursor:
            # Get current database name
            cursor.execute("SELECT DB_NAME()")
            db_name = cursor.fetchone()[0]
            
            # Check if CT is enabled by looking in sys.change_tracking_databases
            cursor.execute("""
                SELECT 
                    retention_period,
                    retention_period_units_desc,
                    is_auto_cleanup_on
                FROM sys.change_tracking_databases
                WHERE database_id = DB_ID()
            """)
            
            ct_row = cursor.fetchone()
            if ct_row:
                return {
                    "database_name": db_name,
                    "is_enabled": True,
                    "retention_period": ct_row[0],
                    "retention_period_units": ct_row[1],
                    "auto_cleanup": bool(ct_row[2]) if ct_row[2] is not None else None
                }
            else:
                return {
                    "database_name": db_name,
                    "is_enabled": False,
                    "retention_period": None,
                    "retention_period_units": None,
                    "auto_cleanup": None
                }

    def get_table_ct_status(self, table_name: str, schema: str = "dbo") -> CTStatus:
        """Check if Change Tracking is enabled on a specific table."""
        # First get database status
        db_status = self.get_database_ct_status()
        
        status = CTStatus(
            database_name=db_status["database_name"] or self.connection.config.database,
            is_enabled_on_database=db_status["is_enabled"],
            table_name=table_name,
            schema_name=schema,
            retention_period_days=db_status["retention_period"] if db_status["retention_period_units"] == "DAYS" else None,
            auto_cleanup=db_status["auto_cleanup"]
        )

        if not db_status["is_enabled"]:
            status.is_enabled_on_table = False
            return status

        # Check if CT is enabled on specific table
        with self.connection.get_cursor() as cursor:
            cursor.execute("""
                SELECT 
                    OBJECT_SCHEMA_NAME(object_id) as schema_name,
                    OBJECT_NAME(object_id) as table_name,
                    is_track_columns_updated_on
                FROM sys.change_tracking_tables
                WHERE object_id = OBJECT_ID(?, 'U')
            """, (f"{schema}.{table_name}",))
            
            row = cursor.fetchone()
            if row:
                status.is_enabled_on_table = True
            else:
                status.is_enabled_on_table = False

        return status

    def get_primary_key_columns(self, table_name: str, schema: str = "dbo") -> list[str]:
        """Get primary key columns for a table."""
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
            
            return [row[0] for row in cursor.fetchall()]

    def get_changes(
        self,
        table_name: str,
        schema: str = "dbo",
        since_version: Optional[int] = None,
        since_timestamp: Optional[datetime] = None
    ) -> list[CTChange]:
        """Get changes for a table since a specific version or timestamp.
        
        Args:
            table_name: Name of the tracked table
            schema: Schema name (default: dbo)
            since_version: Minimum change version to retrieve
            since_timestamp: Retrieve changes since this timestamp (converted to version)
        
        Returns:
            List of CTChange records
        """
        # Get primary key columns
        pk_columns = self.get_primary_key_columns(table_name, schema)
        if not pk_columns:
            raise MSSQLError(f"Table {schema}.{table_name} has no primary key. Change Tracking requires a PK.")

        # If timestamp provided, convert to version
        if since_timestamp and not since_version:
            since_version = self._get_version_from_timestamp(since_timestamp)
            logger.info(f"Converted timestamp {since_timestamp} to version {since_version}")

        # Build CHANGETABLE query
        pk_cols_str = ", ".join(f"c.[{col}]" for col in pk_columns)
        
        with self.connection.get_cursor() as cursor:
            if since_version:
                # Get changes since specific version
                query = f"""
                    SELECT 
                        c.SYS_CHANGE_VERSION,
                        c.SYS_CHANGE_OPERATION,
                        c.SYS_CHANGE_COLUMNS,
                        c.SYS_CHANGE_CONTEXT,
                        {pk_cols_str}
                    FROM CHANGETABLE(CHANGES [{schema}].[{table_name}], {since_version}) c
                    ORDER BY c.SYS_CHANGE_VERSION
                """
            else:
                # Get all changes (using 0 as minimum version)
                query = f"""
                    SELECT 
                        c.SYS_CHANGE_VERSION,
                        c.SYS_CHANGE_OPERATION,
                        c.SYS_CHANGE_COLUMNS,
                        c.SYS_CHANGE_CONTEXT,
                        {pk_cols_str}
                    FROM CHANGETABLE(CHANGES [{schema}].[{table_name}], 0) c
                    ORDER BY c.SYS_CHANGE_VERSION
                """
            
            cursor.execute(query)
            
            changes = []
            for row in cursor.fetchall():
                # Build primary key values dict
                pk_values = {}
                for i, col in enumerate(pk_columns):
                    pk_values[col] = row[4 + i]
                
                change = CTChange(
                    sys_change_version=row[0],
                    sys_change_operation=row[1],
                    sys_change_columns=row[2],
                    sys_change_context=row[3],
                    primary_key_values=pk_values
                )
                changes.append(change)
            
            return changes

    def _get_version_from_timestamp(self, timestamp: datetime) -> int:
        """Convert a timestamp to the minimum change version at that time."""
        with self.connection.get_cursor() as cursor:
            # Get the minimum version that was valid at the given timestamp
            cursor.execute("""
                SELECT MIN(SYS_CHANGE_VERSION)
                FROM sys.dm_tran_commit_table
                WHERE commit_time >= ?
            """, (timestamp,))
            
            row = cursor.fetchone()
            if row and row[0]:
                return row[0]
            else:
                # If no commits found after timestamp, get current minimum version
                cursor.execute("SELECT CHANGE_TRACKING_MIN_VALID_VERSION(OBJECT_ID('sys.objects'))")
                row = cursor.fetchone()
                return row[0] if row and row[0] else 0

    def get_current_version(self) -> int:
        """Get the current Change Tracking version."""
        with self.connection.get_cursor() as cursor:
            cursor.execute("SELECT CHANGE_TRACKING_CURRENT_VERSION()")
            row = cursor.fetchone()
            return row[0] if row and row[0] else 0

    def get_min_valid_version(self, table_name: str, schema: str = "dbo") -> int:
        """Get the minimum valid version for a table."""
        with self.connection.get_cursor() as cursor:
            cursor.execute("""
                SELECT CHANGE_TRACKING_MIN_VALID_VERSION(OBJECT_ID(?, 'U'))
            """, (f"{schema}.{table_name}",))
            
            row = cursor.fetchone()
            return row[0] if row and row[0] else 0

    def format_changes_table(self, changes: list[CTChange]) -> list[dict[str, Any]]:
        """Format changes as a list of dictionaries for display."""
        result = []
        for change in changes:
            row = {
                "SYS_CHANGE_VERSION": change.sys_change_version,
                "SYS_CHANGE_OPERATION": change.sys_change_operation,
                "SYS_CHANGE_COLUMNS": change.sys_change_columns,
                "SYS_CHANGE_CONTEXT": change.sys_change_context,
            }
            # Add primary key columns
            for col, val in change.primary_key_values.items():
                row[f"PK_{col}"] = val
            result.append(row)
        return result

    def enable_database_ct(self, retention_days: int = 2, auto_cleanup: bool = True) -> None:
        """Enable Change Tracking on the database.
        
        Args:
            retention_days: Number of days to retain change tracking data
            auto_cleanup: Whether to enable automatic cleanup of old CT data
        """
        # ALTER DATABASE cannot run inside a transaction, use raw connection with autocommit
        import pyodbc
        conn_str = self.connection.build_connection_string()
        conn = pyodbc.connect(conn_str, autocommit=True)
        try:
            cursor = conn.cursor()
            auto_cleanup_str = "ON" if auto_cleanup else "OFF"
            sql = f"""
                ALTER DATABASE CURRENT
                SET CHANGE_TRACKING = ON
                (CHANGE_RETENTION = {retention_days} DAYS, AUTO_CLEANUP = {auto_cleanup_str})
            """
            cursor.execute(sql)
        finally:
            conn.close()

    def disable_database_ct(self) -> None:
        """Disable Change Tracking on the database."""
        # ALTER DATABASE cannot run inside a transaction, use raw connection with autocommit
        import pyodbc
        conn_str = self.connection.build_connection_string()
        conn = pyodbc.connect(conn_str, autocommit=True)
        try:
            cursor = conn.cursor()
            cursor.execute("ALTER DATABASE CURRENT SET CHANGE_TRACKING = OFF")
        finally:
            conn.close()

    def enable_table_ct(self, table_name: str, schema: str = "dbo", track_columns_updated: bool = True) -> None:
        """Enable Change Tracking on a table.
        
        Args:
            table_name: Name of the table
            schema: Schema name (default: dbo)
            track_columns_updated: Whether to track which columns were updated
        """
        # Verify table has primary key
        pk_columns = self.get_primary_key_columns(table_name, schema)
        if not pk_columns:
            raise MSSQLError(f"Table {schema}.{table_name} does not have a primary key. Change Tracking requires a primary key.")
        
        with self.connection.get_cursor() as cursor:
            track_cols_str = "ON" if track_columns_updated else "OFF"
            sql = f"""
                ALTER TABLE [{schema}].[{table_name}]
                ENABLE CHANGE_TRACKING
                WITH (TRACK_COLUMNS_UPDATED = {track_cols_str})
            """
            cursor.execute(sql)
            cursor.commit()

    def disable_table_ct(self, table_name: str, schema: str = "dbo") -> None:
        """Disable Change Tracking on a table.
        
        Args:
            table_name: Name of the table
            schema: Schema name (default: dbo)
        """
        with self.connection.get_cursor() as cursor:
            cursor.execute(f"ALTER TABLE [{schema}].[{table_name}] DISABLE CHANGE_TRACKING")
            cursor.commit()
