"""Configuration loader."""

from pathlib import Path

from .models.connection import ConnectionConfig


def load_config(config_path: Path) -> ConnectionConfig:
    """Load connection configuration from YAML file."""
    return ConnectionConfig.from_yaml(str(config_path))
