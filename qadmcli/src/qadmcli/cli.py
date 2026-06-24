"""QADM CLI - Main entry point."""

import getpass
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from . import __version__
from .config import load_config
from .db.connection import AS400ConnectionManager, ConnectionError
from .db.schema import SchemaManager
from .db.journal import JournalManager
from .db.mssql import MSSQLConnection, MSSQLManager, MSSQLError
from .models.connection import MSSQLConnection as MSSQLConnectionModel
from .models.table import TableConfig
from .utils.logger import setup_logging
from .utils.formatters import print_table, print_json, print_json_clean, print_ascii_panel
from .utils.db_types import SchemaConverter, DatabaseType

# Import command modules
from .cli_commands import register_all_commands

console = Console()

# Default config path
DEFAULT_CONFIG = Path("config/connection.yaml")


def _get_elevated_connection(
    config: Any,
    admin_user: str | None,
    admin_password: str | None,
    reason: str = "Elevated privileges required"
) -> AS400ConnectionManager | None:
    """Get an elevated connection using admin credentials.
    
    Prompts interactively if credentials not provided via command line.
    Returns None if user cancels or credentials are invalid.
    """
    console.print(f"\n[cyan]Administrative credentials required: {reason}[/cyan]")
    
    # Use provided credentials or prompt interactively
    if not admin_user:
        admin_user = console.input("Admin user: ").strip()
        if not admin_user:
            return None
    
    if not admin_password:
        # Try getpass first (for secure input), fallback to console.input
        try:
            admin_password = getpass.getpass("Admin password: ")
        except (EOFError, OSError):
            # Non-TTY environment (e.g., piped input), use console input
            admin_password = console.input("Admin password (visible): ", password=True)
        if not admin_password:
            return None
    
    # Create temporary config with admin credentials
    from .models.connection import ConnectionConfig, AS400Connection, DefaultsConfig
    admin_as400_config = AS400Connection(
        host=config.as400.host,
        port=config.as400.port,
        user=admin_user,
        password=admin_password,
        database=getattr(config.as400, 'database', '*LOCAL'),
        ssl=getattr(config.as400, 'ssl', True)
    )
    # Wrap in full ConnectionConfig
    admin_config = ConnectionConfig(
        as400=admin_as400_config,
        defaults=getattr(config, 'defaults', DefaultsConfig())
    )
    
    try:
        # Create and test the elevated connection
        admin_conn = AS400ConnectionManager(admin_config)
        admin_conn.connect()
        console.print(f"[green]Connected as {admin_user} with elevated privileges[/green]\n")
        return admin_conn
    except Exception as e:
        console.print(f"[red]Failed to connect as {admin_user}: {e}[/red]")
        return None


def print_panel(
    ctx: click.Context,
    content: str | Text,
    title: str | None = None,
    border_style: str = "blue"
) -> None:
    """Print content in a panel with border style from context.
    
    Uses unicode (Rich Panel) or ascii (print_ascii_panel) based on
    the --border-style CLI option.
    """
    border_style_opt = ctx.obj.get("border_style", "unicode")
    
    if border_style_opt == "ascii":
        print_ascii_panel(console, content, title=title, border_style=border_style)
    else:
        console.print(Panel(content, title=title, border_style=border_style))


def get_config_path(ctx: click.Context, param: Any, value: str | None) -> Path | None:
    """Resolve config path."""
    if value:
        # Explicit -c was given, must exist
        path = Path(value)
        if not path.exists():
            raise click.BadParameter(f"Config file not found: {path}")
        return path
    
    # Try environment variable first
    env_config = os.environ.get("QADMCLI_CONFIG")
    if env_config:
        path = Path(env_config)
        if path.exists():
            return path
        # Env var points to missing file — silently ignore,
        # caller commands that need config will handle None
        return None
    
    # Default path — return None if missing (commands that need config will error)
    if DEFAULT_CONFIG.exists():
        return DEFAULT_CONFIG
    return None


@click.group()
@click.version_option(version=__version__, prog_name="qadmcli")
@click.option(
    "--config", "-c",
    type=click.Path(path_type=Path),
    callback=get_config_path,
    help="Path to connection config file (default: config/connection.yaml)"
)
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
@click.option(
    "--border-style", "-b",
    type=click.Choice(["unicode", "ascii"], case_sensitive=False),
    default="unicode",
    help="Border style for panels: unicode (default) or ascii (for Windows/PowerShell)"
)
@click.pass_context
def cli(ctx: click.Context, config: Path | None, verbose: bool, border_style: str) -> None:
    """QADM CLI - AS400 DB2 for i Database Management Tool."""
    # Ensure context object exists
    ctx.ensure_object(dict)
    
    # Store options in context
    ctx.obj["config_path"] = config
    ctx.obj["verbose"] = verbose
    ctx.obj["border_style"] = border_style.lower()
    
    # Setup logging
    log_level = "DEBUG" if verbose else "INFO"
    setup_logging(log_level)


# Register extracted command modules
register_all_commands(cli)


def main() -> None:
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()
