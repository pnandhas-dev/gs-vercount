"""Journal Commands Module.

This module contains all journal-related CLI commands:
- journal check: Check journal status for a table
- journal disable: Disable journaling on tables
- journal enable: Enable journaling on tables
- journal entries: View journal entries
- journal list: List journals in a library
- journal receivers: List journal receivers
- journal cleanup: Clean up old journal receivers
- journal monitor: Monitor journal health
- journal info: Get detailed journal information
- journal create-receiver: Create a new journal receiver
- journal rollover: Perform journal receiver rollover
- journal create: Create a new journal
- journal last-txn: Get last transaction sequence and timestamp for table(s)
"""

import sys
import os
import logging
from datetime import datetime
from typing import Optional

import click
from rich.console import Console
from rich.text import Text

from ..config import load_config
from ..db.connection import AS400ConnectionManager, ConnectionError
from ..db.journal import JournalManager
from ..utils.formatters import print_table, print_json_clean
from .utils import print_panel

EPOCH_START = datetime(1, 1, 1)


def _dt_to_dotnet_ticks(dt: datetime) -> int:
    """Convert Python datetime to .NET ticks (100-nanosecond intervals since 0001-01-01)."""
    return int((dt - EPOCH_START).total_seconds() * 10_000_000)


def _agent_get_journal_info(client, table_name, library, skip_entry_range=False):
    """Get journal info via agent queries. Returns JournalInfo instance."""
    from ..models.journal import JournalInfo

    table_name = table_name.upper()
    library = library.upper()

    # Resolve system name for JOURNALED_OBJECTS lookup
    system_name = table_name
    try:
        sys_result = client.query(
            "SELECT SYSTEM_TABLE_NAME FROM QSYS2.SYSTABLES "
            "WHERE TABLE_NAME = ? AND TABLE_SCHEMA = ?",
            params=[table_name, library]
        )
        if sys_result["row_count"] > 0 and sys_result["rows"][0][0]:
            system_name = str(sys_result["rows"][0][0]).strip()
    except Exception:
        pass

    # Query JOURNALED_OBJECTS
    jrn_result = client.query(
        "SELECT JOURNAL_LIBRARY, JOURNAL_NAME, JOURNAL_IMAGES "
        "FROM QSYS2.JOURNALED_OBJECTS "
        "WHERE (OBJECT_NAME = ? OR OBJECT_NAME = ?) "
        "AND OBJECT_LIBRARY = ? AND OBJECT_TYPE = '*FILE'",
        params=[table_name, system_name, library]
    )

    j_lib = j_name = j_images = None
    if jrn_result["row_count"] > 0:
        row = jrn_result["rows"][0]
        j_lib = str(row[0]).strip() if row[0] else None
        j_name = str(row[1]).strip() if row[1] else None
        j_images = str(row[2]).strip() if row[2] else None

    info = JournalInfo(
        table_name=table_name,
        table_library=library,
        is_journaled=j_lib is not None and j_name is not None,
        journal_library=j_lib,
        journal_name=j_name,
        journal_images=j_images,
    )

    if info.is_journaled and info.journal_library and info.journal_name:
        recv_result = client.query(
            "SELECT ATTACHED_JOURNAL_RECEIVER_LIBRARY, "
            "ATTACHED_JOURNAL_RECEIVER_NAME "
            "FROM QSYS2.JOURNAL_INFO "
            "WHERE JOURNAL_LIBRARY = ? AND JOURNAL_NAME = ?",
            params=[info.journal_library, info.journal_name]
        )
        if recv_result["row_count"] > 0:
            info.journal_receiver_library = (
                str(recv_result["rows"][0][0]) if recv_result["rows"][0][0] else None
            )
            info.journal_receiver_name = (
                str(recv_result["rows"][0][1]) if recv_result["rows"][0][1] else None
            )

        if not skip_entry_range:
            _agent_populate_entry_range(client, info)

    return info


def _agent_populate_entry_range(client, info):
    """Populate entry range via agent queries."""
    # Get receiver details (attach/detach timestamps, seq range)
    recv_result = client.query(
        "SELECT FIRST_SEQUENCE_NUMBER, LAST_SEQUENCE_NUMBER, "
        "NUMBER_OF_JOURNAL_ENTRIES, ATTACH_TIMESTAMP, DETACH_TIMESTAMP, "
        "JOURNAL_RECEIVER_NAME, JOURNAL_RECEIVER_LIBRARY, STATUS "
        "FROM QSYS2.JOURNAL_RECEIVER_INFO "
        "WHERE JOURNAL_LIBRARY = ? AND JOURNAL_NAME = ? "
        "AND STATUS = 'ATTACHED' FETCH FIRST 1 ROW ONLY",
        params=[info.journal_library, info.journal_name]
    )

    if recv_result["row_count"] > 0:
        row = recv_result["rows"][0]
        info.journal_receiver_name = str(row[5]) if row[5] else None
        info.journal_receiver_library = str(row[6]) if row[6] else None
        info.receiver_attach_timestamp = str(row[3]) if row[3] else None
        info.receiver_detach_timestamp = str(row[4]) if row[4] else None

    # Get table-specific entry range from DISPLAY_JOURNAL
    _agent_populate_table_entry_range(client, info)


def _agent_populate_table_entry_range(client, info):
    """Get entry range specific to the table via agent."""
    system_name = info.table_name
    try:
        sys_result = client.query(
            "SELECT SYSTEM_TABLE_NAME FROM QSYS2.SYSTABLES "
            "WHERE TABLE_NAME = ? AND TABLE_SCHEMA = ?",
            params=[info.table_name, info.table_library]
        )
        if sys_result["row_count"] > 0 and sys_result["rows"][0][0]:
            system_name = str(sys_result["rows"][0][0]).strip()
    except Exception:
        pass

    dj_sql = """
        SELECT MIN(SEQUENCE_NUMBER), MAX(SEQUENCE_NUMBER), COUNT(*),
               MIN(ENTRY_TIMESTAMP), MAX(ENTRY_TIMESTAMP)
        FROM TABLE (
            QSYS2.DISPLAY_JOURNAL(
                JOURNAL_LIBRARY => ?,
                JOURNAL_NAME => ?
            )
        )
        WHERE OBJECT LIKE ?
    """
    object_pattern = f"%{system_name}%"
    try:
        result = client.query(
            dj_sql,
            params=[info.journal_library, info.journal_name, object_pattern]
        )
        if result["row_count"] > 0 and result["rows"][0][0] is not None:
            row = result["rows"][0]
            info.oldest_entry_sequence = row[0]
            info.newest_entry_sequence = row[1]
            info.total_entries = row[2]
            info.oldest_entry_timestamp = str(row[3]) if row[3] else None
            info.newest_entry_timestamp = str(row[4]) if row[4] else None
            return
        # Retry with SQL name
        sql_object_pattern = f"%{info.table_name}%"
        result = client.query(
            dj_sql,
            params=[info.journal_library, info.journal_name, sql_object_pattern]
        )
        if result["row_count"] > 0 and result["rows"][0][0] is not None:
            row = result["rows"][0]
            info.oldest_entry_sequence = row[0]
            info.newest_entry_sequence = row[1]
            info.total_entries = row[2]
            info.oldest_entry_timestamp = str(row[3]) if row[3] else None
            info.newest_entry_timestamp = str(row[4]) if row[4] else None
    except Exception:
        pass


console = Console()


@click.group()
def journal():
    """Journal management commands."""
    pass


