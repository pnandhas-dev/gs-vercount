"""
CLI Commands Package

This package splits the monolithic cli.py into logical command groups:
- connection_commands.py: Connection testing
- table_commands.py: Table operations (check, create, list, drop, etc.)
- journal_commands.py: Journal operations (enable, disable, entries, etc.)
- mockup_commands.py: Mock data generation
- mssql_commands.py: MSSQL operations
- schema_commands.py: Schema conversion and comparison
- utils.py: Shared helper functions
"""

# Only import modules that exist
from . import connection_commands
from . import mockup_commands
from . import mockup_light  # Lightweight agent-based mockup
from . import journal_commands
from . import table_commands
from . import library_commands
from . import sql_commands
from . import mssql_commands
from . import agent_commands
from . import utils

__all__ = [
    "connection_commands",
    "mockup_commands",
    "mockup_light",
    "journal_commands",
    "table_commands",
    "library_commands",
    "sql_commands",
    "mssql_commands",
    "agent_commands",
    "utils",
]


def register_all_commands(cli_group):
    """Register all command modules with the main CLI group."""
    connection_commands.register_connection_commands(cli_group)
    # Use lightweight mockup if agent is configured, otherwise use full version
    import os
    if os.getenv('QADMCLI_AGENT_URL'):
        mockup_light.register_mockup_commands(cli_group)
    else:
        mockup_commands.register_mockup_commands(cli_group)
    journal_commands.register_journal_commands(cli_group)
    table_commands.register_table_commands(cli_group)
    library_commands.register_library_commands(cli_group)
    sql_commands.register_sql_commands(cli_group)
    mssql_commands.register_mssql_commands(cli_group)
    agent_commands.register_agent_commands(cli_group)
