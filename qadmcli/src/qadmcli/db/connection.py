"""AS400 database connection manager."""

import logging
import os
from contextlib import contextmanager
from typing import Any, Generator

from ..models.connection import ConnectionConfig

logger = logging.getLogger("qadmcli")


class ConnectionError(Exception):
    """Connection error with detailed message."""
    
    def __init__(self, message: str, original_error: Exception | None = None):
        self.message = message
        self.original_error = original_error
        super().__init__(self.message)


class AS400ConnectionManager:
    """Manages AS400 database connections using jt400 JDBC driver."""
    
    # jt400 driver class
    DRIVER_CLASS = "com.ibm.as400.access.AS400JDBCDriver"
    
    def __init__(self, config: ConnectionConfig):
        self.config = config
        self._connection: Any = None
        self._jt400_path: str | None = None
    
    def _get_jt400_path(self) -> str:
        """Find or download jt400.jar path."""
        if self._jt400_path:
            return self._jt400_path
        
        # Check common locations
        possible_paths = [
            os.environ.get("JT400_JAR"),
            "/usr/share/java/jt400.jar",
            "/opt/ibm/jt400/jt400.jar",
            os.path.expanduser("~/.local/share/jt400/jt400.jar"),
            os.path.join(os.path.dirname(__file__), "..", "lib", "jt400.jar"),
        ]
        
        for path in possible_paths:
            if path and os.path.exists(path):
                self._jt400_path = path
                logger.debug(f"Found jt400.jar at: {path}")
                return path
        
        # If not found, raise error with instructions
        raise ConnectionError(
            "jt400.jar not found. Please download it from IBM and place it in one of:\n"
            "  - Set JT400_JAR environment variable\n"
            "  - /usr/share/java/jt400.jar\n"
            "  - ~/.local/share/jt400/jt400.jar\n"
            "  - src/qadmcli/lib/jt400.jar\n"
            "Download from: https://sourceforge.net/projects/jt400/"
        )
    
    def _start_jvm(self) -> None:
        """Start JVM if not already running."""
        import jpype
        if not jpype.isJVMStarted():
            jt400_path = self._get_jt400_path()
            classpath = [jt400_path]
            
            # Start JVM
            jpype.startJVM(jpype.getDefaultJVMPath(), classpath=classpath)
            logger.debug("JVM started successfully")
    
    def connect(self) -> None:
        """Establish connection to AS400."""
        try:
            self._start_jvm()
            
            import jaydebeapi
            
            jdbc_url = self.config.get_jdbc_url()
            props = self.config.get_connection_properties()
            
            logger.debug(f"Connecting to: {jdbc_url}")
            
            self._connection = jaydebeapi.connect(
                self.DRIVER_CLASS,
                jdbc_url,
                props,
                jars=[self._get_jt400_path()]
            )
            
            logger.info(f"Connected to AS400: {self.config.as400.host}")
            
        except ConnectionError:
            raise
        except Exception as e:
            error_msg = self._parse_connection_error(e)
            raise ConnectionError(error_msg, e)
    
    def disconnect(self) -> None:
        """Close database connection."""
        if self._connection:
            try:
                self._connection.close()
                logger.info("Disconnected from AS400")
            except Exception as e:
                logger.warning(f"Error closing connection: {e}")
            finally:
                self._connection = None
    
    def is_connected(self) -> bool:
        """Check if connection is active."""
        if not self._connection:
            return False
        try:
            # Test connection with simple query
            cursor = self._connection.cursor()
            cursor.execute("SELECT 1 FROM SYSIBM.SYSDUMMY1")
            cursor.close()
            return True
        except Exception:
            return False
    
    def test_connection(self) -> dict[str, Any]:
        """Test connection and return server info, permissions, and library details."""
        if not self.is_connected():
            self.connect()
        
        default_library = self.config.defaults.library
        
        info = {
            "host": self.config.as400.host,
            "connected": True,
            "server_info": {},
            "user": self.config.as400.user,
            "default_library": default_library,
            "permissions": {},
            "library_info": {},
        }
        
        try:
            cursor = self._connection.cursor()
            
            # Get version info
            logger.debug("Executing: SELECT OS_VERSION, OS_RELEASE FROM SYSIBMADM.ENV_SYS_INFO")
            cursor.execute("SELECT OS_VERSION, OS_RELEASE FROM SYSIBMADM.ENV_SYS_INFO")
            row = cursor.fetchone()
            if row:
                info["server_info"]["version"] = f"{row[0]}.{row[1]}"
            
            # Check user permissions on default library
            perm_sql = """
                SELECT 
                    OBJECT_AUTHORITY,
                    DATA_READ,
                    DATA_ADD,
                    DATA_UPDATE,
                    DATA_DELETE
                FROM QSYS2.OBJECT_PRIVILEGES
                WHERE OBJECT_SCHEMA = ?
                AND OBJECT_NAME = ?
                AND AUTHORIZATION_NAME = ?
            """
            logger.debug(f"Executing SQL: {perm_sql.strip()} [params: ({default_library}, {default_library}, {self.config.as400.user})]")
            cursor.execute(perm_sql, (default_library, default_library, self.config.as400.user))
            
            row = cursor.fetchone()
            if row:
                info["permissions"]["library"] = {
                    "object_authority": row[0],
                    "data_read": row[1] == "YES",
                    "data_add": row[2] == "YES",
                    "data_update": row[3] == "YES",
                    "data_delete": row[4] == "YES",
                    "can_create_table": row[0] in ("*ALL", "*CHANGE"),
                }
            else:
                info["permissions"]["library"] = {"access": "none"}
            
            # List available journals in the library
            journals_sql = """
                SELECT 
                    JOURNAL_LIBRARY,
                    JOURNAL_NAME,
                    ATTACHED_JOURNAL_RECEIVER_LIBRARY,
                    ATTACHED_JOURNAL_RECEIVER_NAME
                FROM QSYS2.JOURNAL_INFO
                WHERE JOURNAL_LIBRARY = ?
            """
            logger.debug(f"Executing SQL: {journals_sql.strip()} [params: ({default_library},)]")
            cursor.execute(journals_sql, (default_library,))
            
            journals = []
            rows = cursor.fetchall()
            logger.debug(f"Found {len(rows)} journals in library {default_library}")
            for row in rows:
                journals.append({
                    "journal": f"{row[0]}.{row[1]}",
                    "receiver": f"{row[2]}.{row[3]}" if row[2] and row[3] else None,
                })
            info["library_info"]["available_journals"] = journals
            
            # List tables in the library
            tables_sql = """
                SELECT 
                    SYSTEM_TABLE_NAME,
                    TABLE_TYPE
                FROM QSYS2.SYSTABLES
                WHERE SYSTEM_TABLE_SCHEMA = ?
                AND TABLE_TYPE IN ('T', 'P')
                ORDER BY SYSTEM_TABLE_NAME
                FETCH FIRST 20 ROWS ONLY
            """
            logger.debug(f"Executing SQL: {tables_sql.strip()} [params: ({default_library},)]")
            cursor.execute(tables_sql, (default_library,))
            
            tables = []
            rows = cursor.fetchall()
            logger.debug(f"Found {len(rows)} tables in library {default_library}")
            for row in rows:
                tables.append({
                    "name": row[0],
                    "type": row[1],
                })
            info["library_info"]["tables"] = tables
            
            cursor.close()
            
        except Exception as e:
            logger.warning(f"Could not retrieve server info: {e}")
        
        return info
    
    def execute(self, sql: str, params: tuple | None = None) -> Any:
        """Execute SQL statement."""
        if not self.is_connected():
            self.connect()
        
        # Log the SQL query (truncate if very long)
        sql_display = sql.strip()[:200] + "..." if len(sql.strip()) > 200 else sql.strip()
        params_display = f" [params: {params}]" if params else ""
        logger.debug(f"SQL: {sql_display}{params_display}")
        
        cursor = self._connection.cursor()
        try:
            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)
            return cursor
        except Exception as e:
            logger.debug(f"SQL Error: {e}")
            cursor.close()
            raise
    
    def execute_many(self, sql: str, params_list: list[tuple]) -> Any:
        """Execute SQL statement with multiple parameter sets."""
        if not self.is_connected():
            self.connect()
        
        cursor = self._connection.cursor()
        try:
            cursor.executemany(sql, params_list)
            return cursor
        except Exception as e:
            cursor.close()
            raise
    
    def commit(self) -> None:
        """Commit current transaction."""
        if self._connection:
            self._connection.commit()
    
    def rollback(self) -> None:
        """Rollback current transaction."""
        if self._connection:
            self._connection.rollback()
    
    @contextmanager
    def cursor(self) -> Generator[Any, None, None]:
        """Context manager for database cursor."""
        if not self.is_connected():
            self.connect()
        
        cursor = self._connection.cursor()
        try:
            yield cursor
        finally:
            cursor.close()
    
    def _parse_connection_error(self, error: Exception) -> str:
        """Parse connection error and return user-friendly message."""
        error_str = str(error)
        
        # Common AS400 error patterns
        if "Connection refused" in error_str:
            return (
                f"Connection refused to {self.config.as400.host}:{self.config.as400.port}\n"
                "Please check:\n"
                "  - Hostname/IP address is correct\n"
                "  - DRDA port (8471) is open and accessible\n"
                "  - AS400 system is online"
            )
        elif "password" in error_str.lower() or "credential" in error_str.lower():
            return (
                "Authentication failed. Please check:\n"
                "  - Username is correct\n"
                "  - Password is correct\n"
                "  - User profile is not disabled"
            )
        elif "ssl" in error_str.lower():
            return (
                "SSL connection error. Please check:\n"
                "  - SSL is properly configured on AS400\n"
                "  - Try setting ssl: false in config if SSL is not required"
            )
        elif "ClassNotFoundException" in error_str or "jt400" in error_str.lower():
            return (
                "jt400 JDBC driver not found.\n"
                "Please download jt400.jar and set JT400_JAR environment variable."
            )
        else:
            return f"Connection error: {error_str}"
    
    def __enter__(self) -> "AS400ConnectionManager":
        self.connect()
        return self
    
    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.disconnect()
