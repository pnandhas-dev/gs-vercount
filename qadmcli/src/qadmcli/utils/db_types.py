"""Database type mappings for cross-database schema conversion."""

from typing import Optional


class DatabaseType:
    """Represents a database column type."""

    def __init__(
        self,
        db_type: str,
        length: Optional[int] = None,
        scale: Optional[int] = None,
        nullable: bool = True,
        default: Optional[str] = None,
        identity: bool = False,
        extra: Optional[dict] = None
    ):
        self.db_type = db_type.upper()
        self.length = length
        self.scale = scale
        self.nullable = nullable
        self.default = default
        self.identity = identity
        self.extra = extra or {}

    def __repr__(self):
        if self.scale is not None:
            return f"{self.db_type}({self.length},{self.scale})"
        elif self.length is not None:
            return f"{self.db_type}({self.length})"
        return self.db_type


class TypeMapper:
    """Maps database types between different database systems."""

    # DB2 for i to MSSQL mappings
    DB2_TO_MSSQL = {
        # Character types
        "CHAR": ("CHAR", None, None),
        "VARCHAR": ("VARCHAR", None, None),
        "NCHAR": ("NCHAR", None, None),
        "NVARCHAR": ("NVARCHAR", None, None),
        "GRAPHIC": ("NCHAR", None, None),
        "VARGRAPHIC": ("NVARCHAR", None, None),
        "CLOB": ("VARCHAR", "MAX", None),
        "DBCLOB": ("NVARCHAR", "MAX", None),

        # Numeric types
        "SMALLINT": ("SMALLINT", None, None),
        "INTEGER": ("INT", None, None),
        "BIGINT": ("BIGINT", None, None),
        "DECIMAL": ("DECIMAL", None, None),
        "NUMERIC": ("NUMERIC", None, None),
        "DECFLOAT": ("FLOAT", None, None),
        "REAL": ("REAL", None, None),
        "DOUBLE": ("FLOAT", None, None),
        "FLOAT": ("FLOAT", None, None),

        # Date/Time types
        "DATE": ("DATE", None, None),
        "TIME": ("TIME", None, None),
        "TIMESTAMP": ("DATETIME2", None, None),
        "TIMESTMP": ("DATETIME2", None, None),  # DB2 shorthand

        # Binary types
        "BINARY": ("BINARY", None, None),
        "VARBINARY": ("VARBINARY", None, None),
        "BLOB": ("VARBINARY", "MAX", None),

        # Row ID
        "ROWID": ("UNIQUEIDENTIFIER", None, None),
    }

    # DB2 for i to MySQL mappings
    DB2_TO_MYSQL = {
        # Character types
        "CHAR": ("CHAR", None, None),
        "VARCHAR": ("VARCHAR", None, None),
        "NCHAR": ("CHAR", None, None),
        "NVARCHAR": ("VARCHAR", None, None),
        "GRAPHIC": ("CHAR", None, None),
        "VARGRAPHIC": ("VARCHAR", None, None),
        "CLOB": ("LONGTEXT", None, None),
        "DBCLOB": ("LONGTEXT", None, None),

        # Numeric types
        "SMALLINT": ("SMALLINT", None, None),
        "INTEGER": ("INT", None, None),
        "BIGINT": ("BIGINT", None, None),
        "DECIMAL": ("DECIMAL", None, None),
        "NUMERIC": ("DECIMAL", None, None),
        "DECFLOAT": ("DOUBLE", None, None),
        "REAL": ("FLOAT", None, None),
        "DOUBLE": ("DOUBLE", None, None),
        "FLOAT": ("DOUBLE", None, None),

        # Date/Time types
        "DATE": ("DATE", None, None),
        "TIME": ("TIME", None, None),
        "TIMESTAMP": ("DATETIME", None, None),
        "TIMESTMP": ("DATETIME", None, None),

        # Binary types
        "BINARY": ("BINARY", None, None),
        "VARBINARY": ("VARBINARY", None, None),
        "BLOB": ("LONGBLOB", None, None),
        "ROWID": ("VARCHAR", 36, None),
    }

    # DB2 for i to Oracle mappings
    DB2_TO_ORACLE = {
        # Character types
        "CHAR": ("CHAR", None, None),
        "VARCHAR": ("VARCHAR2", None, None),
        "NCHAR": ("NCHAR", None, None),
        "NVARCHAR": ("NVARCHAR2", None, None),
        "GRAPHIC": ("NCHAR", None, None),
        "VARGRAPHIC": ("NVARCHAR2", None, None),
        "CLOB": ("CLOB", None, None),
        "DBCLOB": ("NCLOB", None, None),

        # Numeric types
        "SMALLINT": ("NUMBER", 5, 0),
        "INTEGER": ("NUMBER", 10, 0),
        "BIGINT": ("NUMBER", 19, 0),
        "DECIMAL": ("NUMBER", None, None),
        "NUMERIC": ("NUMBER", None, None),
        "DECFLOAT": ("NUMBER", None, None),
        "REAL": ("BINARY_FLOAT", None, None),
        "DOUBLE": ("BINARY_DOUBLE", None, None),
        "FLOAT": ("FLOAT", None, None),

        # Date/Time types
        "DATE": ("DATE", None, None),
        "TIME": ("VARCHAR2", 8, None),  # Oracle doesn't have raw TIME, store as string HH:MM:SS
        "TIMESTAMP": ("TIMESTAMP", None, None),
        "TIMESTMP": ("TIMESTAMP", None, None),

        # Binary types
        "BINARY": ("RAW", None, None),
        "VARBINARY": ("RAW", None, None),
        "BLOB": ("BLOB", None, None),
        "ROWID": ("ROWID", None, None),
    }

    # MSSQL to DB2 for i mappings
    MSSQL_TO_DB2 = {
        # Character types
        "CHAR": ("CHAR", None, None),
        "VARCHAR": ("VARCHAR", None, None),
        "NCHAR": ("NCHAR", None, None),
        "NVARCHAR": ("NVARCHAR", None, None),
        "TEXT": ("CLOB", None, None),
        "NTEXT": ("DBCLOB", None, None),

        # Numeric types
        "TINYINT": ("SMALLINT", None, None),  # DB2 has no TINYINT
        "SMALLINT": ("SMALLINT", None, None),
        "INT": ("INTEGER", None, None),
        "BIGINT": ("BIGINT", None, None),
        "DECIMAL": ("DECIMAL", None, None),
        "NUMERIC": ("NUMERIC", None, None),
        "MONEY": ("DECIMAL", 19, 4),
        "SMALLMONEY": ("DECIMAL", 10, 4),
        "FLOAT": ("DOUBLE", None, None),
        "REAL": ("REAL", None, None),

        # Date/Time types
        "DATE": ("DATE", None, None),
        "TIME": ("TIME", None, None),
        "DATETIME": ("TIMESTAMP", None, None),
        "DATETIME2": ("TIMESTAMP", None, None),
        "SMALLDATETIME": ("TIMESTAMP", None, None),
        "DATETIMEOFFSET": ("TIMESTAMP", None, None),

        # Binary types
        "BINARY": ("BINARY", None, None),
        "VARBINARY": ("VARBINARY", None, None),
        "IMAGE": ("BLOB", None, None),

        # Other
        "UNIQUEIDENTIFIER": ("CHAR", 36, None),  # UUID stored as CHAR(36)
        "BIT": ("SMALLINT", None, None),  # DB2 has no BIT type
        "XML": ("CLOB", None, None),
    }

    @classmethod
    def db2_to_mssql(cls, db2_type: DatabaseType) -> DatabaseType:
        """Convert DB2 for i type to MSSQL type."""
        type_key = db2_type.db_type.upper()

        if type_key not in cls.DB2_TO_MSSQL:
            # Unknown type - return as-is with warning
            return db2_type

        mssql_type, default_length, default_scale = cls.DB2_TO_MSSQL[type_key]

        # Determine length
        length = db2_type.length
        if default_length == "MAX":
            length = "MAX"
        elif length is None and default_length is not None:
            length = default_length

        # Determine scale
        scale = db2_type.scale
        if scale is None and default_scale is not None:
            scale = default_scale

        # Handle special cases
        extra = db2_type.extra.copy()

        # DB2 DECIMAL with 0 scale -> MSSQL INT if length <= 10
        if type_key == "DECIMAL" and scale == 0:
            if length and length <= 10:
                return DatabaseType(
                    "INT",
                    nullable=db2_type.nullable,
                    default=db2_type.default,
                    extra=extra
                )
            elif length and length <= 19:
                return DatabaseType(
                    "BIGINT",
                    nullable=db2_type.nullable,
                    default=db2_type.default,
                    extra=extra
                )

        # DB2 IDENTITY -> MSSQL IDENTITY
        if db2_type.identity:
            extra["identity"] = True
            extra["seed"] = db2_type.extra.get("seed", 1)
            extra["increment"] = db2_type.extra.get("increment", 1)

        return DatabaseType(
            mssql_type,
            length=length,
            scale=scale,
            nullable=db2_type.nullable,
            default=cls._convert_default(db2_type.default, "DB2", "MSSQL"),
            extra=extra
        )

    @classmethod
    def db2_to_mysql(cls, db2_type: DatabaseType) -> DatabaseType:
        """Convert DB2 for i type to MySQL type."""
        type_key = db2_type.db_type.upper()

        if type_key not in cls.DB2_TO_MYSQL:
            return db2_type

        mysql_type, default_length, default_scale = cls.DB2_TO_MYSQL[type_key]

        length = db2_type.length
        if length is None and default_length is not None:
            length = default_length

        scale = db2_type.scale
        if scale is None and default_scale is not None:
            scale = default_scale

        extra = db2_type.extra.copy()
        if db2_type.identity:
            extra["identity"] = True

        return DatabaseType(
            mysql_type,
            length=length,
            scale=scale,
            nullable=db2_type.nullable,
            default=cls._convert_default(db2_type.default, "DB2", "MYSQL"),
            extra=extra
        )

    @classmethod
    def db2_to_oracle(cls, db2_type: DatabaseType) -> DatabaseType:
        """Convert DB2 for i type to Oracle type."""
        type_key = db2_type.db_type.upper()

        if type_key not in cls.DB2_TO_ORACLE:
            return db2_type

        oracle_type, default_length, default_scale = cls.DB2_TO_ORACLE[type_key]

        length = db2_type.length
        if length is None and default_length is not None:
            length = default_length

        scale = db2_type.scale
        if scale is None and default_scale is not None:
            scale = default_scale

        extra = db2_type.extra.copy()
        if db2_type.identity:
            extra["identity"] = True

        return DatabaseType(
            oracle_type,
            length=length,
            scale=scale,
            nullable=db2_type.nullable,
            default=cls._convert_default(db2_type.default, "DB2", "ORACLE"),
            extra=extra
        )

    @classmethod
    def mssql_to_db2(cls, mssql_type: DatabaseType) -> DatabaseType:
        """Convert MSSQL type to DB2 for i type."""
        type_key = mssql_type.db_type.upper()

        if type_key not in cls.MSSQL_TO_DB2:
            # Unknown type - return as-is with warning
            return mssql_type

        db2_type, default_length, default_scale = cls.MSSQL_TO_DB2[type_key]

        # Determine length
        length = mssql_type.length
        if length == "MAX":
            length = None  # DB2 uses CLOB/DBCLOB for MAX
        elif length is None and default_length is not None:
            length = default_length

        # Determine scale
        scale = mssql_type.scale
        if scale is None and default_scale is not None:
            scale = default_scale

        # Handle special cases
        extra = mssql_type.extra.copy()

        # MSSQL IDENTITY -> DB2 GENERATED ALWAYS AS IDENTITY
        if mssql_type.identity or extra.get("identity"):
            extra["generated"] = "ALWAYS"
            extra["identity"] = True
            extra["start_with"] = extra.get("seed", 1)
            extra["increment_by"] = extra.get("increment", 1)

        # MSSQL NVARCHAR -> DB2 NVARCHAR (if CCSID 1200/1208)
        if type_key == "NVARCHAR" and length and length > 16369:
            # DB2 NVARCHAR max is 16369, use NCHAR for larger
            db2_type = "NCHAR"

        return DatabaseType(
            db2_type,
            length=length,
            scale=scale,
            nullable=mssql_type.nullable,
            default=cls._convert_default(mssql_type.default, "MSSQL", "DB2"),
            extra=extra
        )

    @classmethod
    def _convert_default(cls, default: Optional[str], from_db: str, to_db: str) -> Optional[str]:
        """Convert default value between databases."""
        if default is None:
            return None

        default_upper = default.upper().strip()

        # Common conversions
        if from_db == "DB2":
            if to_db == "MSSQL":
                # DB2 CURRENT_TIMESTAMP -> MSSQL GETDATE()
                if "CURRENT_TIMESTAMP" in default_upper:
                    return "GETDATE()"
                # DB2 CURRENT_DATE -> MSSQL CAST(GETDATE() AS DATE)
                if "CURRENT_DATE" in default_upper:
                    return "CAST(GETDATE() AS DATE)"
                # DB2 CURRENT_TIME -> MSSQL CAST(GETDATE() AS TIME)
                if "CURRENT_TIME" in default_upper:
                    return "CAST(GETDATE() AS TIME)"
                # DB2 GENERATED ALWAYS -> handled separately
                if "GENERATED" in default_upper:
                    return None

        elif from_db == "MSSQL":
            if to_db == "DB2":
                # MSSQL GETDATE() -> DB2 CURRENT_TIMESTAMP
                if "GETDATE" in default_upper:
                    return "CURRENT_TIMESTAMP"
                # MSSQL NEWID() -> DB2 GENERATE_UUID()
                if "NEWID" in default_upper:
                    return "GENERATE_UUID()"
                # MSSQL IDENTITY -> handled separately
                if "IDENTITY" in default_upper:
                    return None

        return default


