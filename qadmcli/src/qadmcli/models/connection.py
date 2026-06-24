"""Connection configuration models."""

import os
import re
from typing import Any

from pydantic import BaseModel, Field, field_validator


class AS400Connection(BaseModel):
    """AS400 connection settings."""

    host: str = Field(..., description="AS400 hostname or IP address")
    user: str = Field(..., description="AS400 username")
    password: str = Field(..., description="AS400 password")
    port: int = Field(default=8471, description="DRDA port (default: 8471)")
    ssl: bool = Field(default=True, description="Use SSL connection")
    database: str = Field(default="*LOCAL", description="Database name")
    
    def copy_with_overrides(self, user: str = None, password: str = None) -> "AS400Connection":
        """Create a copy with credential overrides."""
        return AS400Connection(
            host=self.host,
            user=user or self.user,
            password=password or self.password,
            port=self.port,
            ssl=self.ssl,
            database=self.database
        )
    
    @field_validator("host")
    @classmethod
    def validate_host(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Host cannot be empty")
        return v.strip()

    @field_validator("user", "password")
    @classmethod
    def validate_credentials(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Credentials cannot be empty")
        return v.strip()


class MSSQLConnection(BaseModel):
    """MSSQL connection settings."""

    host: str = Field(..., description="MSSQL server hostname or IP")
    port: int = Field(default=1433, description="MSSQL port (default: 1433)")
    username: str = Field(..., description="MSSQL username")
    password: str = Field(..., description="MSSQL password")
    database: str = Field(default="master", description="Default database")

    def copy_with_overrides(self, username: str = None, password: str = None) -> "MSSQLConnection":
        """Create a copy with credential overrides."""
        return MSSQLConnection(
            host=self.host,
            port=self.port,
            username=username or self.username,
            password=password or self.password,
            database=self.database
        )

    @field_validator("host")
    @classmethod
    def validate_host(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Host cannot be empty")
        return v.strip()



class MySQLConnection(BaseModel):
    """MySQL connection settings."""

    host: str = Field(..., description="MySQL server hostname or IP")
    port: int = Field(default=3306, description="MySQL port (default: 3306)")
    username: str = Field(..., description="MySQL username")
    password: str = Field(..., description="MySQL password")
    database: str = Field(default="mysql", description="Default database")

    def copy_with_overrides(self, username: str = None, password: str = None) -> "MySQLConnection":
        """Create a copy with credential overrides."""
        return MySQLConnection(
            host=self.host,
            port=self.port,
            username=username or self.username,
            password=password or self.password,
            database=self.database
        )

    @field_validator("host")
    @classmethod
    def validate_host(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Host cannot be empty")
        return v.strip()


class OracleConnection(BaseModel):
    """Oracle connection settings."""

    host: str = Field(..., description="Oracle server hostname or IP")
    port: int = Field(default=1521, description="Oracle port (default: 1521)")
    username: str = Field(..., description="Oracle username")
    password: str = Field(..., description="Oracle password")
    service_name: str = Field(..., description="Oracle Service Name")

    def copy_with_overrides(self, username: str = None, password: str = None) -> "OracleConnection":
        """Create a copy with credential overrides."""
        return OracleConnection(
            host=self.host,
            port=self.port,
            username=username or self.username,
            password=password or self.password,
            service_name=self.service_name
        )

    @field_validator("host")
    @classmethod
    def validate_host(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Host cannot be empty")
        return v.strip()


class DefaultsConfig(BaseModel):
    """Default settings."""

    library: str = Field(default="QGPL", description="Default library/schema")
    journal_library: str = Field(default="QSYS2", description="Default journal library")
    journal_name: str = Field(default="QSQJRN", description="Default journal name")


class LoggingConfig(BaseModel):
    """Logging configuration."""

    level: str = Field(default="INFO", description="Log level")
    format: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        description="Log format string"
    )


class ConnectionConfig(BaseModel):
    """Root connection configuration."""

    as400: AS400Connection | None = Field(default=None, description="Optional AS400 connection")
    mssql: MSSQLConnection | None = Field(default=None, description="Optional MSSQL connection")
    mysql: MySQLConnection | None = Field(default=None, description="Optional MySQL connection")
    oracle: OracleConnection | None = Field(default=None, description="Optional Oracle connection")
    defaults: DefaultsConfig = Field(default_factory=DefaultsConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    @classmethod
    def from_yaml(cls, config_path: str) -> "ConnectionConfig":
        """Load configuration from YAML file with environment variable substitution."""
        import yaml
        
        with open(config_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Track optional sections that should be removed if env vars are missing
        optional_sections: dict[str, list[str]] = {}
        
        # Substitute environment variables: ${VAR}, ${VAR:-default}, or ${VAR:?} (optional)
        def env_substitute(match: Any) -> str:
            var_expr = match.group(1)
            if ":-" in var_expr:
                var_name, default = var_expr.split(":-", 1)
                return os.environ.get(var_name, default)
            if ":?" in var_expr:
                # Optional variable - return special marker if not set
                var_name = var_expr[:-2]
                return os.environ.get(var_name, "__OPTIONAL_UNSET__")
            return os.environ.get(var_expr, "")
        
        content = re.sub(r"\$\{([^}]+)\}", env_substitute, content)
        data = yaml.safe_load(content)
        
        # Remove optional sections that have unset credential values
        if data.get("mssql"):
            mssql_data = data["mssql"]
            username = mssql_data.get("username", "")
            password = mssql_data.get("password", "")
            if (not username or username == "__OPTIONAL_UNSET__") and \
               (not password or password == "__OPTIONAL_UNSET__"):
                data["mssql"] = None

        if data.get("mysql"):
            mysql_data = data["mysql"]
            username = mysql_data.get("username", "")
            password = mysql_data.get("password", "")
            if (not username or username == "__OPTIONAL_UNSET__") and \
               (not password or password == "__OPTIONAL_UNSET__"):
                data["mysql"] = None

        if data.get("oracle"):
            oracle_data = data["oracle"]
            username = oracle_data.get("username", "")
            password = oracle_data.get("password", "")
            if (not username or username == "__OPTIONAL_UNSET__") and \
               (not password or password == "__OPTIONAL_UNSET__"):
                data["oracle"] = None
        
        return cls(**data)
    
    def get_jdbc_url(self) -> str:
        """Generate JDBC URL for jt400."""
        ssl_param = ";ssl=true" if self.as400.ssl else ""
        return (
            f"jdbc:as400://{self.as400.host}:{self.as400.port}"
            f"/{self.as400.database}{ssl_param}"
        )
    
    def get_connection_properties(self) -> dict[str, str]:
        """Get connection properties for jt400."""
        props = {
            "user": self.as400.user,
            "password": self.as400.password,
            "libraries": self.defaults.library,
        }
        if self.as400.ssl:
            props["ssl"] = "true"
        return props
