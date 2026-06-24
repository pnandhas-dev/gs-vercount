"""Mockup data operations for testing."""

import logging
import random
from typing import Any, Optional
from dataclasses import dataclass

from ..utils.data_generator import DataGenerator
from .connection import AS400ConnectionManager
from .agent_client import AS400AgentClient

logger = logging.getLogger("qadmcli")


class SchemaValidationError(Exception):
    """Raised when schema validation fails."""
    pass


@dataclass
class MockupConfig:
    """Configuration for mockup operations."""
    insert_ratio: int = 60
    update_ratio: int = 20
    delete_ratio: int = 20
    total_transactions: int = 1000
    batch_size: int = 100
    dry_run: bool = False
    random_pks: bool = False


class MockupManager:
    """Manages mockup data generation and operations."""

    def __init__(self, connection: AS400ConnectionManager, schema_hints: Optional[dict[str, str]] = None,
                 schema_validation: Optional[dict[str, Any]] = None):
        self.conn = connection
        self.data_generator = DataGenerator()
        self.schema_hints = schema_hints or {}
        self.schema_validation = schema_validation or {}
        
        # Initialize agent client (auto-detects from QADMCLI_AGENT_URL env var)
        self.agent = AS400AgentClient()
        if self.agent.is_available():
            logger.info("🚀 Using AS400 agent for bulk operations")
        else:
            logger.info("📡 Using direct JT400 connection")

    def validate_schema(self, table_name: str, library: str) -> list[str]:
        """Validate that actual table schema matches the input schema.

        Returns a list of validation errors. Empty list if validation passes.
        """
        if not self.schema_validation:
            return []

        errors = []
        db_columns = self._get_columns(table_name, library)
        db_col_map = {col['name'].upper(): col for col in db_columns}

        for col_name, expected in self.schema_validation.items():
            col_name_upper = col_name.upper()
            if col_name_upper not in db_col_map:
                errors.append(f"Column '{col_name}' not found in table {library}.{table_name}")
                continue

            db_col = db_col_map[col_name_upper]

            # Check data type
            if 'type' in expected:
                expected_type = expected['type'].upper()
                actual_type = db_col['type'].upper()
                # Allow some flexibility in type matching (e.g., VARCHAR vs CHAR)
                if expected_type != actual_type:
                    # Check if types are compatible
                    compatible_types = [
                        ('VARCHAR', 'CHAR'),
                        ('CHAR', 'VARCHAR'),
                        ('DECIMAL', 'NUMERIC'),
                        ('NUMERIC', 'DECIMAL'),
                    ]
                    is_compatible = any(
                        (expected_type == compat[0] and actual_type == compat[1]) or
                        (expected_type == compat[1] and actual_type == compat[0])
                        for compat in compatible_types
                    )
                    if not is_compatible:
                        errors.append(
                            f"Column '{col_name}' type mismatch: expected {expected['type']}, "
                            f"got {db_col['type']}"
                        )

            # Check length
            if 'length' in expected and expected['length'] is not None:
                if db_col['length'] != expected['length']:
                    errors.append(
                        f"Column '{col_name}' length mismatch: expected {expected['length']}, "
                        f"got {db_col['length']}"
                    )

            # Check scale for decimal/numeric
            if 'scale' in expected and expected['scale'] is not None:
                if db_col['scale'] != expected['scale']:
                    errors.append(
                        f"Column '{col_name}' scale mismatch: expected {expected['scale']}, "
                        f"got {db_col['scale']}"
                    )

            # Check nullable
            if 'nullable' in expected:
                expected_nullable = expected['nullable']
                actual_nullable = db_col['nullable']
                if expected_nullable != actual_nullable:
                    errors.append(
                        f"Column '{col_name}' nullable mismatch: expected {expected_nullable}, "
                        f"got {actual_nullable}"
                    )

        return errors

    def generate_mock_data(self, table_name: str, library: str,
                          config: MockupConfig) -> dict[str, Any]:
        """Generate mock data for a table."""
        # Store table info for batch execution
        self._table_name = table_name
        self._library = library
        
        # Validate table exists
        columns = self._get_columns(table_name, library)
        if not columns:
            raise ValueError(f"Table '{library}.{table_name}' does not exist or has no columns")
        
        # Validate schema if validation rules are provided
        if self.schema_validation:
            validation_errors = self.validate_schema(table_name, library)
            if validation_errors:
                error_msg = "Schema validation failed:\n" + "\n".join(f"  - {e}" for e in validation_errors)
                raise SchemaValidationError(error_msg)

        # Store columns for batch execution
        self._columns = columns
        
        # Get primary key info
        pk_columns = self._get_primary_key(table_name, library)
        
        # Get existing PK values to avoid duplicates
        existing_pks = self._get_existing_pk_values(table_name, library, pk_columns) if pk_columns else set()
        
        results = {
            "inserts": [],
            "updates": [],
            "deletes": [],
            "sql_statements": [],
            "stats": {"inserted": 0, "updated": 0, "deleted": 0}
        }
        
        # Calculate transaction counts
        total = config.total_transactions
        insert_count = int(total * config.insert_ratio / 100)
        update_count = int(total * config.update_ratio / 100)
        delete_count = int(total * config.delete_ratio / 100)
        
        logger.info(f"Generating {insert_count} inserts, {update_count} updates, {delete_count} deletes")
        
        all_inserted_pks = []
        
        # Generate INSERT operations
        for i in range(insert_count):
            row_data = self._generate_row(columns, pk_columns, existing_pks, is_insert=True)
            if pk_columns:
                all_inserted_pks.append([row_data[col] for col in pk_columns])
            sql = self._build_insert_sql(table_name, library, row_data, columns)
            
            if config.dry_run:
                results["sql_statements"].append(sql)
            else:
                results["inserts"].append(row_data)
            
            # Execute in batches
            if not config.dry_run and (i + 1) % config.batch_size == 0:
                self._execute_batch(results["inserts"], "INSERT")
                results["stats"]["inserted"] += len(results["inserts"])
                results["inserts"] = []
                logger.debug(f"Executed batch of {config.batch_size} inserts")
        
        # Execute remaining inserts
        if not config.dry_run and results["inserts"]:
            self._execute_batch(results["inserts"], "INSERT")
            results["stats"]["inserted"] += len(results["inserts"])
        
        # Get row IDs for updates/deletes
        if config.random_pks or not all_inserted_pks:
            row_ids = self._get_random_row_ids(table_name, library, update_count + delete_count)
            logger.info(f"Retrieved {len(row_ids)} random row IDs from database")
        else:
            import random
            row_ids = all_inserted_pks.copy()
            random.shuffle(row_ids)
            logger.info(f"Using {len(row_ids)} row IDs from generated inserts")
            
            if len(row_ids) < update_count + delete_count:
                needed = (update_count + delete_count) - len(row_ids)
                db_ids = self._get_random_row_ids(table_name, library, needed)
                row_ids.extend(db_ids)
                logger.info(f"Retrieved {len(db_ids)} additional row IDs from database to meet requirements")
        
        if len(row_ids) < update_count + delete_count:
            logger.warning(f"Not enough rows for all updates/deletes. Will process {len(row_ids)} rows instead of {update_count + delete_count}")
            # Adjust counts proportionally
            total_needed = update_count + delete_count
            if len(row_ids) > 0:
                ratio = len(row_ids) / total_needed
                update_count = max(1, int(update_count * ratio))
                delete_count = max(0, len(row_ids) - update_count)
                logger.info(f"Adjusted counts: {update_count} updates, {delete_count} deletes")
        
        # Generate UPDATE operations
        for i in range(min(update_count, len(row_ids))):
            pk_values = row_ids[i]  # List of PK values for composite keys
            update_data = self._generate_update_data(columns, pk_columns)
            sql = self._build_update_sql(table_name, library, update_data, pk_columns, pk_values)
            
            if config.dry_run:
                results["sql_statements"].append(sql)
            else:
                results["updates"].append({"pk_values": pk_values, "data": update_data})
            
            if not config.dry_run and (i + 1) % config.batch_size == 0:
                self._execute_batch(results["updates"], "UPDATE", pk_columns)
                results["stats"]["updated"] += len(results["updates"])
                results["updates"] = []
        
        if not config.dry_run and results["updates"]:
            self._execute_batch(results["updates"], "UPDATE", pk_columns)
            results["stats"]["updated"] += len(results["updates"])
        
        # Generate DELETE operations
        delete_ids = row_ids[update_count:update_count + delete_count]
        for i, pk_values in enumerate(delete_ids):
            sql = self._build_delete_sql(table_name, library, pk_columns, pk_values)
            
            if config.dry_run:
                results["sql_statements"].append(sql)
            else:
                results["deletes"].append(pk_values)
            
            if not config.dry_run and (i + 1) % config.batch_size == 0:
                self._execute_batch(results["deletes"], "DELETE", pk_columns)
                results["stats"]["deleted"] += len(results["deletes"])
                results["deletes"] = []
        
        if not config.dry_run and results["deletes"]:
            self._execute_batch(results["deletes"], "DELETE", pk_columns)
            results["stats"]["deleted"] += len(results["deletes"])
        
        return results
    
    def _get_columns(self, table_name: str, library: str) -> list[dict[str, Any]]:
        """Get column information for a table."""
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
        cursor = self.conn.execute(sql, (table_name.upper(), library.upper()))
        columns = []
        for row in cursor.fetchall():
            description = str(row[7]) if row[7] else None
            logger.debug(f"Column {row[1]} description: {description}")
            # Extract hint from description if present (format: "Description [hint:xxx]")
            hint = None
            if description and "[hint:" in description.lower():
                import re
                hint_match = re.search(r'\[hint:([^\]]+)\]', description, re.IGNORECASE)
                if hint_match:
                    hint = hint_match.group(1).strip()
                    logger.debug(f"Extracted hint '{hint}' from description")
                    # Remove hint from description
                    description = re.sub(r'\[hint:[^\]]+\]', '', description, flags=re.IGNORECASE).strip()

            col_name = str(row[1])
            # Merge schema hints with database hints (schema hints take priority)
            final_hint = hint
            if col_name.upper() in self.schema_hints:
                final_hint = self.schema_hints[col_name.upper()]
                logger.debug(f"Using schema hint '{final_hint}' for column {col_name}")

            # Check if column is identity or generated
            is_identity = row[8] == "YES" if row[8] else False
            column_default = str(row[6]) if row[6] else ""
            is_generated = "GENERATED" in column_default.upper()

            columns.append({
                "system_name": str(row[0]),
                "name": col_name,
                "type": str(row[2]),
                "length": row[3],
                "scale": row[4],
                "nullable": row[5] == "YES",
                "default": row[6],
                "description": description,
                "hint": final_hint,
                "is_identity": is_identity,
                "is_generated": is_generated,
                "ccsid": row[9] if len(row) > 9 else None,  # CCSID value
                "is_binary": row[9] == 65535 if len(row) > 9 else False,  # CCSID 65535 = binary
            })
        cursor.close()
        return columns
    
    def _get_primary_key(self, table_name: str, library: str) -> list[str]:
        """Get primary key columns."""
        # Use SYSKEYCST for accurate PK column info - simpler query without JOIN
        sql = """
            SELECT COLUMN_NAME
            FROM QSYS2.SYSKEYCST
            WHERE SYSTEM_TABLE_NAME = ?
            AND SYSTEM_TABLE_SCHEMA = ?
            ORDER BY ORDINAL_POSITION
        """
        try:
            cursor = self.conn.execute(sql, (table_name.upper(), library.upper()))
            pk_columns = [str(row[0]) for row in cursor.fetchall()]
            cursor.close()
            return pk_columns
        except Exception as e:
            logger.warning(f"Could not get primary key: {e}")
            return []
    
    def _get_existing_pk_values(self, table_name: str, library: str,
                                pk_columns: list[str]) -> set:
        """Get existing primary key values to avoid duplicates.
            
        For large tables, this returns an empty set to avoid performance issues.
        PK uniqueness will be handled by catching duplicate key errors.
        """
        if not pk_columns:
            return set()
            
        # Skip fetching all PK values for large tables - too slow
        # Instead, we'll handle duplicates by catching SQL errors
        logger.debug("Skipping full PK value fetch for performance - will handle duplicates via error handling")
        return set()
        
    def _get_random_row_ids(self, table_name: str, library: str,
                           count: int) -> list[list[Any]]:
        """Get random row IDs for updates/deletes using efficient sampling.
        
        Returns list of lists, where each inner list contains values for all PK columns.
        Supports composite primary keys.
        
        Note: IBM i DB2 doesn't support TABLESAMPLE, so we use RAND() instead.
        """
        # Get primary key columns
        pk_columns = self._get_primary_key(table_name, library)
        if not pk_columns:
            logger.warning("No primary key found for random row selection")
            return []
        
        # Build column list for SELECT
        pk_cols_str = ", ".join(pk_columns)
        
        # Get table row count to determine appropriate sampling strategy
        try:
            count_sql = f"SELECT COUNT(*) FROM {library}.{table_name}"
            cursor = self.conn.execute(count_sql)
            total_rows = cursor.fetchone()[0]
            cursor.close()
            logger.debug(f"Table {library}.{table_name} has {total_rows} rows")
        except Exception as e:
            logger.debug(f"Could not get row count: {e}")
            total_rows = None
        
        # IBM i DB2 doesn't support TABLESAMPLE, use RAND() with ORDER BY instead
        # Adjust RAND() threshold based on table size to get enough rows
        if total_rows and total_rows > 0:
            # Target: get at least count * 2 rows to be safe
            target_rows = count * 2
            # RAND() returns 0-1, we want to filter enough rows
            # If table has 1000 rows and we want 100, we need ~10% sample
            rand_threshold = min(0.5, max(0.01, target_rows / total_rows))
            logger.debug(f"Using RAND() with threshold {rand_threshold:.4f}")
        else:
            rand_threshold = 0.1  # Default 10% if we don't know table size
            
        # Method 1: Use RAND() with WHERE clause and ORDER BY RAND()
        sql = f"""
            SELECT {pk_cols_str} FROM {library}.{table_name}
            WHERE RAND() < {rand_threshold}
            ORDER BY RAND()
            FETCH FIRST {count} ROWS ONLY
        """
        try:
            cursor = self.conn.execute(sql)
            rows = [list(row) for row in cursor.fetchall()]
            cursor.close()
            logger.debug(f"RAND() WHERE method returned {len(rows)} rows")
            
            if len(rows) >= count:
                return rows
            elif rows:
                logger.warning(f"Only got {len(rows)} rows from RAND(), need {count}")
                # Continue to fallback
        except Exception as e:
            logger.debug(f"RAND() with WHERE failed: {e}, trying alternative")
            
        # Method 2: Simple ORDER BY RAND() without WHERE (slower but works)
        try:
            sql = f"""
                SELECT {pk_cols_str} FROM {library}.{table_name}
                ORDER BY RAND()
                FETCH FIRST {count} ROWS ONLY
            """
            cursor = self.conn.execute(sql)
            rows = [list(row) for row in cursor.fetchall()]
            cursor.close()
            logger.debug(f"ORDER BY RAND() method returned {len(rows)} rows")
            if rows:
                return rows
        except Exception as e:
            logger.debug(f"ORDER BY RAND() failed: {e}")
            
        # For single-column PK: Final fallback using MIN/MAX range
        if len(pk_columns) == 1:
            try:
                pk_col = pk_columns[0]
                sql = f"SELECT MIN({pk_col}), MAX({pk_col}) FROM {library}.{table_name}"
                cursor = self.conn.execute(sql)
                row = cursor.fetchone()
                cursor.close()
                    
                if row and row[0] is not None and row[1] is not None:
                    min_id, max_id = row[0], row[1]
                    import random
                    random_ids = [random.randint(min_id, max_id) for _ in range(count * 2)]
                    id_list = ",".join(str(id_val) for id_val in random_ids)
                    verify_sql = f"SELECT {pk_col} FROM {library}.{table_name} WHERE {pk_col} IN ({id_list}) FETCH FIRST {count} ROWS ONLY"
                    cursor = self.conn.execute(verify_sql)
                    existing_ids = [[row[0]] for row in cursor.fetchall()]  # Return as list of lists
                    cursor.close()
                    return existing_ids[:count]
            except Exception as e:
                logger.warning(f"MIN/MAX fallback failed: {e}")
            
        return []
    
    def _generate_row(self, columns: list[dict], pk_columns: list[str],
                     existing_pks: set, is_insert: bool = True) -> dict[str, Any]:
        """Generate a row of data."""
        row = {}

        for col in columns:
            col_name = col["name"]

            # Skip identity or generated columns (for INSERTs)
            if is_insert and (col.get("is_identity") or col.get("is_generated")):
                logger.debug(f"Skipping identity/generated column {col_name}")
                continue

            # Skip if column has default value
            if col["default"]:
                continue

            # Generate PK with uniqueness check
            if col_name in pk_columns and is_insert:
                value = self._generate_unique_pk(col, existing_pks)
                existing_pks.add(value)
            else:
                # Pass hint if available
                hint = col.get("hint")
                if hint:
                    logger.debug(f"Using hint '{hint}' for column {col_name}")
                value = self.data_generator.generate_for_column(
                    col_name, col["type"], col["length"], col["scale"], hint, col.get("ccsid")
                )

            row[col_name] = value

        return row
    
    def _generate_unique_pk(self, col: dict, existing_pks: set) -> Any:
        """Generate a unique primary key value."""
        max_attempts = 1000
        for _ in range(max_attempts):
            value = self.data_generator.generate_for_column(
                col["name"], col["type"], col["length"], col["scale"], col.get("hint"), col.get("ccsid")
            )
            if value not in existing_pks:
                return value
        
        # If we can't find a unique value, add timestamp
        import time
        base_value = self.data_generator.generate_for_column(
            col["name"], col["type"], col["length"], col["scale"], col.get("hint"), col.get("ccsid")
        )
        return f"{base_value}_{int(time.time() * 1000)}"
    
    def _generate_update_data(self, columns: list[dict],
                             pk_columns: list[str]) -> dict[str, Any]:
        """Generate data for update (excluding PK columns)."""
        update_data = {}

        # Select random columns to update (excluding PK)
        updatable_cols = [c for c in columns if c["name"] not in pk_columns]
        if not updatable_cols:
            return update_data

        # Update 1-3 random columns
        num_cols = min(random.randint(1, 3), len(updatable_cols))
        cols_to_update = random.sample(updatable_cols, num_cols)

        for col in cols_to_update:
            # Pass hint if available for consistent data generation
            value = self.data_generator.generate_for_column(
                col["name"], col["type"], col["length"], col["scale"], col.get("hint"), col.get("ccsid")
            )
            update_data[col["name"]] = value

        return update_data
    
    def _build_insert_sql(self, table_name: str, library: str, 
                         row_data: dict, 
                         columns: list[dict] = None) -> str:
        """Build INSERT SQL statement.
        
        Args:
            table_name: Target table name
            library: Library/schema name
            row_data: Dictionary of column_name -> value
            columns: Optional list of column metadata dicts (for type detection)
        """
        from datetime import datetime, date
        
        columns_str = ", ".join(row_data.keys())
        values = []
        
        # Build column name -> type mapping if columns metadata provided
        col_type_map = {}
        if columns:
            for col in columns:
                col_type_map[col["name"].upper()] = col["type"].upper()
        
        for col_name, val in row_data.items():
            col_type = col_type_map.get(col_name.upper(), "")
            
            if val is None:
                values.append("NULL")
            elif isinstance(val, str):
                # Check if this is a binary column
                # CCSID 65535 or explicit binary types
                is_binary_col = (
                    "FOR BIT DATA" in col_type or 
                    col_type in ("BINARY", "VARBINARY", "BLOB") or
                    any(c["name"].upper() == col_name.upper() and c.get("is_binary") 
                        for c in (columns or []))
                )
                
                if is_binary_col:
                    # Use DB2 binary literal syntax: X'HEXSTRING'
                    # Ensure value contains only hex characters
                    hex_val = val.upper().replace(' ', '')
                    if all(c in '0123456789ABCDEF' for c in hex_val):
                        values.append(f"X'{hex_val}'")
                    else:
                        # Fallback: treat as regular string if not valid hex
                        escaped = val.replace("'", "''")
                        values.append(f"'{escaped}'")
                else:
                    # Regular string column
                    escaped = val.replace("'", "''")
                    values.append(f"'{escaped}'")
            elif isinstance(val, (int, float)):
                values.append(str(val))
            elif isinstance(val, datetime):
                # Format datetime for DB2: 'YYYY-MM-DD HH:MM:SS.microseconds'
                formatted = val.strftime('%Y-%m-%d %H:%M:%S.%f')
                values.append(f"'{formatted}'")
            elif isinstance(val, date):
                # Format date for DB2: 'YYYY-MM-DD'
                formatted = val.strftime('%Y-%m-%d')
                values.append(f"'{formatted}'")
            else:
                values.append(f"'{str(val)}'")
        
        values_str = ", ".join(values)
        return f"INSERT INTO {library}.{table_name} ({columns_str}) VALUES ({values_str});"
    
    def _build_update_sql(self, table_name: str, library: str,
                         update_data: dict, pk_columns: list[str],
                         pk_values: list[Any]) -> str:
        """Build UPDATE SQL statement.
        
        Supports composite primary keys by using all PK columns in WHERE clause.
        """
        from datetime import datetime, date
        
        if not update_data:
            return ""
        
        set_clauses = []
        for col, val in update_data.items():
            if val is None:
                set_clauses.append(f"{col} = NULL")
            elif isinstance(val, str):
                escaped = val.replace("'", "''")
                set_clauses.append(f"{col} = '{escaped}'")
            elif isinstance(val, (int, float)):
                set_clauses.append(f"{col} = {val}")
            elif isinstance(val, datetime):
                # Format datetime for DB2: 'YYYY-MM-DD HH:MM:SS.microseconds'
                formatted = val.strftime('%Y-%m-%d %H:%M:%S.%f')
                set_clauses.append(f"{col} = '{formatted}'")
            elif isinstance(val, date):
                # Format date for DB2: 'YYYY-MM-DD'
                formatted = val.strftime('%Y-%m-%d')
                set_clauses.append(f"{col} = '{formatted}'")
            else:
                set_clauses.append(f"{col} = '{str(val)}'")
        
        set_str = ", ".join(set_clauses)
        
        # Build WHERE clause with all PK columns (composite key support)
        if pk_columns and pk_values and len(pk_columns) == len(pk_values):
            where_conditions = []
            for col, val in zip(pk_columns, pk_values):
                if isinstance(val, str):
                    escaped_val = val.replace("'", "''")
                    where_conditions.append(f"{col} = '{escaped_val}'")
                else:
                    where_conditions.append(f"{col} = {val}")
            where = " AND ".join(where_conditions)
        elif pk_columns:
            # Fallback to first column only
            where = f"{pk_columns[0]} = {pk_values[0] if pk_values else 0}"
        else:
            where = "1=0"  # Safety: prevent update without PK
        
        return f"UPDATE {library}.{table_name} SET {set_str} WHERE {where};"
    
    def _build_delete_sql(self, table_name: str, library: str,
                         pk_columns: list[str], pk_values: list[Any]) -> str:
        """Build DELETE SQL statement.
        
        Supports composite primary keys by using all PK columns in WHERE clause.
        """
        # Build WHERE clause with all PK columns (composite key support)
        if pk_columns and pk_values and len(pk_columns) == len(pk_values):
            where_conditions = []
            for col, val in zip(pk_columns, pk_values):
                if isinstance(val, str):
                    escaped_val = val.replace("'", "''")
                    where_conditions.append(f"{col} = '{escaped_val}'")
                else:
                    where_conditions.append(f"{col} = {val}")
            where = " AND ".join(where_conditions)
        elif pk_columns:
            # Fallback to first column only
            where = f"{pk_columns[0]} = {pk_values[0] if pk_values else 0}"
        else:
            where = "1=0"  # Safety: prevent delete without PK
        
        return f"DELETE FROM {library}.{table_name} WHERE {where};"
    
    def _execute_batch(self, batch: list, operation: str,
                      pk_columns: Optional[list[str]] = None):
        """Execute a batch of operations with enhanced FK error handling."""
        if not batch:
            return
            
        # Get stored table info
        table_name = getattr(self, '_table_name', '')
        library = getattr(self, '_library', '')
        columns = getattr(self, '_columns', [])  # Get stored columns metadata
        
        # Use agent if available for bulk operations
        if self.agent.is_available():
            return self._execute_batch_via_agent(batch, operation, table_name, library, columns, pk_columns)
        
        # Fallback to direct JT400 (original code)
        # Track FK errors
        fk_errors = []
        other_errors = []
        success_count = 0
            
        try:
            if operation == "INSERT":
                for row_data in batch:
                    try:
                        sql = self._build_insert_sql(table_name, library, row_data, columns)
                        cursor = self.conn.execute(sql.rstrip(';'))
                        cursor.close()
                        success_count += 1
                    except Exception as row_e:
                        error_str = str(row_e).upper()
                        # Check for FK constraint violations
                        if any(kw in error_str for kw in ['FOREIGN KEY', 'CONSTRAINT', 'PARENT KEY', 'PARENT ROW']):
                            fk_errors.append(f"FK violation for row {row_data}: {row_e}")
                            logger.warning(f"FK constraint violation in {library}.{table_name}: {row_e}")
                        else:
                            other_errors.append(f"Error for row {row_data}: {row_e}")
                            raise  # Re-raise non-FK errors
                
            elif operation == "UPDATE":
                for item in batch:
                    pk_values = item["pk_values"]
                    update_data = item["data"]
                    if update_data:
                        try:
                            sql = self._build_update_sql(table_name, library, update_data, pk_columns or [], pk_values)
                            logger.debug(f"UPDATE SQL: {sql}")
                            cursor = self.conn.execute(sql.rstrip(';'))
                            cursor.close()
                            success_count += 1
                        except Exception as row_e:
                            error_str = str(row_e).upper()
                            if any(kw in error_str for kw in ['FOREIGN KEY', 'CONSTRAINT', 'PARENT KEY']):
                                fk_errors.append(f"FK violation for PK {pk_values}: {row_e}")
                                logger.warning(f"FK constraint violation in {library}.{table_name}: {row_e}")
                            else:
                                other_errors.append(f"Error for PK {pk_values}: {row_e}")
                                raise
                
            elif operation == "DELETE":
                for pk_values in batch:
                    try:
                        sql = self._build_delete_sql(table_name, library, pk_columns or [], pk_values)
                        cursor = self.conn.execute(sql.rstrip(';'))
                        cursor.close()
                        success_count += 1
                    except Exception as row_e:
                        error_str = str(row_e).upper()
                        # DELETE often fails due to child records (FK violations)
                        if any(kw in error_str for kw in ['FOREIGN KEY', 'CONSTRAINT', 'CHILD RECORD', 'REFERENTIAL']):
                            fk_errors.append(f"FK violation (child records exist) for PK {pk_values}: {row_e}")
                            logger.warning(f"Cannot delete {library}.{table_name} row {pk_values} - child records exist")
                        else:
                            other_errors.append(f"Error for PK {pk_values}: {row_e}")
                            raise
                
            self.conn.commit()
            
            # Log summary
            total = len(batch)
            failed = len(fk_errors) + len(other_errors)
            logger.info(f"Batch {operation}: {success_count}/{total} succeeded, {failed} failed ({len(fk_errors)} FK errors)")
            
            # Raise exception if there were FK errors (but operation partially succeeded)
            if fk_errors and success_count == 0:
                raise Exception(f"All {operation} operations failed due to FK constraints. First error: {fk_errors[0]}")
            elif fk_errors:
                logger.warning(f"Partial success: {success_count}/{total} {operation} operations succeeded. {len(fk_errors)} FK constraint violations ignored.")
            
        except Exception as e:
            logger.error(f"Error executing batch {operation}: {e}")
            raise
    
    def _execute_batch_via_agent(self, batch: list, operation: str, table_name: str, library: str, 
                                 columns: list, pk_columns: Optional[list[str]] = None) -> None:
        """Execute batch operations via AS400 Agent (FAST!)."""
        try:
            col_type_map = {col["name"].upper(): col for col in columns}
            
            if operation == "INSERT":
                # Build parameterized insert SQL
                keys = list(batch[0].keys())
                columns_str = ", ".join(keys)
                placeholders = ", ".join(["?"] * len(keys))
                sql = f"INSERT INTO {library}.{table_name} ({columns_str}) VALUES ({placeholders})"
                
                # Format parameters, wrapping binary columns in bytes serialization
                rows_list = []
                for row_data in batch:
                    row_vals = []
                    for key in keys:
                        val = row_data[key]
                        col = col_type_map.get(key.upper(), {})
                        col_type = col.get("type", "").upper()
                        is_binary_col = (
                            "FOR BIT DATA" in col_type or 
                            col_type in ("BINARY", "VARBINARY", "BLOB") or
                            col.get("is_binary", False)
                        )
                        if is_binary_col and isinstance(val, str):
                            val = {"__type__": "bytes", "value": val.upper().replace(' ', '')}
                        row_vals.append(val)
                    rows_list.append(row_vals)
                
                # Send to agent
                result = self.agent.mockup_insert(sql, rows_list, library)
                logger.info(f"Agent INSERT: {result['rows_affected']} rows in {result['execution_time_ms']:.0f}ms")
                
            elif operation == "UPDATE":
                groups = {}
                for item in batch:
                    cols = tuple(sorted(item["data"].keys()))
                    if not cols:
                        continue
                    groups.setdefault(cols, []).append(item)
                
                for cols, group_batch in groups.items():
                    set_clauses = ", ".join([f"{col} = ?" for col in cols])
                    where_clauses = " AND ".join([f"{col} = ?" for col in pk_columns])
                    sql = f"UPDATE {library}.{table_name} SET {set_clauses} WHERE {where_clauses}"
                    
                    updates = []
                    for item in group_batch:
                        param_dict = {}
                        idx = 1
                        for col_name in cols:
                            val = item["data"][col_name]
                            col = col_type_map.get(col_name.upper(), {})
                            col_type = col.get("type", "").upper()
                            is_binary_col = (
                                "FOR BIT DATA" in col_type or 
                                col_type in ("BINARY", "VARBINARY", "BLOB") or
                                col.get("is_binary", False)
                            )
                            if is_binary_col and isinstance(val, str):
                                val = {"__type__": "bytes", "value": val.upper().replace(' ', '')}
                            param_dict[str(idx)] = val
                            idx += 1
                        
                        for pk_val in item["pk_values"]:
                            param_dict[str(idx)] = pk_val
                            idx += 1
                        updates.append(param_dict)
                    
                    result = self.agent.mockup_update(sql, updates, library)
                    logger.info(f"Agent UPDATE: {result['rows_affected']} rows in {result['execution_time_ms']:.0f}ms")
                
            elif operation == "DELETE":
                where_clauses = " AND ".join([f"{col} = ?" for col in pk_columns])
                sql = f"DELETE FROM {library}.{table_name} WHERE {where_clauses}"
                
                params = []
                for pk_values in batch:
                    param_dict = {}
                    for idx, val in enumerate(pk_values, 1):
                        param_dict[str(idx)] = val
                    params.append(param_dict)
                
                result = self.agent.execute_batch(sql, params, library)
                logger.info(f"Agent DELETE: {result['rows_affected']} rows in {result['execution_time_ms']:.0f}ms")
                
        except Exception as e:
            logger.error(f"Agent batch {operation} failed: {e}")
            raise
