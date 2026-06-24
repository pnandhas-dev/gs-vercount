"""Lightweight mockup command - thin HTTP wrapper for agent."""

import click
import requests
import logging
from rich.console import Console
from rich.panel import Panel

logger = logging.getLogger(__name__)
console = Console()


@click.group()
def mockup():
    """Mockup data generation (via agent)."""
    pass


@mockup.command()
@click.option('-t', '--table', required=True, help='Table name')
@click.option('-l', '--library', default='*LIBL', help='Library name')
@click.option('-r', '--rows', type=int, default=1000, help='Total transactions')
@click.option('--batch-size', type=int, default=100, help='Batch size')
@click.option('--insert-ratio', type=int, default=60, help='Insert ratio (%)')
@click.option('--update-ratio', type=int, default=20, help='Update ratio (%)')
@click.option('--delete-ratio', type=int, default=20, help='Delete ratio (%)')
@click.option('--dry-run', is_flag=True, help='Simulate without executing')
@click.option('--random', is_flag=True, help='Fetch random PKs from database instead of reusing inserts')
@click.option('--agent-url', default=None, help='Agent URL (auto-detected from env)')
def generate(table, library, rows, batch_size, insert_ratio, update_ratio, 
             delete_ratio, dry_run, random, agent_url):
    """Generate mockup data via agent (FAST!)."""
    import os
    
    # Auto-detect agent URL
    agent_url = agent_url or os.getenv('QADMCLI_AGENT_URL')
    if not agent_url:
        console.print(Panel(
            "[red]❌ Agent URL not configured![/red]\n\n"
            "Set QADMCLI_AGENT_URL environment variable:\n"
            "  export QADMCLI_AGENT_URL=http://127.0.0.1:8765\n\n"
            "Or start agent container:\n"
            "  sudo podman run -d --name qadmcli-agent --network=host qadmcli agent start --foreground",
            title="Error"
        ))
        return
    
    # Check agent health
    try:
        health = requests.get(f"{agent_url}/health", timeout=2)
        if health.status_code != 200:
            console.print(f"[red]❌ Agent not healthy at {agent_url}[/red]")
            return
    except requests.exceptions.ConnectionError:
        console.print(f"[red]❌ Cannot connect to agent at {agent_url}[/red]")
        console.print("Start agent first:")
        console.print("  sudo podman start qadmcli-agent")
        return
    
    console.print(f"[green]🚀 Using agent:[/green] {agent_url}")
    console.print(f"[dim]Generating mock data for {library}.{table}...[/dim]")
    console.print(f"[dim]  Transactions: {rows} (Insert: {insert_ratio}%, Update: {update_ratio}%, Delete: {delete_ratio}%)[/dim]")
    console.print(f"[dim]  Batch size: {batch_size}[/dim]\n")
    
    # Send request to agent (all logic runs in agent!)
    try:
        response = requests.post(
            f"{agent_url}/mockup/generate",
            json={
                "table": table,
                "library": library,
                "total_transactions": rows,
                "batch_size": batch_size,
                "insert_ratio": insert_ratio,
                "update_ratio": update_ratio,
                "delete_ratio": delete_ratio,
                "dry_run": dry_run,
                "random_pks": random
            },
            timeout=600  # 10 minutes for large batches
        )
        
        if response.status_code == 200:
            result = response.json()
            
            console.print(Panel(
                f"[green]✅ Mock data generation complete![/green]\n\n"
                f"  [bold]Inserted:[/bold] {result['inserted']} rows\n"
                f"  [bold]Updated:[/bold]  {result['updated']} rows\n"
                f"  [bold]Deleted:[/bold]  {result['deleted']} rows\n\n"
                f"  [bold]Total time:[/bold] {result['execution_time_ms']/1000:.2f}s\n"
                f"  [bold]Throughput:[/bold] {result['total_transactions'] / (result['execution_time_ms']/1000):.0f} rows/sec",
                title=f"{library}.{table}"
            ))
        else:
            console.print(f"[red]❌ Agent error {response.status_code}:[/red] {response.text}")
            
    except requests.exceptions.Timeout:
        console.print("[red]❌ Request timed out (10 minutes)[/red]")
    except requests.exceptions.ConnectionError:
        console.print("[red]❌ Lost connection to agent[/red]")


@mockup.command()
@click.option('-t', '--table', required=True, help='Table name')
@click.option('-l', '--library', default='*LIBL', help='Library name')
@click.option('--agent-url', default=None, help='Agent URL')
def hint(table, library, agent_url):
    """Show schema hints for mockup generation."""
    import os
    
    agent_url = agent_url or os.getenv('QADMCLI_AGENT_URL')
    if not agent_url:
        console.print("[red]❌ Agent URL not configured[/red]")
        return
    
    try:
        response = requests.post(
            f"{agent_url}/schema/inspect",
            json={"table": table, "library": library},
            timeout=30
        )
        
        if response.status_code == 200:
            schema = response.json()
            console.print(Panel(
                f"[bold]Table:[/bold] {schema['table']}\n"
                f"[bold]Library:[/bold] {schema['library']}\n\n"
                f"[bold]Columns:[/bold]\n" +
                "\n".join([f"  - {col['name']}: {col['type']}" for col in schema['columns']]),
                title="Schema Hints"
            ))
        else:
            console.print(f"[red]❌ Error:[/red] {response.text}")
            
    except Exception as e:
        console.print(f"[red]❌ Failed to get schema:[/red] {e}")


def register_mockup_commands(cli_group):
    """Register lightweight mockup commands with main CLI."""
    cli_group.add_command(mockup)