class SchemaConverter:
    """Converts table schemas between database systems."""

    def __init__(self, source_db: str, target_db: str):
        """
        Initialize converter.

        Args:
            source_db: Source database type ("DB2", "MSSQL", "MYSQL", or "ORACLE")
            target_db: Target database type ("DB2", "MSSQL", "MYSQL", or "ORACLE")
        """
        self.source_db = source_db.upper()
        self.target_db = target_db.upper()

    def convert_column(self, col_name: str, source_type: DatabaseType) -> DatabaseType:
        """Convert a single column type."""
        if self.source_db == "DB2":
            if self.target_db == "MSSQL":
                return TypeMapper.db2_to_mssql(source_type)
            elif self.target_db == "MYSQL":
                return TypeMapper.db2_to_mysql(source_type)
            elif self.target_db == "ORACLE":
                return TypeMapper.db2_to_oracle(source_type)
        elif self.source_db == "MSSQL" and self.target_db == "DB2":
            return TypeMapper.mssql_to_db2(source_type)
        
        # Default fallback: return as-is
        return source_type

    def convert_schema(self, columns: list[dict]) -> list[dict]:
        """Convert multiple columns."""
        converted = []
        for col in columns:
            source_type = DatabaseType(
                db_type=col.get("type", "VARCHAR"),
                length=col.get("length"),
                scale=col.get("scale"),
                nullable=col.get("nullable", True),
                default=col.get("default"),
                identity=col.get("identity", False),
                extra=col.get("extra", {})
            )

            target_type = self.convert_column(col.get("name", ""), source_type)

            converted_col = {
                "name": col.get("name"),
                "type": target_type.db_type,
                "length": target_type.length,
                "scale": target_type.scale,
                "nullable": target_type.nullable,
                "default": target_type.default,
                "identity": target_type.identity,
                "extra": target_type.extra,
                "description": col.get("description"),
            }

            converted.append(converted_col)

        return converted
