"""Table configuration models."""

from typing import Any

from pydantic import BaseModel, Field, field_validator


class Column(BaseModel):
    """Table column definition."""

    name: str = Field(..., description="Column name")
    type: str = Field(..., description="DB2 data type (VARCHAR, DECIMAL, INTEGER, etc.)")
    length: int | None = Field(default=None, description="Length/precision")
    scale: int | None = Field(default=None, description="Scale for decimal types")
    nullable: bool = Field(default=True, description="Allow NULL values")
    default: str | None = Field(default=None, description="Default value expression")
    description: str | None = Field(default=None, description="Column description")

    @field_validator("name", "type")
    @classmethod
    def validate_uppercase(cls, v: str) -> str:
        if v:
            return v.upper()
        return v


class Constraint(BaseModel):
    """Table constraint definition."""

    primary_key: dict[str, Any] | None = Field(
        default=None, 
        description="Primary key constraint with 'columns' and optional 'name'"
    )
    unique: list[dict[str, Any]] | None = Field(
        default=None,
        description="List of unique constraints"
    )
    foreign_keys: list[dict[str, Any]] | None = Field(
        default=None,
        description="List of foreign key constraints"
    )
    check: list[dict[str, Any]] | None = Field(
        default=None,
        description="List of check constraints"
    )


class JournalingConfig(BaseModel):
    """Journaling configuration for table."""

    enabled: bool = Field(default=True, description="Enable journaling")
    journal_library: str | None = Field(
        default=None, 
        description="Journal library (uses default if not specified)"
    )
    journal_name: str | None = Field(
        default=None,
        description="Journal name (uses default if not specified)"
    )


class TableConfig(BaseModel):
    """Table configuration from YAML."""

    table: dict[str, Any] = Field(..., description="Table metadata")
    columns: list[Column] = Field(..., description="List of column definitions")
    constraints: Constraint | None = Field(
        default=None, 
        description="Table constraints"
    )
    journaling: JournalingConfig = Field(
        default_factory=JournalingConfig,
        description="Journaling configuration"
    )
    indexes: list[dict[str, Any]] | None = Field(
        default=None,
        description="List of index definitions"
    )

    @property
    def name(self) -> str:
        return self.table.get("name", "").upper()

    @property
    def library(self) -> str:
        return self.table.get("library", "QGPL").upper()

    @property
    def description(self) -> str | None:
        return self.table.get("description")

    @classmethod
    def from_yaml(cls, config_path: str) -> "TableConfig":
        """Load table configuration from YAML file."""
        import yaml
        
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        
        return cls(**data)

    def to_sql_ddl(self) -> str:
        """Generate CREATE TABLE SQL statement."""
        lines = []
        
        # Header
        table_name = f"{self.library}.{self.name}"
        lines.append(f"CREATE TABLE {table_name} (")
        
        # Columns
        column_defs = []
        for col in self.columns:
            col_def = self._format_column(col)
            column_defs.append(f"    {col_def}")
        lines.append(",\n".join(column_defs))
        
        # Constraints
        if self.constraints:
            constraint_sql = self._format_constraints()
            if constraint_sql:
                lines.append(",")
                lines.append(constraint_sql)
        
        lines.append(")")
        
        # Table description - separate statement with semicolon
        if self.description:
            lines.append(f";\nLABEL ON TABLE {table_name} IS '{self.description}'")
        
        # Column descriptions - separate statements with semicolons
        for col in self.columns:
            if col.description:
                lines.append(
                    f";\nLABEL ON COLUMN {table_name}.{col.name} "
                    f"IS '{col.description}'"
                )
        
        # End with semicolon
        lines.append(";")
        
        return "\n".join(lines)

    def _format_column(self, col: Column) -> str:
        """Format a single column definition."""
        parts = [col.name]
        
        # Type definition
        if col.type in ("VARCHAR", "CHAR", "VARBINARY", "BINARY"):
            parts.append(f"{col.type}({col.length or 50})")
        elif col.type in ("DECIMAL", "DEC", "NUMERIC"):
            parts.append(f"{col.type}({col.length or 10}, {col.scale or 0})")
        else:
            parts.append(col.type)
        
        # Nullability
        if not col.nullable:
            parts.append("NOT NULL")
        
        # Default value
        if col.default is not None:
            parts.append(f"DEFAULT {col.default}")
        
        return " ".join(parts)

    def _format_constraints(self) -> str | None:
        """Format table constraints."""
        constraints = []
        
        if self.constraints and self.constraints.primary_key:
            pk = self.constraints.primary_key
            pk_name = pk.get("name", f"PK_{self.name}")
            pk_cols = ", ".join(pk.get("columns", []))
            constraints.append(f"    CONSTRAINT {pk_name} PRIMARY KEY ({pk_cols})")
        
        return ",\n".join(constraints) if constraints else None


class TableInfo(BaseModel):
    """Table information from system catalogs."""

    name: str  # System name (short name)
    sql_name: str | None = None  # SQL name (long name)
    library: str
    table_type: str
    description: str | None = None
    row_count: int | None = None
    created: str | None = None
    last_altered: str | None = None
    journaled: bool = False
    journal_library: str | None = None
    journal_name: str | None = None
