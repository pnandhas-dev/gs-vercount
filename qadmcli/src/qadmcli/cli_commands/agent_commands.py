"""
Agent Commands - AS400 Agent Daemon management

Provides commands to start/stop/status the persistent AS400 agent.
"""

import click
import sys
import os
from pathlib import Path

# Add qadmcli_agent to path (works both inside and outside container)
agent_path = Path(__file__).parent.parent.parent.parent / "qadmcli_agent"
if str(agent_path) not in sys.path:
    sys.path.insert(0, str(agent_path.parent))


def register_agent_commands(cli_group):
    """Register agent commands with main CLI."""
    try:
        from qadmcli_agent.cli import agent as agent_group
        
        # Add agent command group to CLI
        cli_group.add_command(agent_group)
    except ImportError as e:
        # Agent module not available - skip registration (graceful degradation)
        # This is OK for Option 1 (pure container mode without agent)
        pass
