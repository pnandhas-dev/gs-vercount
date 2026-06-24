"""Library Commands Module.

This module contains library-related CLI commands:
- library create: Create a new library
- library grant: Grant library access to user
- library list: List libraries with wildcard support
- library check: Check library privileges and journal status
"""

import sys
import logging
import fnmatch
from typing import Optional

import click
from rich.console import Console
from rich.text import Text

from ..config import load_config
from ..db.connection import AS400ConnectionManager, ConnectionError
from ..utils.formatters import print_table, print_json_clean
from .utils import print_panel

console = Console()
logger = logging.getLogger(__name__)


@click.group()
def library():
    """Library management commands."""
    pass


@library.command("create")
@click.option("--name", "-n", required=True, help="Library name to create")
@click.option("--user", "-u", help="User to grant authority to (optional)")
@click.option("--authority", "-a", default="*ALL", help="Authority level to grant (*USE, *CHANGE, *ALL)")
@click.option("--format", "-f", "output_format", type=click.Choice(["table", "json"]), default="table", help="Output format (default: table)")
@click.pass_context
def library_create(
    ctx: click.Context,
    name: str,
    user: str | None,
    authority: str,
    output_format: str
) -> None:
    """Create a new library and optionally grant user authority.
    
    Examples:
        qadmcli library create -n NEWLIB
        qadmcli library create -n NEWLIB -u USER001
        qadmcli library create -n NEWLIB -u USER001 -a *CHANGE
    """
    config_path = ctx.obj["config_path"]
    
    try:
        config = load_config(config_path)
        
        with AS400ConnectionManager(config) as conn:
            from ..db.user import UserManager
            user_mgr = UserManager(conn)
            
            # Create the library
            result = user_mgr.create_library(name)
            
            # Grant authority if user specified
            if user:
                grant_result = user_mgr.grant_object_authority(
                    user, name, name, authority, "*LIB"
                )
                result["granted_to"] = user
                result["authority"] = authority
            
            if output_format == "json":
                print_json_clean(result)
            else:
                print_panel(
                    ctx,
                    f"Library {name} created successfully",
                    title="Library Created",
                    border_style="green"
                )
                if user:
                    console.print(f"Granted {authority} authority to {user}")
        
    except ConnectionError as e:
        console.print(f"[red]Connection error: {e.message}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@library.command("grant")
@click.option("--name", "-n", required=True, help="Library name")
@click.option("--user", "-u", required=True, help="User to grant authority to")
@click.option("--authority", "-a", default="*USE", help="Authority level (*USE, *CHANGE, *ALL)")
@click.option("--format", "-f", "output_format", type=click.Choice(["table", "json"]), default="table", help="Output format (default: table)")
@click.pass_context
def library_grant(
    ctx: click.Context,
    name: str,
    user: str,
    authority: str,
    output_format: str
) -> None:
    """Grant authority to a user on a library.
    
    Examples:
        qadmcli library grant -n MYLIB -u USER001
        qadmcli library grant -n MYLIB -u USER001 -a *ALL
    """
    config_path = ctx.obj["config_path"]
    
    try:
        config = load_config(config_path)
        
        with AS400ConnectionManager(config) as conn:
            from ..db.user import UserManager
            user_mgr = UserManager(conn)
            
            result = user_mgr.grant_object_authority(
                user, name, name, authority, "*LIB"
            )
            
            if output_format == "json":
                print_json_clean(result)
            else:
                print_panel(
                    ctx,
                    f"Granted {authority} authority to {user} on library {name}",
                    title="Authority Granted",
                    border_style="green"
                )
        
    except ConnectionError as e:
        console.print(f"[red]Connection error: {e.message}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@library.command("list")
@click.option("--pattern", "-p", default="*", help="Library name pattern (supports wildcards: *, ?, e.g., GS*, TEST?)")
@click.option("--format", "-f", "output_format", type=click.Choice(["table", "json"]), default="table", help="Output format (default: table)")
@click.pass_context
def library_list(
    ctx: click.Context,
    pattern: str,
    output_format: str
) -> None:
    """List libraries with optional wildcard pattern matching.
    
    Examples:
        qadmcli library list
        qadmcli library list -p GS*
        qadmcli library list -p TEST?
        qadmcli library list -p "*PROD*"
    """
    config_path = ctx.obj["config_path"]
    
    try:
        config = load_config(config_path)
        
        with AS400ConnectionManager(config) as conn:
            # Query system catalogs for libraries (schemas)
            sql = """
                SELECT SCHEMA_NAME
                FROM QSYS2.SYSSCHEMAS
                ORDER BY SCHEMA_NAME
            """
            cursor = conn.execute(sql)
            all_libraries = [str(row[0]) for row in cursor.fetchall()]
            cursor.close()
            
            # Filter by pattern
            if pattern != "*":
                libraries = [lib for lib in all_libraries if fnmatch.fnmatch(lib, pattern)]
            else:
                libraries = all_libraries
            
            if output_format == "json":
                print_json_clean({"pattern": pattern, "count": len(libraries), "libraries": libraries})
            else:
                if libraries:
                    console.print(f"\n[cyan]Libraries matching '{pattern}' ({len(libraries)} found):[/cyan]\n")
                    for lib in libraries:
                        console.print(f"  • {lib}")
                    console.print()
                else:
                    console.print(f"[yellow]No libraries found matching pattern '{pattern}'[/yellow]\n")
        
    except ConnectionError as e:
        console.print(f"[red]Connection error: {e.message}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@library.command("check")
@click.option("--library", "-l", required=True, help="Library name to check")
@click.option("--user", "-u", default=None, help="Specific user to check privileges for")
@click.option("--format", "-f", "output_format", type=click.Choice(["table", "json"]), default="table", help="Output format (default: table)")
@click.pass_context
def library_check(
    ctx: click.Context,
    library: str,
    user: Optional[str],
    output_format: str
) -> None:
    """Check library privileges and journal status.
    
    Shows which users have privileges on the library and whether
    the library has journaling enabled.
    
    Examples:
        qadmcli library check -l GSLIBTST
        qadmcli library check -l GSLIBTST -u USER001
    """
    config_path = ctx.obj["config_path"]
    name = library  # Use 'name' internally for consistency with SQL queries
    
    try:
        config = load_config(config_path)
        
        with AS400ConnectionManager(config) as conn:
            result = {
                "library": name,
                "privileges": [],
                "journaling": {}
            }
            
            # Check privileges - query library authority from SYSSCHEMAS and system tables
            try:
                if user:
                    # Check specific user's authority
                    priv_sql = """
                        SELECT 
                            s.SCHEMA_NAME,
                            s.SCHEMA_OWNER,
                            p.AUTHORIZATION_NAME,
                            p.OBJECT_AUTHORITY
                        FROM QSYS2.SYSSCHEMAS s
                        LEFT JOIN TABLE(QSYS2.OBJECT_PRIVILEGES(s.SCHEMA_NAME, '*', '*LIB')) p
                            ON s.SCHEMA_NAME = p.SYSTEM_OBJECT_NAME
                        WHERE s.SCHEMA_NAME = ?
                        AND p.AUTHORIZATION_NAME = ?
                    """
                    cursor = conn.execute(priv_sql, (name.upper(), user.upper()))
                else:
                    # Check all users with authority
                    priv_sql = """
                        SELECT 
                            s.SCHEMA_NAME,
                            s.SCHEMA_OWNER,
                            p.AUTHORIZATION_NAME,
                            p.OBJECT_AUTHORITY
                        FROM QSYS2.SYSSCHEMAS s
                        LEFT JOIN TABLE(QSYS2.OBJECT_PRIVILEGES(s.SCHEMA_NAME, '*', '*LIB')) p
                            ON s.SCHEMA_NAME = p.SYSTEM_OBJECT_NAME
                        WHERE s.SCHEMA_NAME = ?
                        ORDER BY p.AUTHORIZATION_NAME
                    """
                    cursor = conn.execute(priv_sql, (name.upper(),))
                
                rows = cursor.fetchall()
                cursor.close()
                
                for row in rows:
                    auth_name = str(row[2]) if row[2] else None
                    authority = str(row[3]) if row[3] else None
                    
                    if auth_name and authority:
                        result["privileges"].append({
                            "user": auth_name,
                            "authority": authority
                        })
            except Exception as e:
                # Fallback: just show schema owner
                try:
                    owner_sql = """
                        SELECT SCHEMA_NAME, SCHEMA_OWNER
                        FROM QSYS2.SYSSCHEMAS
                        WHERE SCHEMA_NAME = ?
                    """
                    cursor = conn.execute(owner_sql, (name.upper(),))
                    row = cursor.fetchone()
                    cursor.close()
                    
                    if row:
                        result["privileges"].append({
                            "user": str(row[1]) if row[1] else "unknown",
                            "authority": "*OWNER"
                        })
                except Exception:
                    pass
            
            # Check journal status - use JOURNALED_OBJECTS view (same as journal info command)
            try:
                logger.debug("Journal check: Querying JOURNALED_OBJECTS view")
                
                # Get journal usage statistics - group by journal
                journal_sql = """
                    SELECT 
                        JOURNAL_NAME,
                        JOURNAL_LIBRARY,
                        COUNT(DISTINCT OBJECT_NAME) as table_count
                    FROM QSYS2.JOURNALED_OBJECTS
                    WHERE OBJECT_LIBRARY = ?
                    AND OBJECT_TYPE = '*FILE'
                    GROUP BY JOURNAL_NAME, JOURNAL_LIBRARY
                    ORDER BY table_count DESC
                """
                cursor = conn.execute(journal_sql, (name.upper(),))
                rows = cursor.fetchall()
                cursor.close()
                
                journals = []
                total_journaled = 0
                for row in rows:
                    jrn_name = str(row[0]) if row[0] else None
                    jrn_lib = str(row[1]) if row[1] else None
                    tbl_count = int(row[2]) if row[2] else 0
                    
                    if jrn_name and tbl_count > 0:
                        journals.append({
                            "journal": jrn_name,
                            "journal_library": jrn_lib,
                            "table_count": tbl_count
                        })
                        total_journaled += tbl_count
                        logger.debug(f"Journal check: {jrn_name} ({jrn_lib}) - {tbl_count} tables")
                
                if journals:
                    logger.debug(f"Journal check: SUCCESS - {len(journals)} journal(s), {total_journaled} total tables")
                    
                    result["journaling"] = {
                        "status": "enabled",
                        "total_journaled_tables": total_journaled,
                        "journals": journals
                    }
                    
                    # Check if library has a default journal for auto-journaling new tables
                    # Try OBJECT_STATISTICS to get library attributes
                    try:
                        logger.debug("Journal check: Checking library default journal via OBJECT_STATISTICS")
                        default_jrn_sql = """
                            SELECT 
                                OBJATTRIBUTE,
                                OBJTEXT
                            FROM TABLE(QSYS2.OBJECT_STATISTICS(?, '*LIB'))
                            WHERE OBJNAME = ?
                        """
                        cursor = conn.execute(default_jrn_sql, (name.upper(), name.upper()))
                        row = cursor.fetchone()
                        cursor.close()
                        
                        if row:
                            # Library found, but we need journal info from different source
                            # Try using SQL to check if new objects inherit journaling
                            logger.debug(f"Journal check: Library exists, checking inherit status")
                            
                            # Check OBJECTJOURNAL column in SYSTABLES for recent tables
                            inherit_check_sql = """
                                SELECT 
                                    COUNT(*) as total,
                                    SUM(CASE WHEN JOURNALED = 'YES' AND CREATE_TIMESTAMP > CURRENT_TIMESTAMP - 30 DAYS THEN 1 ELSE 0 END) as recent_journaled
                                FROM QSYS2.SYSTABLES
                                WHERE TABLE_SCHEMA = ?
                                AND TABLE_TYPE = 'BASE TABLE'
                            """
                            cursor = conn.execute(inherit_check_sql, (name.upper(),))
                            row = cursor.fetchone()
                            cursor.close()
                            
                            if row and int(row[0]) > 0:
                                logger.debug(f"Journal check: Library has tables, journaling appears active")
                                result["journaling"]["default_journal"] = {
                                    "auto_journal": "likely",
                                    "message": "New objects likely inherit journaling (*YES) - verify with DSPLIBD"
                                }
                            else:
                                result["journaling"]["default_journal"] = {
                                    "auto_journal": "unknown",
                                    "message": "Unable to determine - use DSPLIBD LIB(name) on AS400"
                                }
                        else:
                            logger.debug(f"Journal check: Library not found in OBJECT_STATISTICS")
                            result["journaling"]["default_journal"] = {
                                "auto_journal": "unknown",
                                "message": "Unable to determine auto-journal status"
                            }
                    except Exception as e:
                        logger.debug(f"Journal check: Failed to get default journal - {e}")
                        error_msg = str(e)
                        # Provide helpful guidance
                        result["journaling"]["default_journal"] = {
                            "auto_journal": "unknown",
                            "message": f"Use DSPLIBD LIB({name.upper()}) on AS400 to check auto-journal status"
                        }
                else:
                    logger.debug(f"Journal check: No journaled tables found")
                    result["journaling"] = {
                        "status": "disabled",
                        "message": "No journaled tables found"
                    }
            except Exception as e:
                logger.debug(f"Journal check: FAILED - {e}")
                result["journaling"] = {
                    "status": "unknown",
                    "message": f"Journal status unavailable: {str(e)[:100]}"
                }
            
            if output_format == "json":
                print_json_clean(result)
            else:
                # Display privileges
                console.print(f"\n[cyan]Library: {name}[/cyan]\n")
                
                if result["privileges"]:
                    console.print("[bold]User Privileges:[/bold]")
                    for priv in result["privileges"]:
                        username = priv.get("user", "unknown")
                        authority = priv.get("authority", "unknown")
                        console.print(f"  • {username}: {authority}")
                else:
                    if user:
                        console.print(f"[yellow]No privileges found for user '{user}'[/yellow]")
                    else:
                        console.print("[yellow]No user privileges found[/yellow]")
                
                console.print()
                
                # Display journal status
                console.print("[bold]Journal Status:[/bold]")
                journal_info = result["journaling"]
                status = journal_info.get("status", "unknown")
                
                if status == "enabled":
                    console.print(f"  • Status: [green]Enabled[/green]")
                    if journal_info.get("total_journaled_tables") is not None:
                        total = journal_info['total_journaled_tables']
                        console.print(f"  • Total: {total} table(s) journaled")
                    
                    # Show each journal
                    journals = journal_info.get("journals", [])
                    if journals:
                        console.print(f"  • Journals:")
                        for jrn in journals:
                            jrn_name = jrn['journal']
                            jrn_lib = jrn.get('journal_library', 'N/A')
                            tbl_count = jrn['table_count']
                            console.print(f"    - {jrn_name} ({jrn_lib}): {tbl_count} table(s)")
                    
                    # Show default journal (auto-journal for new tables)
                    default_jrn = journal_info.get("default_journal")
                    if default_jrn:
                        auto_status = default_jrn.get("auto_journal")
                        if auto_status == True:
                            jrn_name = default_jrn.get('journal', 'unknown')
                            jrn_lib = default_jrn.get('journal_library', 'unknown')
                            console.print(f"  • [green]Auto-Journal: Enabled[/green]")
                            console.print(f"    New tables will be automatically journaled to: {jrn_name} ({jrn_lib})")
                        elif auto_status == "likely":
                            console.print(f"  • [green]Auto-Journal: Likely Enabled[/green]")
                            console.print(f"    {default_jrn.get('message', 'New tables likely inherit journaling')}")
                        elif auto_status == "unknown":
                            console.print(f"  • [yellow]Auto-Journal: Unknown[/yellow]")
                            console.print(f"    {default_jrn.get('message', 'Unable to determine auto-journal status')}")
                        else:
                            console.print(f"  • [red]Auto-Journal: Disabled[/red]")
                            console.print(f"    {default_jrn.get('message', 'New tables will NOT be auto-journaled')}")
                elif status == "disabled":
                    console.print(f"  • Status: [red]Disabled[/red]")
                    if "message" in journal_info:
                        console.print(f"  • {journal_info['message']}")
                else:
                    console.print(f"  • Status: [yellow]{status}[/yellow]")
                    if "message" in journal_info:
                        console.print(f"  • Message: {journal_info['message']}")
                
                console.print()
        
    except ConnectionError as e:
        console.print(f"[red]Connection error: {e.message}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


# Mockup commands - extracted to cli_commands/mockup_commands.py




def register_library_commands(cli_group):
    """Register library commands with the main CLI group."""
    cli_group.add_command(library)