@journal.command("check")
@click.option("--table", "-t", required=True, help="Table name")
@click.option("--library", "-l", required=True, help="Library name")
@click.option("--format", "-f", "output_format", type=click.Choice(["table", "json"]), default="table", help="Output format (default: table)")
@click.pass_context
def journal_check(ctx: click.Context, table: str, library: str, output_format: str) -> None:
    """Check journal status for a table."""
    config_path = ctx.obj["config_path"]
    
    # Suppress logging for JSON output
    if output_format == "json":
        import logging
        logging.getLogger("qadmcli").setLevel(logging.WARNING)
    
    try:
        # Check if agent is available (no JVM needed in CLI)
        agent_url = os.environ.get("QADMCLI_AGENT_URL")
        if agent_url:
            from ..db.agent_client import AS400AgentClient
            client = AS400AgentClient(agent_url)
            if client.is_available():
                check_result = client.query(
                    "SELECT JOURNAL_LIBRARY, JOURNAL_NAME, JOURNAL_IMAGES "
                    "FROM QSYS2.JOURNALED_OBJECTS "
                    "WHERE (OBJECT_NAME = ? OR OBJECT_NAME = ?) "
                    "AND OBJECT_LIBRARY = ? AND OBJECT_TYPE = '*FILE'",
                    params=[table.upper(), table.upper(), library.upper()]
                )
                is_journaled = check_result["row_count"] > 0
                j_lib = j_name = j_images = r_lib = r_name = None
                if is_journaled:
                    row = check_result["rows"][0]
                    j_lib = row[0] or None
                    j_name = row[1] or None
                    j_images = row[2] or None
                    if j_lib and j_name:
                        recv_result = client.query(
                            "SELECT ATTACHED_JOURNAL_RECEIVER_LIBRARY, "
                            "ATTACHED_JOURNAL_RECEIVER_NAME "
                            "FROM QSYS2.JOURNAL_INFO "
                            "WHERE JOURNAL_LIBRARY = ? AND JOURNAL_NAME = ?",
                            params=[j_lib, j_name]
                        )
                        if recv_result["row_count"] > 0:
                            r_lib = recv_result["rows"][0][0] or None
                            r_name = recv_result["rows"][0][1] or None
                
                if output_format == "json":
                    from ..utils.formatters import print_json_clean
                    print_json_clean({
                        "table": f"{library}.{table}",
                        "is_journaled": is_journaled,
                        "journal_library": j_lib,
                        "journal_name": j_name,
                        "journal_images": j_images,
                        "journal_receiver_library": r_lib,
                        "journal_receiver_name": r_name,
                    })
                else:
                    status_color = "green" if is_journaled else "yellow"
                    journal_str = f"{j_lib}.{j_name}" if j_lib and j_name else "N/A"
                    receiver_str = f"{r_lib}.{r_name}" if r_lib and r_name else "N/A"
                    print_panel(
                        ctx,
                        Text.assemble(
                            ("Table: ", "bold"), f"{library}.{table}", "\n",
                            ("Journaled: ", "bold"), ("Yes" if is_journaled else "No", status_color), "\n",
                            ("Journal: ", "bold"), (journal_str, status_color), "\n",
                            ("Receiver: ", "bold"), (receiver_str, status_color), "\n",
                        ),
                        title="Journal Information",
                        border_style=status_color
                    )
                return
        
        config = load_config(config_path)
        
        with AS400ConnectionManager(config) as conn:
            jrn = JournalManager(conn)
            info = jrn.get_journal_info(table, library)
            
            if output_format == "json":
                print_json_clean(info.get_summary())
            else:
                status_color = "green" if info.is_journaled else "yellow"
                print_panel(
                    ctx,
                    Text.assemble(
                        ("Table: ", "bold"), f"{library}.{table}", "\n",
                        ("Journaled: ", "bold"), ("Yes" if info.is_journaled else "No", status_color), "\n",
                        ("Journal: ", "bold"), (f"{info.journal_library}.{info.journal_name}" if info.journal_library and info.journal_name else "N/A"), "\n",
                        ("Receiver: ", "bold"), (f"{info.journal_receiver_library}.{info.journal_receiver_name}" if info.journal_receiver_library and info.journal_receiver_name else "N/A"), "\n",
                        ("Entry Range: ", "bold"), 
                        (f"{info.oldest_entry_sequence} - {info.newest_entry_sequence}" if info.oldest_entry_sequence and info.newest_entry_sequence else "N/A"),
                    ),
                    title="Journal Information",
                    border_style=status_color
                )
        
    except ConnectionError as e:
        console.print(f"[red]Connection error: {e.message}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@journal.command("disable")
@click.option("--table", "-t", required=True, help="Table name (supports wildcards: * or %)")
@click.option("--library", "-l", required=True, help="Library name")
@click.option("--dry-run", is_flag=True, help="Show which tables would be affected without making changes")
@click.option("--format", "-f", "output_format", type=click.Choice(["table", "json"]), default="table", help="Output format (default: table)")
@click.pass_context
def journal_disable(
    ctx: click.Context,
    table: str,
    library: str,
    dry_run: bool,
    output_format: str
) -> None:
    """Disable journaling for one or more tables.
    
    Supports wildcards:
      - * or % for multiple characters
      - ? or _ for single character
    
    Examples:
      qadmcli journal disable -t TB_01 -l EZPIPE
      qadmcli journal disable -t "TB_*" -l EZPIPE
      qadmcli journal disable -t "%TEST%" -l MYLIB --dry-run
    """
    config_path = ctx.obj["config_path"]
    
    try:
        # Check if agent is available (no JVM needed in CLI)
        agent_url = os.environ.get("QADMCLI_AGENT_URL")
        if agent_url:
            from ..db.agent_client import AS400AgentClient
            client = AS400AgentClient(agent_url)
            if client.is_available():
                if '*' in table or '%' in table or '?' in table:
                    import fnmatch
                    tables_result = client.query(
                        "SELECT TABLE_NAME FROM QSYS2.SYSTABLES WHERE TABLE_SCHEMA = ?",
                        params=[library.upper()]
                    )
                    pattern = table.replace('%', '*')
                    matched_tables = [
                        r[0] for r in tables_result.get("rows", [])
                        if r[0] and fnmatch.fnmatch(r[0], pattern)
                    ]
                    if not matched_tables:
                        console.print(f"[yellow]No tables matching pattern '{table}' in {library}[/yellow]")
                        return

                    if dry_run:
                        console.print(f"[blue]Dry run - would disable journaling for {len(matched_tables)} table(s):[/blue]")
                        for t in matched_tables:
                            console.print(f"  - {t}")
                        return

                    results = []
                    success_count = 0
                    error_count = 0
                    console.print(f"[blue]Disabling journaling for {len(matched_tables)} table(s)...[/blue]")
                    for tbl in matched_tables:
                        try:
                            cmd = f"ENDJRNPF FILE({library.upper()}/{tbl}) JRN(*FILE)"
                            client.execute("CALL QSYS2.QCMDEXC(?, ?)", params=[cmd, len(cmd.encode('utf-8'))])
                            results.append({"table": f"{library}.{tbl}", "success": True})
                            success_count += 1
                            console.print(f"  [green]OK[/green] {library}.{tbl}")
                        except Exception as e:
                            results.append({"table": f"{library}.{tbl}", "success": False, "error": str(e)})
                            error_count += 1
                            console.print(f"  [red]ERR[/red] {library}.{tbl}: {e}")

                    if output_format == "json":
                        from ..utils.formatters import print_json_clean
                        print_json_clean({
                            "operation": "disable", "pattern": table, "library": library,
                            "total": len(matched_tables), "success": success_count,
                            "errors": error_count, "results": results
                        })
                    else:
                        console.print(f"\n[green]Completed: {success_count} succeeded, {error_count} failed[/green]")
                else:
                    if dry_run:
                        console.print(f"[blue]Dry run - would disable journaling for {library}.{table}[/blue]")
                        return
                    cmd = f"ENDJRNPF FILE({library.upper()}/{table.upper()}) JRN(*FILE)"
                    client.execute("CALL QSYS2.QCMDEXC(?, ?)", params=[cmd, len(cmd.encode('utf-8'))])
                    if output_format == "json":
                        from ..utils.formatters import print_json_clean
                        print_json_clean({"success": True, "table": f"{library}.{table}"})
                    else:
                        console.print(f"[green]Disabled journaling for {library}.{table}[/green]")
                return

        config = load_config(config_path)
        
        with AS400ConnectionManager(config) as conn:
            jrn = JournalManager(conn)
            
            # Check if wildcard pattern (* and ? are shell-style, % is SQL-style)
            # Note: _ is a valid character in IBM i table names, not a wildcard
            if '*' in table or '%' in table or '?' in table:
                # Find matching tables
                from ..db.schema import SchemaManager
                import fnmatch
                schema_mgr = SchemaManager(conn)
                all_tables = schema_mgr.list_tables(library)
                
                # Filter tables by pattern (convert SQL wildcards to fnmatch pattern)
                pattern = name.replace('%', '*').replace('_', '?')
                tables = [t for t in all_tables if fnmatch.fnmatch(t.name, pattern)]
                
                if not tables:
                    console.print(f"[yellow]No tables matching pattern '{table}' in {library}[/yellow]")
                    return
                
                if dry_run:
                    console.print(f"[blue]Dry run - would disable journaling for {len(tables)} table(s):[/blue]")
                    for table in tables:
                        console.print(f"  - {table.name}")
                    return
                
                # Process each table
                results = []
                success_count = 0
                error_count = 0
                
                console.print(f"[blue]Disabling journaling for {len(tables)} table(s)...[/blue]")
                for table in tables:
                    try:
                        result = jrn.disable_journaling(table.name, library)
                        results.append({
                            "table": f"{library}.{table.name}",
                            "success": True
                        })
                        success_count += 1
                        console.print(f"  [green]OK[/green] {library}.{table.name}")
                    except Exception as e:
                        results.append({
                            "table": f"{library}.{table.name}",
                            "success": False,
                            "error": str(e)
                        })
                        error_count += 1
                        console.print(f"  [red]ERR[/red] {library}.{table.name}: {e}")
                
                if output_format == "json":
                    print_json_clean({
                        "operation": "disable",
                        "pattern": name,
                        "library": library,
                        "total": len(tables),
                        "success": success_count,
                        "errors": error_count,
                        "results": results
                    })
                else:
                    console.print(f"\n[green]Completed: {success_count} succeeded, {error_count} failed[/green]")
            else:
                # Single table
                if dry_run:
                    console.print(f"[blue]Dry run - would disable journaling for {library}.{table}[/blue]")
                    return
                
                result = jrn.disable_journaling(table, library)
                
                if output_format == "json":
                    print_json_clean(result)
                else:
                    console.print(f"[green]Disabled journaling for {library}.{table}[/green]")
        
    except ConnectionError as e:
        console.print(f"[red]Connection error: {e.message}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@journal.command("enable")
@click.option("--table", "-t", required=True, help="Table name (supports wildcards: * or %)")
@click.option("--library", "-l", required=True, help="Library name")
@click.option("--journal-library", "-j", help="Journal library (default from config)")
@click.option("--journal-name", help="Journal name (default from config)")
@click.option("--images", "-i", type=click.Choice(["*BOTH", "*AFTER", "*BEFORE"]), 
              default="*AFTER", help="Journal images to capture (default: *AFTER)")
@click.option("--dry-run", is_flag=True, help="Show which tables would be affected without making changes")
@click.option("--format", "-f", "output_format", type=click.Choice(["table", "json"]), default="table", help="Output format (default: table)")
@click.pass_context
def journal_enable(
    ctx: click.Context,
    table: str,
    library: str,
    journal_library: str | None,
    journal_name: str | None,
    images: str,
    dry_run: bool,
    output_format: str
) -> None:
    """Enable journaling for one or more tables.
    
    Supports wildcards:
      - * or % for multiple characters
      - ? or _ for single character
    
    Examples:
      qadmcli journal enable -t TB_01 -l EZPIPE
      qadmcli journal enable -t "TB_*" -l EZPIPE --images *BOTH
      qadmcli journal enable -t "%TEST%" -l MYLIB -j MYLIB --dry-run
    """
    config_path = ctx.obj["config_path"]
    
    try:
        # Check if agent is available (no JVM needed in CLI)
        agent_url = os.environ.get("QADMCLI_AGENT_URL")
        if agent_url:
            from ..db.agent_client import AS400AgentClient
            client = AS400AgentClient(agent_url)
            if client.is_available():
                j_lib = journal_library
                j_name = journal_name
                if not j_lib or not j_name:
                    cfg = load_config(config_path)
                    if not j_lib:
                        j_lib = cfg.defaults.journal_library
                    if not j_name:
                        j_name = cfg.defaults.journal_name

                if '*' in table or '%' in table or '?' in table:
                    import fnmatch
                    tables_result = client.query(
                        "SELECT TABLE_NAME FROM QSYS2.SYSTABLES WHERE TABLE_SCHEMA = ?",
                        params=[library.upper()]
                    )
                    pattern = table.replace('%', '*')
                    matched_tables = [
                        r[0] for r in tables_result.get("rows", [])
                        if r[0] and fnmatch.fnmatch(r[0], pattern)
                    ]
                    if not matched_tables:
                        console.print(f"[yellow]No tables matching pattern '{table}' in {library}[/yellow]")
                        return

                    if dry_run:
                        console.print(f"[blue]Dry run - would enable journaling for {len(matched_tables)} table(s):[/blue]")
                        for t in matched_tables:
                            console.print(f"  - {t} (images: {images})")
                        return

                    results = []
                    success_count = 0
                    error_count = 0
                    console.print(f"[blue]Enabling journaling for {len(matched_tables)} table(s) with {images}...[/blue]")
                    for tbl in matched_tables:
                        try:
                            cmd = f"STRJRNPF FILE({library.upper()}/{tbl}) JRN({j_lib.upper()}/{j_name.upper()}) IMAGES({images}) OMTJRNE(*OPNCLO)"
                            client.execute("CALL QSYS2.QCMDEXC(?, ?)", params=[cmd, len(cmd.encode('utf-8'))])
                            results.append({"table": f"{library}.{tbl}", "success": True, "journal": f"{j_lib}.{j_name}"})
                            success_count += 1
                            console.print(f"  [green]OK[/green] {library}.{tbl} -> {j_lib}.{j_name}")
                        except Exception as e:
                            results.append({"table": f"{library}.{tbl}", "success": False, "error": str(e)})
                            error_count += 1
                            console.print(f"  [red]ERR[/red] {library}.{tbl}: {e}")

                    if output_format == "json":
                        from ..utils.formatters import print_json_clean
                        print_json_clean({
                            "operation": "enable", "pattern": table, "library": library,
                            "images": images, "total": len(matched_tables),
                            "success": success_count, "errors": error_count, "results": results
                        })
                    else:
                        console.print(f"\n[green]Completed: {success_count} succeeded, {error_count} failed[/green]")
                        console.print(f"Images mode: {images}")
                else:
                    if dry_run:
                        console.print(f"[blue]Dry run - would enable journaling for {library}.{table} with {images}[/blue]")
                        return
                    cmd = f"STRJRNPF FILE({library.upper()}/{table.upper()}) JRN({j_lib.upper()}/{j_name.upper()}) IMAGES({images}) OMTJRNE(*OPNCLO)"
                    client.execute("CALL QSYS2.QCMDEXC(?, ?)", params=[cmd, len(cmd.encode('utf-8'))])
                    if output_format == "json":
                        from ..utils.formatters import print_json_clean
                        print_json_clean({"success": True, "table": f"{library}.{table}", "journal": f"{j_lib}.{j_name}"})
                    else:
                        console.print(f"[green]Enabled journaling for {library}.{table}[/green]")
                        console.print(f"Journal: {j_lib}.{j_name}")
                        console.print(f"Images: {images}")
                return

        config = load_config(config_path)
        
        with AS400ConnectionManager(config) as conn:
            jrn = JournalManager(conn)
            
            # Check if wildcard pattern (* and ? are shell-style, % is SQL-style)
            # Note: _ is a valid character in IBM i table names, not a wildcard
            if '*' in table or '%' in table or '?' in table:
                # Find matching tables
                from ..db.schema import SchemaManager
                import fnmatch
                schema_mgr = SchemaManager(conn)
                all_tables = schema_mgr.list_tables(library)
                
                # Filter tables by pattern (convert SQL wildcards to fnmatch pattern)
                pattern = name.replace('%', '*').replace('_', '?')
                tables = [t for t in all_tables if fnmatch.fnmatch(t.name, pattern)]
                
                if not tables:
                    console.print(f"[yellow]No tables matching pattern '{table}' in {library}[/yellow]")
                    return
                
                if dry_run:
                    console.print(f"[blue]Dry run - would enable journaling for {len(tables)} table(s):[/blue]")
                    for table in tables:
                        console.print(f"  - {table.name} (images: {images})")
                    return
                
                # Process each table
                results = []
                success_count = 0
                error_count = 0
                
                console.print(f"[blue]Enabling journaling for {len(tables)} table(s) with {images}...[/blue]")
                for table in tables:
                    try:
                        result = jrn.enable_journaling(table.name, library, journal_library, journal_name, images)
                        results.append({
                            "table": f"{library}.{table.name}",
                            "success": True,
                            "journal": result['journal']
                        })
                        success_count += 1
                        console.print(f"  [green]OK[/green] {library}.{table.name} -> {result['journal']}")
                    except Exception as e:
                        results.append({
                            "table": f"{library}.{table.name}",
                            "success": False,
                            "error": str(e)
                        })
                        error_count += 1
                        console.print(f"  [red]ERR[/red] {library}.{table.name}: {e}")
                
                if output_format == "json":
                    print_json_clean({
                        "operation": "enable",
                        "pattern": name,
                        "library": library,
                        "images": images,
                        "total": len(tables),
                        "success": success_count,
                        "errors": error_count,
                        "results": results
                    })
                else:
                    console.print(f"\n[green]Completed: {success_count} succeeded, {error_count} failed[/green]")
                    console.print(f"Images mode: {images}")
            else:
                # Single table
                if dry_run:
                    console.print(f"[blue]Dry run - would enable journaling for {library}.{table} with {images}[/blue]")
                    return
                
                result = jrn.enable_journaling(table, library, journal_library, journal_name, images)
                
                if output_format == "json":
                    print_json_clean(result)
                else:
                    console.print(f"[green]Enabled journaling for {library}.{table}[/green]")
                    console.print(f"Journal: {result['journal']}")
                    console.print(f"Images: {images}")
        
    except ConnectionError as e:
        console.print(f"[red]Connection error: {e.message}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@journal.command("entries")
@click.option("--table", "-t", required=True, help="Table name")
@click.option("--library", "-l", required=True, help="Library name")
@click.option("--limit", default=100, help="Number of entries to retrieve (default: 100)")
@click.option("--from-time", help="Filter entries from timestamp (ISO 8601: YYYY-MM-DD or YYYY-MM-DD HH:MM:SS)")
@click.option("--to-time", help="Filter entries to timestamp (ISO 8601: YYYY-MM-DD or YYYY-MM-DD HH:MM:SS)")
@click.option("--format", "output_format", type=click.Choice(["sql", "json", "summary"]), default="sql", help="Output format")
@click.pass_context
def journal_entries(
    ctx: click.Context,
    table: str,
    library: str,
    limit: int,
    from_time: str | None,
    to_time: str | None,
    output_format: str
) -> None:
    """Get journal entries for a table.
    
    Use --format summary to get operation counts (useful for comparison with MSSQL CT).
    """
    config_path = ctx.obj["config_path"]
    
    # Suppress logging for JSON output to keep it clean
    if output_format in ("json", "summary"):
        import logging
        logging.getLogger("qadmcli").setLevel(logging.WARNING)
    
    try:
        # Check if agent is available (no JVM needed in CLI)
        agent_url = os.environ.get("QADMCLI_AGENT_URL")
        if agent_url:
            from ..db.agent_client import AS400AgentClient
            from ..models.journal import JournalEntry
            client = AS400AgentClient(agent_url)
            if client.is_available():
                info = _agent_get_journal_info(client, table, library, skip_entry_range=True)

                if not info.is_journaled:
                    console.print(f"[yellow]Table {library}.{table} is not journaled[/yellow]")
                    return

                system_name = table.upper()
                sys_result = client.query(
                    "SELECT SYSTEM_TABLE_NAME FROM QSYS2.SYSTABLES "
                    "WHERE TABLE_NAME = ? AND TABLE_SCHEMA = ?",
                    params=[table.upper(), library.upper()]
                )
                if sys_result["row_count"] > 0 and sys_result["rows"][0][0]:
                    system_name = str(sys_result["rows"][0][0]).strip().upper()

                object_prefix = f"{system_name} {library.upper()}"

                if output_format == "summary":
                    summary_sql = """
                        SELECT JOURNAL_CODE, JOURNAL_ENTRY_TYPE, COUNT(*) as count
                        FROM TABLE (
                            QSYS2.DISPLAY_JOURNAL(
                                JOURNAL_LIBRARY => ?,
                                JOURNAL_NAME => ?,
                                JOURNAL_ENTRY_TYPES => '*ALL'
                            )
                        )
                        WHERE OBJECT LIKE ?
                    """
                    summary_params = [info.journal_library, info.journal_name, f"{object_prefix}%"]
                    if from_time:
                        summary_sql += " AND ENTRY_TIMESTAMP >= ?"
                        summary_params.append(from_time)
                    if to_time:
                        summary_sql += " AND ENTRY_TIMESTAMP <= ?"
                        summary_params.append(to_time)
                    summary_sql += " GROUP BY JOURNAL_CODE, JOURNAL_ENTRY_TYPE ORDER BY JOURNAL_CODE, JOURNAL_ENTRY_TYPE"

                    result = client.query(summary_sql, params=summary_params)

                    summary = {
                        'table': f"{library.upper()}.{table.upper()}",
                        'from_time': from_time,
                        'to_time': to_time,
                        'total': 0,
                        'inserts': 0,
                        'updates': 0,
                        'deletes': 0,
                        'commits': 0,
                        'other': 0,
                        'entries': []
                    }

                    for row in result.get("rows", []):
                        journal_code = str(row[0]).strip() if row[0] else '?'
                        entry_type = str(row[1]).strip() if row[1] else '?'
                        count = int(row[2]) if row[2] else 0
                        entry_info = {'code': journal_code, 'type': entry_type, 'count': count}

                        if entry_type == 'PT':
                            summary['inserts'] += count
                            entry_info['operation'] = 'INSERT'
                        elif entry_type in ('UP', 'UB'):
                            summary['updates'] += count
                            entry_info['operation'] = 'UPDATE'
                        elif entry_type == 'DL':
                            summary['deletes'] += count
                            entry_info['operation'] = 'DELETE'
                        elif entry_type in ('CG',):
                            summary['commits'] += count
                            entry_info['operation'] = 'COMMIT'
                        else:
                            summary['other'] += count
                            entry_info['operation'] = 'OTHER'

                        summary['entries'].append(entry_info)
                        summary['total'] += count

                    from ..utils.formatters import print_json_clean
                    print_json_clean(summary)
                else:
                    entries_sql = """
                        SELECT SEQUENCE_NUMBER, ENTRY_TIMESTAMP, JOB_NAME, JOB_USER,
                               JOB_NUMBER, PROGRAM_NAME, JOURNAL_CODE, JOURNAL_ENTRY_TYPE,
                               OBJECT, OBJECT_TYPE, ENTRY_DATA
                        FROM TABLE (
                            QSYS2.DISPLAY_JOURNAL(
                                JOURNAL_LIBRARY => ?,
                                JOURNAL_NAME => ?,
                                JOURNAL_ENTRY_TYPES => '*ALL'
                            )
                        )
                        WHERE OBJECT LIKE ?
                    """
                    entries_params = [info.journal_library, info.journal_name, f"{object_prefix}%"]

                    if from_time:
                        entries_sql += " AND ENTRY_TIMESTAMP >= ?"
                        entries_params.append(from_time)
                    if to_time:
                        entries_sql += " AND ENTRY_TIMESTAMP <= ?"
                        entries_params.append(to_time)

                    entries_sql += " ORDER BY SEQUENCE_NUMBER DESC FETCH FIRST ? ROWS ONLY"
                    entries_params.append(limit)

                    result = client.query(entries_sql, params=entries_params)
                    rows_data = result.get("rows", [])

                    entries = []
                    for row in rows_data:
                        raw_data = None
                        if len(row) > 10 and row[10]:
                            hex_str = str(row[10])
                            try:
                                raw_data = bytes.fromhex(hex_str).decode('utf-8', errors='ignore')
                            except Exception:
                                raw_data = hex_str

                        object_raw = str(row[8]).strip() if row[8] else None
                        actual_table_name = None
                        if object_raw:
                            parts = object_raw.split()
                            actual_table_name = parts[0] if len(parts) >= 1 else object_raw

                        entry = JournalEntry(
                            entry_number=row[0],
                            entry_timestamp=str(row[1]) if row[1] else None,
                            job_name=str(row[2]) if row[2] else None,
                            job_user=str(row[3]) if row[3] else None,
                            job_number=str(row[4]) if row[4] else None,
                            program_name=str(row[5]) if row[5] else None,
                            code=str(row[6]) if row[6] else None,
                            entry_type=str(row[7]) if row[7] else None,
                            object_name=actual_table_name,
                            object_library=library.upper(),
                            object_type=str(row[9]) if row[9] else None,
                            raw_entry_data=raw_data,
                        )
                        entries.append(entry)

                    if output_format == "json":
                        from ..utils.formatters import print_json_clean
                        data = [e.model_dump() for e in entries]
                        print_json_clean(data)
                    else:
                        if not entries:
                            console.print("[yellow]No journal entries found for this table.[/yellow]")
                        else:
                            for entry in entries:
                                sql_text = entry.to_sql()
                                if sql_text:
                                    console.print(f"-- Entry {entry.entry_number} ({entry.operation}) at {entry.entry_timestamp}")
                                    console.print(f"{sql_text}\n")
                                else:
                                    console.print(f"-- Entry {entry.entry_number} ({entry.entry_type or 'Unknown'}) at {entry.entry_timestamp}")
                                    console.print(f"-- Job: {entry.job_name}, User: {entry.job_user}, Program: {entry.program_name}")
                                    if entry.raw_entry_data:
                                        console.print(f"-- Raw data: {entry.raw_entry_data[:100]}...\n")
                                    else:
                                        console.print("-- No data available\n")
                return

        config = load_config(config_path)
        
        with AS400ConnectionManager(config) as conn:
            jrn = JournalManager(conn)
            
            if output_format == "summary":
                # Get summary only
                summary = jrn.get_journal_summary(table, library, from_time, to_time)
                print_json_clean(summary)
            else:
                # Get full entries
                entries = jrn.get_journal_entries(
                    table, library, 
                    limit=limit,
                    from_time=from_time,
                    to_time=to_time
                )
                
                if output_format == "json":
                    data = [e.model_dump() for e in entries]
                    print_json_clean(data)
                else:
                    # SQL format
                    if not entries:
                        console.print("[yellow]No journal entries found for this table.[/yellow]")
                    else:
                        for entry in entries:
                            sql = entry.to_sql()
                            if sql:
                                console.print(f"-- Entry {entry.entry_number} ({entry.operation}) at {entry.entry_timestamp}")
                                console.print(f"{sql}\n")
                            else:
                                # Show entry info even if SQL can't be generated
                                console.print(f"-- Entry {entry.entry_number} ({entry.entry_type or 'Unknown'}) at {entry.entry_timestamp}")
                                console.print(f"-- Job: {entry.job_name}, User: {entry.job_user}, Program: {entry.program_name}")
                                if entry.raw_entry_data:
                                    console.print(f"-- Raw data: {entry.raw_entry_data[:100]}...\n")
                                else:
                                    console.print("-- No data available\n")
        
    except ConnectionError as e:
        console.print(f"[red]Connection error: {e.message}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@journal.command("list")
@click.option("--library", "-l", help="Filter by library name")
@click.option("--format", "-f", "output_format", type=click.Choice(["table", "json"]), default="table", help="Output format (default: table)")
@click.pass_context
def journal_list(ctx: click.Context, library: str | None, output_format: str) -> None:
    """List all journals with their sizes and status."""
    config_path = ctx.obj["config_path"]
    
    try:
        # Check if agent is available (no JVM needed in CLI)
        agent_url = os.environ.get("QADMCLI_AGENT_URL")
        if agent_url:
            from ..db.agent_client import AS400AgentClient
            client = AS400AgentClient(agent_url)
            if client.is_available():
                sql = (
                    "SELECT JOURNAL_LIBRARY, JOURNAL_NAME, "
                    "COUNT(*) as RECEIVER_COUNT, "
                    "SUM(NUMBER_OF_JOURNAL_ENTRIES) as TOTAL_ENTRIES, "
                    "MAX(CASE WHEN STATUS = 'ATTACHED' THEN JOURNAL_RECEIVER_NAME END) as ATTACHED_RECEIVER "
                    "FROM QSYS2.JOURNAL_RECEIVER_INFO "
                    "WHERE 1=1"
                )
                params = []
                if library:
                    sql += " AND JOURNAL_LIBRARY = ?"
                    params.append(library.upper())
                sql += " GROUP BY JOURNAL_LIBRARY, JOURNAL_NAME ORDER BY TOTAL_ENTRIES DESC"
                
                result = client.query(sql, params=params if params else None)
                rows_data = result.get("rows", [])
                
                if output_format == "json":
                    journals = []
                    for row in rows_data:
                        journals.append({
                            "journal_library": row[0] or "",
                            "journal_name": row[1] or "",
                            "receiver_count": row[2] or 0,
                            "total_entries": row[3] or 0,
                            "attached_receiver": row[4] or None
                        })
                    from ..utils.formatters import print_json_clean
                    print_json_clean(journals)
                else:
                    if rows_data:
                        table_rows = []
                        for row in rows_data:
                            j_lib = row[0] or ""
                            j_name = row[1] or ""
                            recv_count = row[2] or 0
                            total_entries = row[3] or 0
                            attached_recv = row[4] or "N/A"
                            
                            if total_entries < 10000:
                                size_cat = "[green]Small[/green]"
                            elif total_entries < 1000000:
                                size_cat = "[yellow]Medium[/yellow]"
                            else:
                                size_cat = "[red]Large[/red]"
                            
                            table_rows.append([
                                f"{j_lib}.{j_name}",
                                str(recv_count),
                                f"{total_entries:,}" if total_entries else "N/A",
                                size_cat,
                                attached_recv
                            ])
                        
                        from ..utils.formatters import print_table
                        console.print(print_table(
                            console,
                            ["Journal", "Receivers", "Total Entries", "Size", "Current Receiver"],
                            table_rows,
                            title="Journal List"
                        ))
                    else:
                        console.print("[yellow]No journals found[/yellow]")
                return
        
        config = load_config(config_path)
        
        with AS400ConnectionManager(config) as conn:
            from ..db.journal import JournalManager
            jrn = JournalManager(conn)
            journals = jrn.list_journals(library)
            
            if output_format == "json":
                print_json_clean(journals)
            else:
                if journals:
                    rows = []
                    for j in journals:
                        total_entries = j.get('total_entries', 0) or 0
                        if total_entries < 10000:
                            size_cat = "[green]Small[/green]"
                        elif total_entries < 1000000:
                            size_cat = "[yellow]Medium[/yellow]"
                        else:
                            size_cat = "[red]Large[/red]"
                        
                        rows.append([
                            f"{j['journal_library']}.{j['journal_name']}",
                            str(j.get('receiver_count', 0)),
                            f"{total_entries:,}" if total_entries else "N/A",
                            size_cat,
                            j.get('attached_receiver', 'N/A') or 'N/A'
                        ])
                    
                    console.print(print_table(
                        console,
                        ["Journal", "Receivers", "Total Entries", "Size", "Current Receiver"],
                        rows,
                        title="Journal List"
                    ))
                else:
                    console.print("[yellow]No journals found[/yellow]")
    
    except ConnectionError as e:
        console.print(f"[red]Connection error: {e.message}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@journal.command("receivers")
@click.option("--journal", "-j", required=True, help="Journal name")
@click.option("--library", "-l", required=True, help="Library name")
@click.option("--format", "-f", "output_format", type=click.Choice(["table", "json"]), default="table", help="Output format (default: table)")
@click.pass_context
def journal_receivers(ctx: click.Context, journal: str, library: str, output_format: str) -> None:
    """Show journal receiver chain with cleanup recommendations."""
    config_path = ctx.obj["config_path"]
    
    try:
        # Check if agent is available (no JVM needed in CLI)
        agent_url = os.environ.get("QADMCLI_AGENT_URL")
        if agent_url:
            from ..db.agent_client import AS400AgentClient
            client = AS400AgentClient(agent_url)
            if client.is_available():
                result = client.query(
                    "SELECT JOURNAL_RECEIVER_LIBRARY, JOURNAL_RECEIVER_NAME, "
                    "NUMBER_OF_JOURNAL_ENTRIES, STATUS, SIZE "
                    "FROM QSYS2.JOURNAL_RECEIVER_INFO "
                    "WHERE JOURNAL_LIBRARY = ? AND JOURNAL_NAME = ? "
                    "ORDER BY CASE STATUS "
                    "WHEN 'ATTACHED' THEN 1 WHEN 'ONLINE' THEN 2 ELSE 3 END, "
                    "JOURNAL_RECEIVER_NAME",
                    params=[library.upper(), journal.upper()]
                )
                rows_data = result.get("rows", [])
                
                if output_format == "json":
                    receivers = []
                    for row in rows_data:
                        size_bytes = row[4] or 0
                        size_mb = size_bytes / (1024 * 1024) if size_bytes else 0
                        receivers.append({
                            "receiver_library": row[0] or "",
                            "receiver_name": row[1] or "",
                            "entries": row[2] or 0,
                            "status": row[3] or "UNKNOWN",
                            "size_mb": round(size_mb, 2)
                        })
                    from ..utils.formatters import print_json_clean
                    print_json_clean(receivers)
                else:
                    if rows_data:
                        receiver_list = []
                        for row in rows_data:
                            r_name = row[1] or ""
                            r_status = row[3] or "UNKNOWN"
                            r_entries = row[2] or 0
                            size_bytes = row[4] or 0
                            size_mb = size_bytes / (1024 * 1024) if size_bytes else 0
                            cleanup = "[red]KEEP (Attached)[/red]" if r_status == 'ATTACHED' else "[green]Safe to cleanup[/green]"
                            receiver_list.append({
                                "name": r_name,
                                "status": r_status,
                                "entries": r_entries,
                                "size_mb": size_mb,
                                "cleanup_label": cleanup
                            })
                        
                        table_rows = []
                        for r in receiver_list:
                            table_rows.append([
                                r["name"],
                                r["status"],
                                f"{r['entries']:,}" if r["entries"] else "N/A",
                                f"{r['size_mb']:.2f} MB" if r["size_mb"] else "N/A",
                                r["cleanup_label"]
                            ])
                        
                        from ..utils.formatters import print_table
                        console.print(print_table(
                            console,
                            ["Receiver", "Status", "Entries", "Size", "Cleanup Status"],
                            table_rows,
                            title=f"Journal Receivers: {library}.{journal}"
                        ))
                        
                        total_receivers = len(receiver_list)
                        attached = sum(1 for r in receiver_list if r["status"] == 'ATTACHED')
                        online = sum(1 for r in receiver_list if r["status"] == 'ONLINE')
                        console.print(f"\n[blue]Summary:[/blue] {total_receivers} receivers total ({attached} attached, {online} online, {total_receivers - attached - online} other)")
                        if online > 0:
                            console.print(f"[yellow]Tip:[/yellow] {online} receiver(s) can be saved and deleted to free space")
                    else:
                        console.print(f"[yellow]No receivers found for {library}.{journal}[/yellow]")
                return
        
        config = load_config(config_path)
        
        with AS400ConnectionManager(config) as conn:
            jrn = JournalManager(conn)
            receivers = jrn.get_receiver_chain(journal, library)
            
            if output_format == "json":
                print_json_clean(receivers)
            else:
                if receivers:
                    rows = []
                    for r in receivers:
                        status_icon = "\U0001f7e2" if r['status'] == 'ATTACHED' else "\U0001f535" if r['status'] == 'ONLINE' else "\u26aa"
                        cleanup = "[red]KEEP (Attached)[/red]" if r['status'] == 'ATTACHED' else "[green]Safe to cleanup[/green]"
                        rows.append([
                            r['receiver_name'],
                            r['status'],
                            f"{r['entries']:,}" if r['entries'] else "N/A",
                            f"{r['size_mb']:.2f} MB" if r['size_mb'] else "N/A",
                            cleanup
                        ])
                    
                    console.print(print_table(
                        console,
                        ["Receiver", "Status", "Entries", "Size", "Cleanup Status"],
                        rows,
                        title=f"Journal Receivers: {library}.{journal}"
                    ))
                    
                    # Summary
                    total_receivers = len(receivers)
                    attached = sum(1 for r in receivers if r['status'] == 'ATTACHED')
                    online = sum(1 for r in receivers if r['status'] == 'ONLINE')
                    console.print(f"\n[blue]Summary:[/blue] {total_receivers} receivers total ({attached} attached, {online} online, {total_receivers - attached - online} other)")
                    if online > 0:
                        console.print(f"[yellow]Tip:[/yellow] {online} receiver(s) can be saved and deleted to free space")
                else:
                    console.print(f"[yellow]No receivers found for {library}.{journal}[/yellow]")
    
    except ConnectionError as e:
        console.print(f"[red]Connection error: {e.message}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@journal.command("cleanup")
@click.option("--journal", "-j", required=True, help="Journal name")
@click.option("--library", "-l", required=True, help="Library name")
@click.option("--keep", "-k", default=2, help="Number of recent receivers to keep (default: 2)")
@click.option("--dry-run", is_flag=True, help="Show what would be deleted without executing")
@click.option("--force", is_flag=True, help="Force delete by auto-answering the 'receiver not saved' inquiry (CPA7025). Prevents hanging in MSGW status.")
@click.pass_context
def journal_cleanup(ctx: click.Context, journal: str, library: str, keep: int, dry_run: bool, force: bool) -> None:
    """Clean up old journal receivers (keeps attached + N recent)."""
    config_path = ctx.obj["config_path"]
    
    try:
        # Check if agent is available (no JVM needed in CLI)
        agent_url = os.environ.get("QADMCLI_AGENT_URL")
        if agent_url:
            from ..db.agent_client import AS400AgentClient
            client = AS400AgentClient(agent_url)
            if client.is_available():
                recv_result = client.query(
                    "SELECT JOURNAL_RECEIVER_LIBRARY, JOURNAL_RECEIVER_NAME, "
                    "NUMBER_OF_JOURNAL_ENTRIES, STATUS, SIZE "
                    "FROM QSYS2.JOURNAL_RECEIVER_INFO "
                    "WHERE JOURNAL_LIBRARY = ? AND JOURNAL_NAME = ? "
                    "ORDER BY CASE STATUS WHEN 'ATTACHED' THEN 1 "
                    "WHEN 'ONLINE' THEN 2 ELSE 3 END, JOURNAL_RECEIVER_NAME",
                    params=[library.upper(), journal.upper()]
                )

                receivers = []
                for row in recv_result.get("rows", []):
                    size_bytes = int(row[4]) if row[4] else 0
                    size_mb = size_bytes / (1024 * 1024) if size_bytes else 0
                    receivers.append({
                        'receiver_library': str(row[0]) if row[0] else '',
                        'receiver_name': str(row[1]) if row[1] else '',
                        'entries': int(row[2]) if row[2] else 0,
                        'status': str(row[3]) if row[3] else 'UNKNOWN',
                        'size_bytes': size_bytes,
                        'size_mb': size_mb
                    })

                attached = [r for r in receivers if r['status'] == 'ATTACHED']
                online = [r for r in receivers if r['status'] == 'ONLINE']
                others = [r for r in receivers if r['status'] not in ('ATTACHED', 'ONLINE')]

                to_keep = attached.copy()
                to_delete = []
                if len(online) > keep:
                    to_keep.extend(online[-keep:])
                    to_delete = online[:-keep]
                to_delete.extend(others)

                plan = {
                    'journal_library': library.upper(),
                    'journal_name': journal.upper(),
                    'keeping': len(to_keep),
                    'deleting': len(to_delete),
                    'space_mb': sum(r['size_mb'] for r in to_delete),
                    'entries': sum(r['entries'] for r in to_delete),
                    'to_keep': to_keep,
                    'to_delete': to_delete,
                }

                if not plan['to_delete']:
                    console.print(f"[green]No receivers to clean up for {library}.{journal}[/green]")
                    return

                console.print(f"\n[blue]Cleanup Plan for {library}.{journal}:[/blue]")
                console.print(f"Keeping: {plan['keeping']} receiver(s)")
                console.print(f"Deleting: {plan['deleting']} receiver(s)")
                console.print(f"Space to free: {plan['space_mb']:.2f} MB\n")

                if plan['to_delete']:
                    rows = []
                    for r in plan['to_delete']:
                        rows.append([r['receiver_name'], f"{r['entries']:,}", f"{r['size_mb']:.2f} MB"])
                    console.print(print_table(
                        console, ["Receiver", "Entries", "Size"], rows, title="Receivers to Delete"
                    ))

                if dry_run:
                    console.print(f"\n[yellow]Dry run mode - no changes made[/yellow]")
                    console.print(f"Run without --dry-run to execute cleanup")
                else:
                    if force:
                        console.print(f"\n[yellow]Force mode: auto-answering 'receiver not saved' inquiry (CPA7025)[/yellow]")
                    console.print(f"\n[yellow]Executing cleanup...[/yellow]")

                    results = []
                    for r in plan['to_delete']:
                        try:
                            if force:
                                chgjob_cmd = "CHGJOB INQMSGRPY(*DFT)"
                                client.execute(
                                    "CALL QSYS2.QCMDEXC(?, ?)",
                                    params=[chgjob_cmd, len(chgjob_cmd.encode('utf-8'))]
                                )
                            cmd = f"DLTJRNRCV JRNRCV({r['receiver_library']}/{r['receiver_name']})"
                            client.execute("CALL QSYS2.QCMDEXC(?, ?)", params=[cmd, len(cmd.encode('utf-8'))])
                            results.append({'receiver_name': r['receiver_name'], 'success': True, 'error': None})
                            if force:
                                reset_cmd = "CHGJOB INQMSGRPY(*RQD)"
                                client.execute(
                                    "CALL QSYS2.QCMDEXC(?, ?)",
                                    params=[reset_cmd, len(reset_cmd.encode('utf-8'))]
                                )
                        except Exception as e:
                            results.append({'receiver_name': r['receiver_name'], 'success': False, 'error': str(e)})

                    success = sum(1 for r in results if r['success'])
                    failed = len(results) - success
                    console.print(f"[green]Cleanup complete:[/green] {success} deleted, {failed} failed")
                    if failed > 0:
                        for r in results:
                            if not r['success']:
                                console.print(f"[red]Failed:[/red] {r['receiver_name']} - {r['error']}")
                return

        config = load_config(config_path)
        
        with AS400ConnectionManager(config) as conn:
            jrn = JournalManager(conn)
            
            # Get cleanup plan
            plan = jrn.get_cleanup_plan(journal, library, keep)
            
            if not plan['to_delete']:
                console.print(f"[green]No receivers to clean up for {library}.{journal}[/green]")
                return
            
            # Show plan
            console.print(f"\n[blue]Cleanup Plan for {library}.{journal}:[/blue]")
            console.print(f"Keeping: {plan['keeping']} receiver(s)")
            console.print(f"Deleting: {plan['deleting']} receiver(s)")
            console.print(f"Space to free: {plan['space_mb']:.2f} MB\n")
            
            if plan['to_delete']:
                rows = []
                for r in plan['to_delete']:
                    rows.append([r['receiver_name'], f"{r['entries']:,}", f"{r['size_mb']:.2f} MB"])
                console.print(print_table(
                    console,
                    ["Receiver", "Entries", "Size"],
                    rows,
                    title="Receivers to Delete"
                ))
            
            if dry_run:
                console.print(f"\n[yellow]Dry run mode - no changes made[/yellow]")
                console.print(f"Run without --dry-run to execute cleanup")
            else:
                if force:
                    console.print(f"\n[yellow]Force mode: auto-answering 'receiver not saved' inquiry (CPA7025)[/yellow]")
                console.print(f"\n[yellow]Executing cleanup...[/yellow]")
                results = jrn.execute_cleanup(plan, force=force)
                
                success = sum(1 for r in results if r['success'])
                failed = len(results) - success
                
                console.print(f"[green]Cleanup complete:[/green] {success} deleted, {failed} failed")
                
                if failed > 0:
                    for r in results:
                        if not r['success']:
                            console.print(f"[red]Failed:[/red] {r['receiver_name']} - {r['error']}")

    
    except ConnectionError as e:
        console.print(f"[red]Connection error: {e.message}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@journal.command("monitor")
@click.option("--library", "-l", help="Monitor specific library")
@click.option("--threshold", "-t", default=1000000, help="Entry count threshold for warning (default: 1M)")
@click.option("--format", "-f", "output_format", type=click.Choice(["table", "json"]), default="table", help="Output format (default: table)")
@click.pass_context
def journal_monitor(ctx: click.Context, library: str | None, threshold: int, output_format: str) -> None:
    """Monitor journal sizes and alert on large journals."""
    config_path = ctx.obj["config_path"]
    
    try:
        # Check if agent is available (no JVM needed in CLI)
        agent_url = os.environ.get("QADMCLI_AGENT_URL")
        if agent_url:
            from ..db.agent_client import AS400AgentClient
            client = AS400AgentClient(agent_url)
            if client.is_available():
                sql = (
                    "SELECT JOURNAL_LIBRARY, JOURNAL_NAME, "
                    "COUNT(*) as RECEIVER_COUNT, "
                    "SUM(NUMBER_OF_JOURNAL_ENTRIES) as TOTAL_ENTRIES, "
                    "MAX(CASE WHEN STATUS = 'ATTACHED' THEN JOURNAL_RECEIVER_NAME END) as ATTACHED_RECEIVER "
                    "FROM QSYS2.JOURNAL_RECEIVER_INFO "
                    "WHERE 1=1"
                )
                params = []
                if library:
                    sql += " AND JOURNAL_LIBRARY = ?"
                    params.append(library.upper())
                sql += " GROUP BY JOURNAL_LIBRARY, JOURNAL_NAME ORDER BY TOTAL_ENTRIES DESC"
                
                result = client.query(sql, params=params if params else None)
                rows_data = result.get("rows", [])
                
                alerts = []
                table_rows = []
                journals_list = []
                for row in rows_data:
                    j_lib = row[0] or ""
                    j_name = row[1] or ""
                    recv_count = row[2] or 0
                    total_entries = row[3] or 0
                    
                    if total_entries > threshold * 5:
                        status = "[red]CRITICAL[/red]"
                        alerts.append(f"{j_lib}.{j_name}: {total_entries:,} entries")
                    elif total_entries > threshold:
                        status = "[yellow]WARNING[/yellow]"
                        alerts.append(f"{j_lib}.{j_name}: {total_entries:,} entries")
                    else:
                        status = "[green]OK[/green]"
                    
                    table_rows.append([
                        f"{j_lib}.{j_name}",
                        f"{total_entries:,}",
                        str(recv_count),
                        status
                    ])
                    journals_list.append({
                        "journal_library": j_lib,
                        "journal_name": j_name,
                        "total_entries": total_entries,
                        "receiver_count": recv_count
                    })
                
                if output_format == "json":
                    from ..utils.formatters import print_json_clean
                    print_json_clean({
                        'journals': journals_list,
                        'alerts': alerts,
                        'threshold': threshold
                    })
                else:
                    from ..utils.formatters import print_table
                    console.print(print_table(
                        console,
                        ["Journal", "Entries", "Receivers", "Status"],
                        table_rows,
                        title=f"Journal Monitor (Threshold: {threshold:,} entries)"
                    ))
                    if alerts:
                        console.print(f"\n[yellow]\u26a0\ufe0f  Alerts ({len(alerts)}):[/yellow]")
                        for alert in alerts:
                            console.print(f"  \u2022 {alert}")
                        console.print(f"\n[blue]Recommendation:[/blue] Use 'journal cleanup' or 'journal receivers' to manage large journals")
                    else:
                        console.print(f"\n[green]\u2713 All journals within threshold[/green]")
                return
        
        config = load_config(config_path)
        
        with AS400ConnectionManager(config) as conn:
            jrn = JournalManager(conn)
            journals = jrn.list_journals(library)
            
            alerts = []
            rows = []
            
            for j in journals:
                entries = j.get('total_entries', 0) or 0
                
                if entries > threshold * 5:
                    status = "[red]CRITICAL[/red]"
                    alerts.append(f"{j['journal_library']}.{j['journal_name']}: {entries:,} entries")
                elif entries > threshold:
                    status = "[yellow]WARNING[/yellow]"
                    alerts.append(f"{j['journal_library']}.{j['journal_name']}: {entries:,} entries")
                else:
                    status = "[green]OK[/green]"
                
                rows.append([
                    f"{j['journal_library']}.{j['journal_name']}",
                    f"{entries:,}",
                    str(j.get('receiver_count', 0)),
                    status
                ])
            
            if output_format == "json":
                print_json_clean({
                    'journals': journals,
                    'alerts': alerts,
                    'threshold': threshold
                })
            else:
                console.print(print_table(
                    console,
                    ["Journal", "Entries", "Receivers", "Status"],
                    rows,
                    title=f"Journal Monitor (Threshold: {threshold:,} entries)"
                ))
                
                if alerts:
                    console.print(f"\n[yellow]⚠️  Alerts ({len(alerts)}):[/yellow]")
                    for alert in alerts:
                        console.print(f"  • {alert}")
                    console.print(f"\n[blue]Recommendation:[/blue] Use 'journal cleanup' or 'journal receivers' to manage large journals")
                else:
                    console.print(f"\n[green]✓ All journals within threshold[/green]")
    
    except ConnectionError as e:
        console.print(f"[red]Connection error: {e.message}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@journal.command("info")
@click.option("--table", "-t", required=True, help="Table name (supports wildcards: * or %)")
@click.option("--library", "-l", required=True, help="Library name")
@click.option("--fast", "-f", is_flag=True, help="Skip slow entry range query (for large journals)")
@click.option("--format", "-F", "output_format", type=click.Choice(["table", "json"]), default="table", help="Output format (default: table)")
@click.pass_context
def journal_info(ctx: click.Context, table: str, library: str, fast: bool, output_format: str) -> None:
    """Get detailed journal information for one or more tables.
    
    Supports wildcards:
      - * or % for multiple characters
      - ? for single character
    
    Examples:
      qadmcli journal info -t TB_01 -l EZPIPE
      qadmcli journal info -t "TB_*" -l EZPIPE --fast
      qadmcli journal info -t "TEST*" -l MYLIB
    """
    config_path = ctx.obj["config_path"]
    
    # Suppress logging for JSON output
    if output_format == "json":
        import logging
        logging.getLogger("qadmcli").setLevel(logging.WARNING)
    
    try:
        # Check if agent is available (no JVM needed in CLI)
        agent_url = os.environ.get("QADMCLI_AGENT_URL")
        if agent_url:
            from ..db.agent_client import AS400AgentClient
            client = AS400AgentClient(agent_url)
            if client.is_available():
                if '*' in table or '%' in table or '?' in table:
                    import fnmatch
                    tables_result = client.query(
                        "SELECT TABLE_NAME FROM QSYS2.SYSTABLES WHERE TABLE_SCHEMA = ?",
                        params=[library.upper()]
                    )
                    pattern = table.replace('%', '*')
                    matched_tables = [
                        r[0] for r in tables_result.get("rows", [])
                        if r[0] and fnmatch.fnmatch(r[0], pattern)
                    ]

                    if not matched_tables:
                        console.print(f"[yellow]No tables matching pattern '{table}' in {library}[/yellow]")
                        return

                    results_list = []
                    console.print(f"[blue]Journal info for {len(matched_tables)} table(s):[/blue]\n")

                    import logging
                    original_level = logging.getLogger("qadmcli").level
                    logging.getLogger("qadmcli").setLevel(logging.WARNING)

                    try:
                        for tbl in matched_tables:
                            try:
                                info = _agent_get_journal_info(client, tbl, library, skip_entry_range=fast)
                                results_list.append({
                                    "table": f"{library}.{tbl}",
                                    "info": info.model_dump()
                                })

                                images_display = info.journal_images or "N/A"
                                if images_display == "*BOTH":
                                    images_display = "BOTH"
                                elif images_display == "*AFTER":
                                    images_display = "AFTER"
                                elif images_display == "*BEFORE":
                                    images_display = "BEFORE"

                                status = "Journaled" if info.is_journaled else "Not Journaled"
                                journal_str = f"{info.journal_library}.{info.journal_name}" if info.journal_library else "N/A"
                                console.print(f"  {library}.{tbl}: {status} | {images_display} | {journal_str}")
                            except Exception as e:
                                results_list.append({"table": f"{library}.{tbl}", "error": str(e)})
                                console.print(f"  [red]ERR[/red] {library}.{tbl}: {e}")
                    finally:
                        logging.getLogger("qadmcli").setLevel(original_level)

                    if output_format == "json":
                        from ..utils.formatters import print_json_clean
                        print_json_clean({
                            "pattern": table,
                            "library": library,
                            "tables": results_list
                        })
                else:
                    info = _agent_get_journal_info(client, table, library, skip_entry_range=fast)

                    if output_format == "json":
                        from ..utils.formatters import print_json_clean
                        print_json_clean(info.model_dump())
                    else:
                        images_display = info.journal_images or "N/A"
                        if images_display == "*BOTH":
                            images_display = "BOTH (Before & After)"
                        elif images_display == "*AFTER":
                            images_display = "AFTER (After image only)"
                        elif images_display == "*BEFORE":
                            images_display = "BEFORE (Before image only)"

                        content = Text.assemble(
                            ("Table: ", "bold"), f"{library}.{table}", "\n\n",
                            ("Journal Status:\n", "bold underline"),
                            ("  Journaled: ", "bold"), ("Yes" if info.is_journaled else "No"), "\n",
                            ("  Journal: ", "bold"), (f"{info.journal_library}.{info.journal_name}" if info.journal_library else "N/A"), "\n",
                            ("  Write Mode: ", "bold"), images_display, "\n",
                            ("  Receiver: ", "bold"), (f"{info.journal_receiver_library}.{info.journal_receiver_name}" if info.journal_receiver_library else "N/A"), "\n",
                            ("  Receiver Attached: ", "bold"), str(info.receiver_attach_timestamp or "N/A"), "\n",
                            ("  Receiver Detached: ", "bold"), str(info.receiver_detach_timestamp or "Still attached"), "\n\n",
                            ("Table Entry Range:\n", "bold underline"),
                            ("  Oldest Sequence: ", "bold"), str(info.oldest_entry_sequence or "N/A"), "\n",
                            ("  Newest Sequence: ", "bold"), str(info.newest_entry_sequence or "N/A"), "\n",
                            ("  Oldest Time: ", "bold"), str(info.oldest_entry_timestamp or "N/A"), "\n",
                            ("  Newest Time: ", "bold"), str(info.newest_entry_timestamp or "N/A"), "\n",
                            ("  Total Entries: ", "bold"), str(info.total_entries or "N/A"),
                        )
                        print_panel(ctx, content, title="Detailed Journal Information", border_style="blue")
                return

        config = load_config(config_path)
        
        with AS400ConnectionManager(config) as conn:
            jrn = JournalManager(conn)
            
            # Check if wildcard pattern (* and ? are shell-style, % is SQL-style)
            if '*' in table or '%' in table or '?' in table:
                # Find matching tables
                from ..db.schema import SchemaManager
                import fnmatch
                schema_mgr = SchemaManager(conn)
                all_tables = schema_mgr.list_tables(library)
                
                # Filter tables by pattern
                pattern = table.replace('%', '*')
                tables = [t for t in all_tables if fnmatch.fnmatch(t.name, pattern)]
                
                if not tables:
                    console.print(f"[yellow]No tables matching pattern '{table}' in {library}[/yellow]")
                    return
                
                # Process each table
                results = []
                console.print(f"[blue]Journal info for {len(tables)} table(s):[/blue]\n")
                
                # Temporarily suppress INFO logging for cleaner batch output
                import logging
                original_level = logging.getLogger("qadmcli").level
                logging.getLogger("qadmcli").setLevel(logging.WARNING)
                
                try:
                    for table in tables:
                        try:
                            info = jrn.get_journal_info(table.name, library, skip_entry_range=fast)
                            results.append({
                                "table": f"{library}.{table.name}",
                                "info": info.model_dump()
                            })
                            
                            # Format journal images for display
                            images_display = info.journal_images or "N/A"
                            if images_display == "*BOTH":
                                images_display = "BOTH"
                            elif images_display == "*AFTER":
                                images_display = "AFTER"
                            elif images_display == "*BEFORE":
                                images_display = "BEFORE"
                            
                            # Compact display for batch mode
                            status = "Journaled" if info.is_journaled else "Not Journaled"
                            journal_info = f"{info.journal_library}.{info.journal_name}" if info.journal_library else "N/A"
                            console.print(f"  {library}.{table.name}: {status} | {images_display} | {journal_info}")
                            
                        except Exception as e:
                            results.append({
                                "table": f"{library}.{table.name}",
                                "error": str(e)
                            })
                            console.print(f"  [red]ERR[/red] {library}.{table.name}: {e}")
                finally:
                    # Restore original logging level
                    logging.getLogger("qadmcli").setLevel(original_level)
                
                if output_format == "json":
                    print_json_clean({
                        "pattern": table,
                        "library": library,
                        "tables": results
                    })
            else:
                # Single table
                info = jrn.get_journal_info(table, library, skip_entry_range=fast)
                
                if output_format == "json":
                    print_json_clean(info.model_dump())
                else:
                    # Format journal images for display
                    images_display = info.journal_images or "N/A"
                    if images_display == "*BOTH":
                        images_display = "BOTH (Before & After)"
                    elif images_display == "*AFTER":
                        images_display = "AFTER (After image only)"
                    elif images_display == "*BEFORE":
                        images_display = "BEFORE (Before image only)"
                    
                    content = Text.assemble(
                        ("Table: ", "bold"), f"{library}.{table}", "\n\n",
                        ("Journal Status:\n", "bold underline"),
                        ("  Journaled: ", "bold"), ("Yes" if info.is_journaled else "No"), "\n",
                        ("  Journal: ", "bold"), (f"{info.journal_library}.{info.journal_name}" if info.journal_library else "N/A"), "\n",
                        ("  Write Mode: ", "bold"), images_display, "\n",
                        ("  Receiver: ", "bold"), (f"{info.journal_receiver_library}.{info.journal_receiver_name}" if info.journal_receiver_library else "N/A"), "\n",
                        ("  Receiver Attached: ", "bold"), str(info.receiver_attach_timestamp or "N/A"), "\n",
                        ("  Receiver Detached: ", "bold"), str(info.receiver_detach_timestamp or "Still attached"), "\n\n",
                        ("Table Entry Range:\n", "bold underline"),
                        ("  Oldest Sequence: ", "bold"), str(info.oldest_entry_sequence or "N/A"), "\n",
                        ("  Newest Sequence: ", "bold"), str(info.newest_entry_sequence or "N/A"), "\n",
                        ("  Oldest Time: ", "bold"), str(info.oldest_entry_timestamp or "N/A"), "\n",
                        ("  Newest Time: ", "bold"), str(info.newest_entry_timestamp or "N/A"), "\n",
                        ("  Total Entries: ", "bold"), str(info.total_entries or "N/A"),
                    )
                    print_panel(ctx, content, title="Detailed Journal Information", border_style="blue")
        
    except ConnectionError as e:
        console.print(f"[red]Connection error: {e.message}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@journal.command("last-txn")
@click.option("--table", "-t", "tables", required=True, multiple=True,
              help="Table in Library.Table format (can be specified multiple times)")
@click.option("--format", "-f", "output_format", type=click.Choice(["table", "json"]),
              default="table", help="Output format (default: table)")
@click.pass_context
def journal_last_txn(ctx: click.Context, tables: tuple[str], output_format: str) -> None:
    """Get last transaction sequence and timestamp for table(s).

    Queries the attached journal receiver for LAST_SEQUENCE_NUMBER
    and converts the attach timestamp to .NET ticks, providing both
    TransactionID (sequence) and TransactionTS (ticks) as used by
    Syniti Replicate metadata.

    Examples:

      qadmcli journal last-txn -t SYNITI.CHDRPF50

      qadmcli journal last-txn -t SYNITI.CHDRPF50 -t SYNITI.DEMOTABLETEST_2

      qadmcli journal last-txn -t SYNITI.CHDRPF50 -f json
    """
    config_path = ctx.obj["config_path"]

    if output_format == "json":
        import logging
        logging.getLogger("qadmcli").setLevel(logging.WARNING)

    try:
        # Check if agent is available (no JVM needed in CLI)
        agent_url = os.environ.get("QADMCLI_AGENT_URL")
        if agent_url:
            from ..db.agent_client import AS400AgentClient
            client = AS400AgentClient(agent_url)
            if client.is_available():
                results = []
                for table_ref in tables:
                    parts = table_ref.split(".")
                    if len(parts) != 2:
                        results.append({
                            "table": table_ref,
                            "error": f"Invalid format: expected Library.Table, got '{table_ref}'"
                        })
                        continue

                    lib, tbl = parts[0].upper(), parts[1].upper()

                    try:
                        info = _agent_get_journal_info(client, tbl, lib, skip_entry_range=True)

                        # Check if entry info was populated (only when skip_entry_range=False)
                        has_entry_info = not info.is_journaled or getattr(info, 'newest_entry_timestamp', None) is not None
                        if not has_entry_info and info.is_journaled and info.journal_library and info.journal_name:
                            # Lightweight: try DISPLAY_JOURNAL for just the last entry (FETCH FIRST 1)
                            # This is faster than the full entry range query
                            try:
                                sys_name = info.table_name
                                sys_result = client.query(
                                    "SELECT SYSTEM_TABLE_NAME FROM QSYS2.SYSTABLES "
                                    "WHERE TABLE_NAME = ? AND TABLE_SCHEMA = ?",
                                    params=[tbl, lib]
                                )
                                if sys_result["row_count"] > 0 and sys_result["rows"][0][0]:
                                    sys_name = str(sys_result["rows"][0][0]).strip()
                                obj_pattern = f"%{sys_name}%"
                                last_entry = client.query(
                                    "SELECT SEQUENCE_NUMBER, ENTRY_TIMESTAMP "
                                    "FROM TABLE (QSYS2.DISPLAY_JOURNAL("
                                    "JOURNAL_LIBRARY => ?, JOURNAL_NAME => ?)) "
                                    "WHERE OBJECT LIKE ? "
                                    "ORDER BY SEQUENCE_NUMBER DESC FETCH FIRST 1 ROW ONLY",
                                    params=[info.journal_library, info.journal_name, obj_pattern]
                                )
                                if last_entry["row_count"] > 0:
                                    info.newest_entry_sequence = last_entry["rows"][0][0]
                                    info.newest_entry_timestamp = str(last_entry["rows"][0][1]) if last_entry["rows"][0][1] else None
                            except Exception:
                                pass  # Fall back to attach info only

                        if not info.is_journaled:
                            results.append({
                                "table": f"{lib}.{tbl}",
                                "journaled": False,
                                "error": "Table is not journaled"
                            })
                            continue

                        if not info.journal_library or not info.journal_name:
                            results.append({
                                "table": f"{lib}.{tbl}",
                                "journaled": True,
                                "error": "Could not determine journal for table"
                            })
                            continue

                        # Query attached receiver for ATTACH_TIMESTAMP
                        recv_result = client.query(
                            "SELECT LAST_SEQUENCE_NUMBER, ATTACH_TIMESTAMP, "
                            "JOURNAL_RECEIVER_NAME, JOURNAL_RECEIVER_LIBRARY, STATUS "
                            "FROM QSYS2.JOURNAL_RECEIVER_INFO "
                            "WHERE JOURNAL_LIBRARY = ? AND JOURNAL_NAME = ? "
                            "AND STATUS = 'ATTACHED' FETCH FIRST 1 ROW ONLY",
                            params=[info.journal_library, info.journal_name]
                        )

                        if recv_result["row_count"] == 0 or recv_result["rows"][0][0] is None:
                            results.append({
                                "table": f"{lib}.{tbl}",
                                "journaled": True,
                                "journal": f"{info.journal_library}.{info.journal_name}",
                                "error": "No attached receiver with entries found"
                            })
                            continue

                        recv_row = recv_result["rows"][0]
                        attach_ts = str(recv_row[1]) if recv_row[1] else None
                        receiver_name = str(recv_row[2]) if recv_row[2] else None
                        receiver_lib = str(recv_row[3]) if recv_row[3] else None

                        # Get per-table entry info (from lightweight DISPLAY_JOURNAL query above, or None)
                        entry_seq = info.newest_entry_sequence
                        entry_ts = info.newest_entry_timestamp

                        # Convert attach timestamp to .NET ticks (Syniti Replicate compatibility)
                        transaction_ts = None
                        if attach_ts:
                            from datetime import datetime
                            dt = datetime.strptime(attach_ts.split('.')[0], "%Y-%m-%d %H:%M:%S")
                            transaction_ts = _dt_to_dotnet_ticks(dt)

                        results.append({
                            "table": f"{lib}.{tbl}",
                            "journaled": True,
                            "journal": f"{info.journal_library}.{info.journal_name}",
                            "journal_library": info.journal_library,
                            "journal_name": info.journal_name,
                            "receiver_library": receiver_lib,
                            "receiver_name": receiver_name,
                            "attach_timestamp": attach_ts,
                            "entry_sequence": int(entry_seq) if entry_seq is not None else None,
                            "entry_timestamp": entry_ts,
                            "transaction_ts": transaction_ts,
                        })
                    except Exception as e:
                        results.append({
                            "table": f"{lib}.{tbl}",
                            "error": str(e)
                        })

                if output_format == "json":
                    from ..utils.formatters import print_json_clean
                    print_json_clean(results)
                else:
                    rows = []
                    for r in results:
                        if "error" in r:
                            rows.append([
                                r.get("table", "?"),
                                "[red]ERROR[/red]",
                                r.get("error", "Unknown error"),
                                "\u2014", "\u2014"
                            ])
                        else:
                            entry_seq_display = str(int(r["entry_sequence"])) if r.get("entry_sequence") is not None else "—"
                            entry_ts_display = r.get("entry_timestamp") or "\u2014"
                            attach_ts_display = r.get("attach_timestamp") or "\u2014"
                            rows.append([
                                r["table"],
                                r["journal"],
                                entry_seq_display,
                                entry_ts_display,
                                attach_ts_display,
                            ])

                    console.print(print_table(
                        console,
                        ["Table", "Journal", "Seq#", "Entry TS (SQL)", "Attach TS (Receiver)"],
                        rows,
                        title="Last Transaction Info"
                    ))
                    console.print("[dim]Tip: Use 'tick_convert.py <TransactionTS>' to convert attach ticks[/dim]")
                return

        config = load_config(config_path)

        with AS400ConnectionManager(config) as conn:
            jrn = JournalManager(conn)
            results = jrn.get_last_transaction(list(tables))

            if output_format == "json":
                print_json_clean(results)
            else:
                rows = []
                for r in results:
                    if "error" in r:
                        rows.append([
                            r.get("table", "?"),
                            "[red]ERROR[/red]",
                            r.get("error", "Unknown error"),
                            "—", "—"
                        ])
                    else:
                        entry_seq_display = str(int(r["entry_sequence"])) if r.get("entry_sequence") is not None else "—"
                        entry_ts_display = r.get("entry_timestamp") or "—"
                        attach_ts_display = r.get("attach_timestamp") or "—"
                        rows.append([
                            r["table"],
                            r["journal"],
                            entry_seq_display,
                            entry_ts_display,
                            attach_ts_display,
                        ])

                console.print(print_table(
                    console,
                    ["Table", "Journal", "Seq#", "Entry TS (SQL)", "Attach TS (Receiver)"],
                    rows,
                    title="Last Transaction Info"
                ))
                console.print("[dim]Tip: Use 'tick_convert.py <TransactionTS>' to convert attach ticks[/dim]")

    except ConnectionError as e:
        console.print(f"[red]Connection error: {e.message}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@journal.command("create-receiver")
@click.option("--name", "-n", required=True, help="Journal receiver name")
@click.option("--library", "-l", required=True, help="Library for journal receiver")
@click.option("--threshold", "-t", default="*NONE", help="Size threshold (e.g., '100000' or '*NONE')")
@click.option("--format", "-F", "output_format", type=click.Choice(["table", "json"]), default="table", help="Output format (default: table)")
@click.pass_context
def journal_create_receiver(
    ctx: click.Context,
    name: str,
    library: str,
    threshold: str,
    output_format: str
) -> None:
    """Create a standalone journal receiver (not attached to any journal)."""
    config_path = ctx.obj["config_path"]
    
    try:
        # Check if agent is available (no JVM needed in CLI)
        agent_url = os.environ.get("QADMCLI_AGENT_URL")
        if agent_url:
            from ..db.agent_client import AS400AgentClient
            client = AS400AgentClient(agent_url)
            if client.is_available():
                cmd = f"CRTJRNRCV JRNRCV({library.upper()}/{name.upper()})"
                if threshold != "*NONE":
                    cmd += f" THRESHOLD({threshold})"
                client.execute(
                    "CALL QSYS2.QCMDEXC(?, ?)",
                    params=[cmd, len(cmd.encode('utf-8'))]
                )
                console.print(f"[green]Created journal receiver {library}.{name}[/green]")
                console.print("[yellow]Note: Receiver is not attached to any journal.[/yellow]")
                console.print("Use 'journal rollover' to attach it to a journal.")
                if threshold != "*NONE":
                    console.print(f"Threshold: {threshold} KB")
                return

        config = load_config(config_path)
        
        with AS400ConnectionManager(config) as conn:
            jrn = JournalManager(conn)
            result = jrn.create_journal_receiver(name, library, threshold)
            
            console.print(f"[green]Created journal receiver {library}.{name}[/green]")
            console.print("[yellow]Note: Receiver is not attached to any journal.[/yellow]")
            console.print("Use 'journal rollover' to attach it to a journal.")
            if threshold != "*NONE":
                console.print(f"Threshold: {threshold} KB")
        
    except ConnectionError as e:
        console.print(f"[red]Connection error: {e.message}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@journal.command("rollover")
@click.option("--journal", "-j", required=True, help="Journal name")
@click.option("--library", "-l", required=True, help="Library name")
@click.option("--receiver", "-r", help="New receiver name (auto-generated if not specified)")
@click.option("--receiver-library", "-rl", help="Library for new receiver (defaults to journal library)")
@click.pass_context
def journal_rollover(
    ctx: click.Context,
    journal: str,
    library: str,
    receiver: str | None,
    receiver_library: str | None
) -> None:
    """Rollover journal to a new receiver (detaches current, attaches new).
    
    This creates a new receiver and attaches it to the journal, automatically
    detaching the current receiver. The detached receiver becomes ONLINE status
    and can be cleaned up later.
    """
    config_path = ctx.obj["config_path"]
    
    try:
        # Check if agent is available (no JVM needed in CLI)
        agent_url = os.environ.get("QADMCLI_AGENT_URL")
        if agent_url:
            from ..db.agent_client import AS400AgentClient
            client = AS400AgentClient(agent_url)
            if client.is_available():
                recv_result = client.query(
                    "SELECT JOURNAL_RECEIVER_LIBRARY, JOURNAL_RECEIVER_NAME, STATUS "
                    "FROM QSYS2.JOURNAL_RECEIVER_INFO "
                    "WHERE JOURNAL_LIBRARY = ? AND JOURNAL_NAME = ? "
                    "ORDER BY CASE STATUS WHEN 'ATTACHED' THEN 1 "
                    "WHEN 'ONLINE' THEN 2 ELSE 3 END, JOURNAL_RECEIVER_NAME",
                    params=[library.upper(), journal.upper()]
                )
                old_name = "Unknown"
                for row in recv_result.get("rows", []):
                    if len(row) > 2 and row[2] == 'ATTACHED':
                        old_name = str(row[1]) if row[1] else "Unknown"
                        break

                recv_lib = receiver_library or library
                if receiver:
                    cmd = f"CHGJRN JRN({library.upper()}/{journal.upper()}) JRNRCV({recv_lib.upper()}/{receiver.upper()})"
                else:
                    cmd = f"CHGJRN JRN({library.upper()}/{journal.upper()}) JRNRCV(*GEN)"

                client.execute("CALL QSYS2.QCMDEXC(?, ?)", params=[cmd, len(cmd.encode('utf-8'))])

                console.print(f"[green]Journal rollover complete:[/green] {library}.{journal}")

                new_recv = client.query(
                    "SELECT JOURNAL_RECEIVER_NAME FROM QSYS2.JOURNAL_RECEIVER_INFO "
                    "WHERE JOURNAL_LIBRARY = ? AND JOURNAL_NAME = ? AND STATUS = 'ATTACHED' "
                    "FETCH FIRST 1 ROW ONLY",
                    params=[library.upper(), journal.upper()]
                )
                new_name = "Unknown"
                if new_recv["row_count"] > 0 and new_recv["rows"][0][0]:
                    new_name = str(new_recv["rows"][0][0])

                console.print(f"  Old receiver: {old_name} (now ONLINE)")
                console.print(f"  New receiver: {new_name} (now ATTACHED)")
                console.print(f"\n[blue]Tip:[/blue] Use 'journal receivers -j {journal} -l {library}' to view the chain")
                console.print(f"      Use 'journal cleanup -j {journal} -l {library}' to remove old receivers")
                return

        config = load_config(config_path)
        
        with AS400ConnectionManager(config) as conn:
            jrn = JournalManager(conn)
            
            # Get current receiver before rollover
            old_receivers = jrn.get_receiver_chain(journal, library)
            old_attached = [r for r in old_receivers if r['status'] == 'ATTACHED']
            old_name = old_attached[0]['receiver_name'] if old_attached else 'Unknown'
            
            # Perform rollover
            result = jrn.rollover_journal(journal, library, receiver, receiver_library)
            
            console.print(f"[green]Journal rollover complete:[/green] {library}.{journal}")
            console.print(f"  Old receiver: {old_name} (now ONLINE)")
            console.print(f"  New receiver: {result['new_receiver']} (now ATTACHED)")
            console.print(f"\n[blue]Tip:[/blue] Use 'journal receivers -j {journal} -l {library}' to view the chain")
            console.print(f"      Use 'journal cleanup -j {journal} -l {library}' to remove old receivers")
        
    except ConnectionError as e:
        console.print(f"[red]Connection error: {e.message}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@journal.command("create")
@click.option("--name", "-n", required=True, help="Journal name")
@click.option("--library", "-l", required=True, help="Library for journal")
@click.option("--receiver", "-r", required=True, help="Journal receiver name")
@click.option("--receiver-library", "-rl", help="Journal receiver library (defaults to journal library)")
@click.option("--msg-queue", "-m", default="*NONE", help="Message queue for journal messages")
@click.option("--format", "-F", "output_format", type=click.Choice(["table", "json"]), default="table", help="Output format (default: table)")
@click.pass_context
def journal_create(
    ctx: click.Context,
    name: str,
    library: str,
    receiver: str,
    receiver_library: str | None,
    msg_queue: str,
    output_format: str
) -> None:
    """Create a journal."""
    config_path = ctx.obj["config_path"]
    
    try:
        # Check if agent is available (no JVM needed in CLI)
        agent_url = os.environ.get("QADMCLI_AGENT_URL")
        if agent_url:
            from ..db.agent_client import AS400AgentClient
            client = AS400AgentClient(agent_url)
            if client.is_available():
                recv_lib = receiver_library or library
                cmd = f"CRTJRN JRN({library.upper()}/{name.upper()}) JRNRCV({recv_lib.upper()}/{receiver.upper()})"
                if msg_queue != "*NONE":
                    cmd += f" MSGQ({msg_queue})"
                client.execute(
                    "CALL QSYS2.QCMDEXC(?, ?)",
                    params=[cmd, len(cmd.encode('utf-8'))]
                )
                console.print(f"[green]Created journal {library}.{name}[/green]")
                console.print(f"Attached to receiver: {recv_lib}.{receiver}")
                return

        config = load_config(config_path)
        
        with AS400ConnectionManager(config) as conn:
            jrn = JournalManager(conn)
            result = jrn.create_journal(name, library, receiver, receiver_library, msg_queue)
            
            recv_lib = receiver_library or library
            console.print(f"[green]Created journal {library}.{name}[/green]")
            console.print(f"Attached to receiver: {recv_lib}.{receiver}")
        
    except ConnectionError as e:
        console.print(f"[red]Connection error: {e.message}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)




def register_journal_commands(cli_group):
    """Register journal commands with the main CLI group."""
    cli_group.add_command(journal)
