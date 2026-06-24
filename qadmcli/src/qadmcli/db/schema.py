"""Table schema operations."""

import logging
import re
from typing import Any

from ..models.table import TableConfig, TableInfo
from .connection import AS400ConnectionManager

logger = logging.getLogger("qadmcli")


class SchemaManager:
    """Manages database schema operations."""
    
    def __init__(self, connection: AS400ConnectionManager):
        self.conn = connection
    
    def _resolve_table_name(self, table_name: str, library: str) -> str | None:
        """Resolve SQL name to system name. Returns system name or None if not found."""
        # First try as system name
        sql = """
            SELECT SYSTEM_TABLE_NAME 
            FROM QSYS2.SYSTABLES 
            WHERE SYSTEM_TABLE_NAME = ? AND SYSTEM_TABLE_SCHEMA = ?
        """
        cursor = self.conn.execute(sql, (table_name.upper(), library.upper()))
        row = cursor.fetchone()
        cursor.close()
        if row:
            return str(row[0])
        
        # Try as SQL name
        sql = """
            SELECT SYSTEM_TABLE_NAME 
            FROM QSYS2.SYSTABLES 
            WHERE TABLE_NAME = ? AND TABLE_SCHEMA = ?
        """
        cursor = self.conn.execute(sql, (table_name.upper(), library.upper()))
        row = cursor.fetchone()
        cursor.close()
        if row:
            return str(row[0])
        
        return None
    
    def table_exists(self, table_name: str, library: str) -> bool:
        """Check if table exists in specified library (accepts SQL or system name)."""
        return self._resolve_table_name(table_name, library) is not None
    
    def get_table_info(self, table_name: str, library: str) -> TableInfo | None:
        """Get table information from system catalogs including journal info.
        
        Accepts either SQL name or system name.
        """
        # Resolve table name (SQL name -> system name)
        system_name = self._resolve_table_name(table_name, library)
        if not system_name:
            return None
        
        # Use OBJECT_STATISTICS for accurate info including journal status
        sql = """
            SELECT 
                OBJNAME,
                OBJTYPE,
                OBJTEXT,
                JOURNALED,
                JOURNAL_NAME,
                JOURNAL_LIBRARY
            FROM TABLE(QSYS2.OBJECT_STATISTICS(?, 'FILE', ?))
            WHERE OBJTYPE = '*FILE'
        """
        cursor = self.conn.execute(sql, (library.upper(), system_name))
        row = cursor.fetchone()
        cursor.close()
        
        if not row:
            return None
        
        # Get SQL name from SYSTABLES
        sql_name = None
        try:
            sql_sql = """
                SELECT TABLE_NAME 
                FROM QSYS2.SYSTABLES 
                WHERE SYSTEM_TABLE_NAME = ? AND SYSTEM_TABLE_SCHEMA = ?
            """
            cursor = self.conn.execute(sql_sql, (str(row[0]), library.upper()))
            sql_row = cursor.fetchone()
            cursor.close()
            if sql_row and sql_row[0]:
                sql_name = str(sql_row[0])
        except Exception:
            pass
        
        # Handle potential None values from database
        return TableInfo(
            name=str(row[0]) if row[0] else "",
            sql_name=sql_name,
            library=library.upper(),
            table_type="T",
            description=str(row[2]) if row[2] else None,
            journaled=row[3] == "YES" if row[3] else False,
            journal_name=str(row[4]) if row[4] else None,
            journal_library=str(row[5]) if row[5] else None,
        )
    
    def get_table_row_count(self, table_name: str, library: str) -> int | None:
        """Get row count for a table (accepts SQL or system name)."""
        try:
            # Resolve table name
            system_name = self._resolve_table_name(table_name, library)
            if not system_name:
                return None
            cursor = self.conn.execute(f"SELECT COUNT(*) FROM {library}.{system_name}")
            row = cursor.fetchone()
            cursor.close()
            return row[0] if row else None
        except Exception:
            return None
    
    def get_columns(self, table_name: str, library: str) -> list[dict[str, Any]]:
        """Get column information for a table (accepts SQL or system name)."""
        # Resolve table name
        system_name = self._resolve_table_name(table_name, library)
        if not system_name:
            return []
        
        sql = """
            SELECT 
                c.SYSTEM_COLUMN_NAME,
                c.COLUMN_NAME,
                c.DATA_TYPE,
                c.LENGTH,
                c.NUMERIC_SCALE,
                c.IS_NULLABLE,
                c.COLUMN_DEFAULT,
                c.COLUMN_TEXT,
                c.IS_IDENTITY,
                c.CCSID
            FROM QSYS2.SYSCOLUMNS c
            WHERE c.SYSTEM_TABLE_NAME = ?
            AND c.SYSTEM_TABLE_SCHEMA = ?
            ORDER BY c.ORDINAL_POSITION
        """
        cursor = self.conn.execute(sql, (system_name, library.upper()))
        columns = []
        for row in cursor.fetchall():
            # Convert Java strings to Python strings
            nullable_val = str(row[5]).upper() if row[5] else "Y"
            column_default = str(row[6]) if row[6] else ""
            is_identity = str(row[8]).upper() in ("Y", "YES", "TRUE", "1") if row[8] else False
            is_generated = "GENERATED" in column_default.upper()
            
            columns.append({
                "system_name": str(row[0]) if row[0] else None,
                "name": str(row[1]) if row[1] else None,
                "type": str(row[2]) if row[2] else None,
                "length": row[3],
                "scale": row[4],
                "nullable": nullable_val in ("Y", "YES", "TRUE", "1"),
                "default": column_default if row[6] else None,
                "description": str(row[7]) if row[7] else None,
                "is_identity": is_identity,
                "is_generated": is_generated,
                "ccsid": row[9] if len(row) > 9 else None,  # CCSID value
                "is_binary": row[9] == 65535 if len(row) > 9 else False,  # CCSID 65535 = binary
            })
        cursor.close()
        return columns
    
    def get_primary_key(self, table_name: str, library: str) -> list[str]:
        """Get primary key columns for a table (accepts SQL or system name)."""
        # Resolve table name
        system_name = self._resolve_table_name(table_name, library)
        if not system_name:
            return []
        
        sql = """
            SELECT k.COLUMN_NAME
            FROM QSYS2.SYSKEYCST k
            JOIN QSYS2.SYSCST c ON k.CONSTRAINT_NAME = c.CONSTRAINT_NAME
                AND k.CONSTRAINT_SCHEMA = c.CONSTRAINT_SCHEMA
            WHERE k.SYSTEM_TABLE_NAME = ?
            AND k.SYSTEM_TABLE_SCHEMA = ?
            AND c.CONSTRAINT_TYPE = 'PRIMARY KEY'
            ORDER BY k.ORDINAL_POSITION
        """
        try:
            cursor = self.conn.execute(sql, (system_name, library.upper()))
            pk_columns = [str(row[0]) for row in cursor.fetchall()]
            cursor.close()
            return pk_columns
        except Exception:
            return []
    
    def create_table(self, config: TableConfig, dry_run: bool = False) -> str:
        """Create table from configuration."""
        ddl = config.to_sql_ddl()
        
        if dry_run:
            logger.info("DRY RUN - Would execute:")
            logger.info(ddl)
            return ddl
        
        # Execute DDL statements
        statements = [s.strip() for s in ddl.split(";") if s.strip()]
        
        for stmt in statements:
            if stmt.upper().startswith(("CREATE", "LABEL")):
                logger.debug(f"Executing: {stmt[:100]}...")
                cursor = self.conn.execute(stmt)
                cursor.close()
        
        # Create indexes if specified
        if config.indexes:
            for idx in config.indexes:
                idx_sql = self._build_index_sql(config, idx)
                logger.debug(f"Creating index: {idx_sql[:100]}...")
                cursor = self.conn.execute(idx_sql)
                cursor.close()
        
        self.conn.commit()
        logger.info(f"Created table {config.library}.{config.name}")
        
        return ddl
    
    def drop_table(self, table_name: str, library: str, cascade: bool = False) -> None:
        """Drop a table."""
        cascade_str = "CASCADE" if cascade else ""
        sql = f"DROP TABLE {library}.{table_name} {cascade_str}".strip()
        
        logger.debug(f"Executing: {sql}")
        cursor = self.conn.execute(sql)
        cursor.close()
        self.conn.commit()
        
        logger.info(f"Dropped table {library}.{table_name}")
    
    def drop_create_table(
        self, 
        config: TableConfig, 
        force: bool = False,
        dry_run: bool = False
    ) -> str:
        """Drop and recreate table."""
        if self.table_exists(config.name, config.library):
            if not force and not dry_run:
                raise ValueError(
                    f"Table {config.library}.{config.name} exists. "
                    "Use --force to drop and recreate."
                )
            
            if dry_run:
                logger.info(f"DRY RUN - Would drop table {config.library}.{config.name}")
            else:
                self.drop_table(config.name, config.library)
        
        return self.create_table(config, dry_run)
    
    def load_sql_file(self, sql_path: str) -> str:
        """Load SQL from file."""
        with open(sql_path, "r", encoding="utf-8") as f:
            return f.read()
    
    def execute_sql_file(self, sql_path: str, dry_run: bool = False) -> list[str]:
        """Execute SQL statements from file."""
        sql_content = self.load_sql_file(sql_path)
        
        # Split into statements
        statements = self._split_sql_statements(sql_content)
        
        executed = []
        for stmt in statements:
            stmt = stmt.strip()
            if not stmt or stmt.startswith("--"):
                continue
            
            if dry_run:
                logger.info(f"DRY RUN - Would execute: {stmt[:100]}...")
            else:
                logger.debug(f"Executing: {stmt[:100]}...")
                cursor = self.conn.execute(stmt)
                cursor.close()
            
            executed.append(stmt)
        
        if not dry_run:
            self.conn.commit()
        
        return executed
    
    def _build_index_sql(self, config: TableConfig, index_def: dict[str, Any]) -> str:
        """Build CREATE INDEX SQL."""
        idx_name = index_def.get("name", f"IDX_{config.name}_{index_def['columns'][0]}")
        unique = "UNIQUE " if index_def.get("unique") else ""
        columns = ", ".join(index_def["columns"])
        
        return (
            f"CREATE {unique}INDEX {config.library}.{idx_name} "
            f"ON {config.library}.{config.name} ({columns})"
        )
    
    def _split_sql_statements(self, sql: str) -> list[str]:
        """Split SQL content into individual statements."""
        # Remove comments
        sql = re.sub(r"--.*?\n", "\n", sql)
        sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
        
        # Split by semicolon
        statements = []
        current = []
        
        for line in sql.split("\n"):
            line = line.strip()
            if not line:
                continue
            
            current.append(line)
            if line.endswith(";"):
                statements.append(" ".join(current))
                current = []
        
        if current:
            statements.append(" ".join(current))
        
        return statements
    
    def list_tables(self, library: str, table_type: str | None = None) -> list[TableInfo]:
        """List tables in a library using OBJECT_STATISTICS for journal info."""
        # Use OBJECT_STATISTICS to get journal info (it doesn't have row count)
        sql = """
            SELECT 
                OBJNAME,
                OBJTYPE,
                OBJTEXT,
                JOURNALED,
                JOURNAL_NAME,
                JOURNAL_LIBRARY
            FROM TABLE(QSYS2.OBJECT_STATISTICS(?, 'FILE', '*ALL'))
            WHERE OBJTYPE = '*FILE'
        """
        cursor = self.conn.execute(sql, (library.upper(),))
        tables = []
        
        # Get all SQL names in one query for efficiency
        sql_names = {}
        try:
            sql_name_query = """
                SELECT SYSTEM_TABLE_NAME, TABLE_NAME 
                FROM QSYS2.SYSTABLES 
                WHERE SYSTEM_TABLE_SCHEMA = ?
            """
            name_cursor = self.conn.execute(sql_name_query, (library.upper(),))
            for name_row in name_cursor.fetchall():
                if name_row[0] and name_row[1]:
                    sql_names[str(name_row[0])] = str(name_row[1])
            name_cursor.close()
        except Exception:
            pass
        
        for row in cursor.fetchall():
            system_name = str(row[0]) if row[0] else ""
            tables.append(TableInfo(
                name=system_name,
                sql_name=sql_names.get(system_name),
                library=library.upper(),
                table_type="T",  # All files from OBJECT_STATISTICS are tables
                description=str(row[2]) if row[2] else None,
                journaled=row[3] == "YES" if row[3] else False,
                journal_name=str(row[4]) if row[4] else None,
                journal_library=str(row[5]) if row[5] else None,
            ))
        
        cursor.close()
        return tables
    
    def generate_yaml_from_table(self, table_name: str, library: str) -> str:
        """Generate YAML schema from existing table."""
        import yaml
        
        # Helper to convert Java types to Python
        def to_python(val):
            if val is None:
                return None
            # Handle Java integers
            if hasattr(val, 'intValue'):
                return int(val.intValue())
            # Handle Java strings
            if hasattr(val, 'toString'):
                return str(val.toString())
            return val
        
        # Get table info
        table_info = self.get_table_info(table_name, library)
        columns = self.get_columns(table_name, library)
        
        # Build YAML structure
        schema = {
            "table": {
                "name": str(table_name).upper(),
                "library": str(library).upper(),
                "description": table_info.description if table_info and table_info.description else f"Schema for {table_name}"
            },
            "columns": []
        }
        
        # Map IBM i types to schema types
        type_mapping = {
            "CHARACTER": "CHAR",
            "CHAR": "CHAR",
            "VARCHAR": "VARCHAR",
            "DECIMAL": "DECIMAL",
            "NUMERIC": "DECIMAL",
            "INTEGER": "INTEGER",
            "BIGINT": "BIGINT",
            "SMALLINT": "SMALLINT",
            "DATE": "DATE",
            "TIME": "TIME",
            "TIMESTAMP": "TIMESTAMP",
            "BLOB": "BLOB",
            "CLOB": "CLOB",
            "VARBINARY": "VARBINARY",
            "BINARY": "BINARY",
            "GRAPHIC": "GRAPHIC",
            "VARGRAPHIC": "VARGRAPHIC",
        }
        
        for col in columns:
            col_type = str(col["type"]).upper()
            col_def = {
                "name": str(col["name"]),
                "type": type_mapping.get(col_type, col_type),
                "nullable": col["nullable"]
            }
            
            # Add length if applicable
            col_length = to_python(col["length"])
            if col_length and col_type in ("CHARACTER", "CHAR", "VARCHAR", "GRAPHIC", "VARGRAPHIC", "BINARY", "VARBINARY"):
                col_def["length"] = int(col_length)
            
            # Add scale for decimal/numeric
            col_scale = to_python(col["scale"])
            if col_scale is not None and col_type in ("DECIMAL", "NUMERIC"):
                col_def["length"] = int(col_length) if col_length else None
                col_def["scale"] = int(col_scale)
            
            # Add default if present
            if col["default"]:
                col_def["default"] = str(col["default"])
            
            # Add description
            if col["description"]:
                col_def["description"] = str(col["description"])
            
            schema["columns"].append(col_def)
        
        # Get constraints (primary key, foreign keys)
        constraints = self._get_constraints(table_name, library)
        if constraints:
            schema["constraints"] = constraints
        
        # Get indexes
        indexes = self._get_indexes(table_name, library)
        if indexes:
            schema["constraints"]["indexes"] = indexes
        
        # Add journaling info
        if table_info and table_info.journaled:
            schema["journaling"] = {
                "enabled": True,
                "journal_library": table_info.journal_library or library.upper(),
                "journal_name": table_info.journal_name or "${JOURNAL_NAME}"
            }
        
        return yaml.dump(schema, default_flow_style=False, sort_keys=False, allow_unicode=True)
    
    def _get_constraints(self, table_name: str, library: str) -> dict:
        """Get table constraints."""
        constraints = {}
        
        # Primary key - use SYSKEYCST for column names
        pk_sql = """
            SELECT k.COLUMN_NAME
            FROM QSYS2.SYSKEYCST k
            JOIN QSYS2.SYSCST c ON k.CONSTRAINT_NAME = c.CONSTRAINT_NAME
                AND k.CONSTRAINT_SCHEMA = c.CONSTRAINT_SCHEMA
            WHERE k.SYSTEM_TABLE_NAME = ?
            AND k.SYSTEM_TABLE_SCHEMA = ?
            AND c.CONSTRAINT_TYPE = 'PRIMARY KEY'
            ORDER BY k.ORDINAL_POSITION
        """
        try:
            cursor = self.conn.execute(pk_sql, (table_name.upper(), library.upper()))
            pk_columns = [str(row[0]) for row in cursor.fetchall()]
            cursor.close()
            if pk_columns:
                constraints["primary_key"] = {"columns": pk_columns}
        except Exception:
            pass
        
        # Foreign keys
        fk_sql = """
            SELECT 
                CONSTRAINT_NAME,
                COLUMN_NAME,
                REFERENTIAL_CONSTRAINT_SCHEMA,
                REFERENTIAL_CONSTRAINT_NAME
            FROM QSYS2.SYSKEYCST
            WHERE SYSTEM_TABLE_NAME = ?
            AND SYSTEM_TABLE_SCHEMA = ?
        """
        try:
            cursor = self.conn.execute(fk_sql, (table_name.upper(), library.upper()))
            fk_rows = cursor.fetchall()
            cursor.close()
            if fk_rows:
                constraints["foreign_keys"] = []
                for row in fk_rows:
                    constraints["foreign_keys"].append({
                        "name": row[0],
                        "columns": [row[1]],
                        "references": {
                            "table": row[2],
                            "columns": [row[3]]
                        }
                    })
        except Exception:
            pass
        
        return constraints
    
    def _get_indexes(self, table_name: str, library: str) -> list:
        """Get table indexes."""
        indexes = []
        
        sql = """
            SELECT 
                INDEX_NAME,
                COLUMN_NAME,
                IS_UNIQUE
            FROM QSYS2.SYSKEYS
            WHERE SYSTEM_TABLE_NAME = ?
            AND SYSTEM_TABLE_SCHEMA = ?
            ORDER BY INDEX_NAME, ORDINAL_POSITION
        """
        try:
            cursor = self.conn.execute(sql, (table_name.upper(), library.upper()))
            index_map = {}
            for row in cursor.fetchall():
                idx_name = row[0]
                if idx_name not in index_map:
                    index_map[idx_name] = {
                        "name": idx_name,
                        "columns": [],
                        "unique": row[2] == "YES"
                    }
                index_map[idx_name]["columns"].append(row[1])
            cursor.close()
            
            indexes = list(index_map.values())
        except Exception:
            pass
        
        return indexes
