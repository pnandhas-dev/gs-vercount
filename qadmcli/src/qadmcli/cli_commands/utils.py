"""Shared CLI Utilities.

Common functions used across multiple CLI command modules.
"""

import getpass
from typing import Any, Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from ..models.connection import ConnectionConfig, AS400Connection, DefaultsConfig
from ..db.connection import AS400ConnectionManager

console = Console()


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
    title: str | Optional[str] = None,
    border_style: str = "blue"
) -> None:
    """Print content in a panel with border style from context.
    
    Uses unicode (Rich Panel) or ascii (print_ascii_panel) based on
    the --border-style CLI option.
    """
    border_style_opt = ctx.obj.get("border_style", "unicode")
    
    if border_style_opt == "ascii":
        # ASCII border style - use simple print
        if isinstance(content, Text):
            content = content.plain
        console.print(f"\n--- {title or ''} ---")
        console.print(content)
        console.print("-" * 60)
    else:
        # Unicode border style - use Rich Panel
        if isinstance(content, str):
            content = Text.from_markup(content)
        
        panel = Panel(content, title=title, border_style=border_style)
        console.print(panel)
