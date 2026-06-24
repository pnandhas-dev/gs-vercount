"""Output formatters."""

import json
from typing import Any

from rich.console import Console
from rich.table import Table as RichTable
from rich.json import JSON as RichJSON
from rich import box
from rich.text import Text


def format_table(
    headers: list[str],
    rows: list[list[Any]],
    title: str | None = None
) -> RichTable:
    """Format data as Rich table."""
    table = RichTable(
        title=title, 
        show_header=True, 
        header_style="bold magenta", 
        box=box.ASCII,
        show_edge=False  # Disable edge to prevent truncation issues
    )
    
    for header in headers:
        # Use overflow="fold" to wrap long text instead of truncating with ellipsis
        table.add_column(header, overflow="fold", no_wrap=False)
    
    for row in rows:
        table.add_row(*[str(cell) for cell in row])
    
    return table


def format_json(data: Any, indent: int = 2) -> str:
    """Format data as JSON string."""
    return json.dumps(data, indent=indent, default=str, ensure_ascii=False)


def print_table(
    console: Console,
    headers: list[str],
    rows: list[list[Any]],
    title: str | None = None
) -> None:
    """Print formatted table to console."""
    table = format_table(headers, rows, title)
    console.print(table)


def print_json(console: Console, data: Any, indent: int = 2) -> None:
    """Print formatted JSON to console.
    
    NOTE: This uses RichJSON which adds ANSI color codes for syntax highlighting.
    For script-friendly output (no ANSI codes), use print_json_clean() instead.
    """
    json_str = format_json(data, indent)
    console.print(RichJSON(json_str))


def print_json_clean(data: Any, indent: int = 2) -> None:
    """Print clean JSON to stdout (no Rich formatting, for scripts/piping)."""
    json_str = json.dumps(data, indent=indent, default=str, ensure_ascii=False)
    print(json_str)


def print_ascii_panel(
    console: Console,
    content: str | Text,
    title: str | None = None,
    border_style: str = "blue"
) -> None:
    """Print content in an ASCII box (Windows-compatible).
    
    Replaces Rich Panel which uses Unicode box-drawing characters
    that don't render correctly in Windows terminals.
    """
    lines = str(content).split('\n')
    max_width = max(len(line) for line in lines) if lines else 0
    
    # Build ASCII box
    top_border = f"+{'-' * (max_width + 2)}+"
    bottom_border = top_border
    
    if title:
        title_str = f" {title} "
        title_pos = (max_width + 2 - len(title_str)) // 2
        top_border = f"+{'-' * title_pos}{title_str}{'-' * (max_width + 2 - title_pos - len(title_str))}+"
    
    # Print box
    console.print(f"[{border_style}]{top_border}[/{border_style}]")
    for line in lines:
        padding = ' ' * (max_width - len(line))
        console.print(f"[{border_style}]|[/{border_style}] {line}{padding} [{border_style}]|[/{border_style}]")
    console.print(f"[{border_style}]{bottom_border}[/{border_style}]")
