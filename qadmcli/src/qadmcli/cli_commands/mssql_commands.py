"""MSSQL Commands Module.

This module contains MSSQL-related CLI commands:
- mssql query: Execute SELECT queries on MSSQL
- mssql execute: Execute DDL/DML on MSSQL
- mssql user check: Check user permissions
- mssql user check-table: Check table permissions
- mssql user grant: Grant permissions
- mssql ct status: Check Change Tracking status
- mssql ct changes: Get CT changes
- mssql ct enable-db: Enable CT on database
- mssql ct disable-db: Disable CT on database
- mssql ct enable-table: Enable CT on table
- mssql ct disable-table: Disable CT on table
"""

import sys
import logging
from datetime import datetime
from typing import Optional

import click
from rich.console import Console

from ..config import load_config
from ..db.mssql import MSSQLConnection
from ..db.mssql_user import MSSQLUserManager
from ..db.mssql_ct import MSSQLChangeTracking
from ..utils.formatters import print_table, print_json_clean
from .utils import print_panel

console = Console()


@click.group()
def mssql():
    """MSSQL-specific commands."""
    pass


@mssql.command("query")
@click.option("--query", "-q", required=True, help="SQL SELECT query to execute")
@click.option("--limit", "-l", type=int, default=100, help="Maximum rows to return (default: 100)")
@click.option("--offset", "-o", type=int, default=0, help="Number of rows to skip (default: 0)")
@click.option("--format", "-f", "output_format", type=click.Choice(["table", "csv", "json"]), default="table", help="Output format")
@click.option("--user", "-u", default=None, help="Override username for connection")
@click.option("--password", "-p", default=None, help="Override password for connection")
@click.pass_context
def mssql_query(ctx: click.Context, query: str, limit: int, offset: int, output_format: str, user: str, password: str) -> None:
    """Execute a SELECT query on MSSQL database.
    
    This is a convenience alias for 'sql query --target mssql'.
    
    Examples:
        qadmcli mssql query -q "SELECT * FROM dbo.CUSTOMERS"
        qadmcli mssql query -q "SELECT * FROM dbo.CUSTOMERS" --limit 10
        qadmcli mssql query -q "SELECT * FROM dbo.CUSTOMERS" --format json
        qadmcli mssql query -q "SELECT * FROM dbo.CUSTOMERS" -u GLUESYNC01 -p password123
    """
    # Import sql_query from sql_commands
    from .sql_commands import sql_query
    
    # Delegate to sql_query with target=mssql
    ctx.invoke(sql_query, query=query, target="mssql", limit=limit, offset=offset, output_format=output_format, user=user, password=password)


@mssql.command("execute")
@click.option("--query", "-q", required=True, help="SQL query to execute (DDL/DML)")
@click.option("--user", "-u", default=None, help="Override username for connection")
@click.option("--password", "-p", default=None, help="Override password for connection")
@click.pass_context
def mssql_execute(ctx: click.Context, query: str, user: str, password: str) -> None:
    """Execute a SQL query on MSSQL database (DDL/DML).
    
    Use this for CREATE, ALTER, DROP, INSERT, UPDATE, DELETE operations.
    For SELECT queries, use 'mssql query' instead.
    
    Examples:
        qadmcli mssql execute -q "CREATE TABLE dbo.TEST (ID INT)"
        qadmcli mssql execute -q "INSERT INTO dbo.CUSTOMERS VALUES (1, 'John')"
        qadmcli mssql execute -q "UPDATE dbo.CUSTOMERS SET STATUS='ACTIVE'"
        qadmcli mssql execute -q "DROP TABLE dbo.TEST"
        qadmcli mssql execute -q "GRANT SELECT ON dbo.CUSTOMERS TO GLUESYNC01" -u sa -p password
    """
    # Import sql_execute from sql_commands
    from .sql_commands import sql_execute
    
    # Delegate to sql_execute with target=mssql
    ctx.invoke(sql_execute, query=query, target="mssql", user=user, password=password)


@mssql.group()
def user() -> None:
    """MSSQL user management commands."""
    pass


@user.command("check")
@click.option("--user", "-u", required=True, help="Username to check")
@click.option("--format", "-f", "output_format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def mssql_user_check(ctx: click.Context, user: str, output_format: str) -> None:
    """Check if user exists in MSSQL and get permissions.
    
    Shows server login, database user, roles, and explicit permissions.
    
    Examples:
        qadmcli mssql user check -u GLUESYNC01
        qadmcli mssql user check -u myuser
    """
    config_path = ctx.obj["config_path"]
    
    try:
        config = load_config(config_path)
        
        if not config.mssql:
            console.print("[red]Error: MSSQL configuration not found[/red]")
            sys.exit(1)
        
        mssql_conn = MSSQLConnection(config.mssql)
        mssql_conn.connect()
        
        try:
            user_mgr = MSSQLUserManager(mssql_conn)
            result = user_mgr.check_user(user)
            
            if output_format == "json":
                print_json_clean(result)
            else:
                print_panel(
                    ctx,
                    f"Checking user: {user}",
                    title="MSSQL User Check",
                    border_style="blue"
                )
                
                # Server Login Info
                if result["server_login_exists"]:
                    login_info = result["server_login_info"]
                    login_rows = [
                        ["Name", login_info["name"]],
                        ["Type", login_info["type"]],
                        ["Disabled", "Yes" if login_info["is_disabled"] else "No"],
                        ["Default Database", login_info["default_database"] or "N/A"],
                        ["Created", login_info["create_date"] or "N/A"]
                    ]
                    console.print(print_table(
                        console,
                        ["Property", "Value"],
                        login_rows,
                        title="Server Login"
                    ))
                    
                    # Server Roles
                    if result["server_roles"]:
                        roles_text = ", ".join(result["server_roles"])
                        console.print(f"[green]Server Roles: {roles_text}[/green]")
                    else:
                        console.print("[yellow]No server roles assigned[/yellow]")
                else:
                    console.print("[red]✗ Server login does not exist[/red]")
                
                # Login-to-User Mapping
                if result["mapped_database_user"]:
                    mapping = result["mapped_database_user"]
                    map_rows = [
                        ["Server Login", mapping["login_name"]],
                        ["Database User", mapping["database_user_name"]],
                        ["User Type", mapping["user_type"]],
                        ["Default Schema", mapping["default_schema"] or "N/A"]
                    ]
                    console.print(print_table(
                        console,
                        ["Property", "Value"],
                        map_rows,
                        title="Login-to-User Mapping"
                    ))
                elif result["server_login_exists"] and not result["database_user_exists"]:
                    console.print(f"[yellow]⚠ Login '{user}' is not mapped to any database user in current database[/yellow]")
                
                # Database User Info
                if result["database_user_exists"]:
                    db_info = result["database_user_info"]
                    db_rows = [
                        ["Name", db_info["name"]],
                        ["Type", db_info["type"]],
                        ["Default Schema", db_info["default_schema"] or "N/A"],
                        ["Created", db_info["create_date"] or "N/A"]
                    ]
                    console.print(print_table(
                        console,
                        ["Property", "Value"],
                        db_rows,
                        title="Database User"
                    ))
                    
                    # Database Roles
                    if result["database_roles"]:
                        roles_text = ", ".join(result["database_roles"])
                        console.print(f"[green]Database Roles: {roles_text}[/green]")
                    else:
                        console.print("[yellow]No database roles assigned[/yellow]")
                    
                    # Explicit Permissions
                    if result["explicit_permissions"]:
                        perm_rows = []
                        for perm in result["explicit_permissions"]:
                            perm_rows.append([
                                perm["permission"],
                                perm["state"],
                                f"{perm['schema_name']}.{perm['object_name']}" if perm["object_name"] else perm["class"],
                            ])
                        console.print(print_table(
                            console,
                            ["Permission", "State", "Object"],
                            perm_rows,
                            title="Explicit Permissions"
                        ))
                    else:
                        console.print("[yellow]No explicit permissions found[/yellow]")
                else:
                    console.print("[red]✗ Database user does not exist[/red]")
                
                # Summary
                if result["server_login_exists"] and result["database_user_exists"]:
                    console.print("\n[green]✓ User is fully configured (login + database user)[/green]")
                elif result["server_login_exists"]:
                    console.print("\n[yellow]⚠ Server login exists but database user is missing[/yellow]")
                    console.print("[dim]Run: CREATE USER [username] FROM LOGIN [username][/dim]")
                else:
                    console.print("\n[red]✗ User does not exist. Create login first:[/red]")
                    console.print(f"[dim]CREATE LOGIN [{user}] WITH PASSWORD = 'password'[/dim]".replace('[', '\\[').replace(']', '\\]'))
        
        finally:
            mssql_conn.disconnect()
    
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@user.command("check-table")
@click.option("--user", "-u", required=True, help="Username to check")
@click.option("--table", "-t", required=True, help="Table name to check")
@click.option("--schema", "-s", default="dbo", show_default=True, help="Schema name")
@click.option("--format", "-f", "output_format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def mssql_user_check_table(ctx: click.Context, user: str, table: str, schema: str, output_format: str) -> None:
    """Check user permissions for a specific table.
    
    Shows effective permissions, role permissions, and public permissions.
    
    Examples:
        qadmcli mssql user check-table -u GLUESYNC01 -t CUSTOMERS
        qadmcli mssql user check-table -u GLUESYNC01 -t CUSTOMERS -s dbo
    """
    config_path = ctx.obj["config_path"]
    
    try:
        config = load_config(config_path)
        
        if not config.mssql:
            console.print("[red]Error: MSSQL configuration not found[/red]")
            sys.exit(1)
        
        mssql_conn = MSSQLConnection(config.mssql)
        mssql_conn.connect()
        
        try:
            user_mgr = MSSQLUserManager(mssql_conn)
            result = user_mgr.check_table_permissions(user, table, schema)
            
            if output_format == "json":
                print_json_clean(result)
            else:
                print_panel(
                    ctx,
                    f"Checking permissions for {user} on {schema}.{table}",
                    title="MSSQL Table Permission Check",
                    border_style="blue"
                )
                
                # Table existence
                if result["table_exists"]:
                    console.print(f"[green]✓ Table {schema}.{table} exists[/green]")
                else:
                    console.print(f"[red]✗ Table {schema}.{table} does not exist[/red]")
                    return
                
                # Server login status
                if result["server_login_exists"]:
                    console.print(f"[green]✓ Server login: {user}[/green]")
                else:
                    console.print(f"[red]✗ Server login: {user} does not exist[/red]")
                    return
                
                # Show login-to-user mapping
                if result["mapped_database_user"]:
                    mapping = result["mapped_database_user"]
                    console.print(f"[green]✓ Mapped to database user: {mapping['database_user_name']} (type: {mapping['user_type']})[/green]")
                    effective_user = mapping["database_user_name"]
                elif result["database_user_exists"]:
                    console.print(f"[green]✓ Database user: {user} (explicit)[/green]")
                    effective_user = user
                else:
                    console.print(f"[yellow]⚠ No database user mapping found[/yellow]")
                    console.print(f"[dim]Login '{user}' is not mapped to any user in this database[/dim]")
                    effective_user = user
                
                # Special roles
                if result["is_sysadmin"]:
                    console.print(f"[green]✓ Server role: sysadmin (full access to all databases)[/green]")
                
                if result["is_db_owner"]:
                    console.print(f"[green]✓ Database role: db_owner (full access to this database)[/green]")
                
                if result["has_db_datareader"]:
                    console.print(f"[green]✓ Database role: db_datareader (can SELECT from all tables)[/green]")
                
                if result["has_db_datawriter"]:
                    console.print(f"[green]✓ Database role: db_datawriter (can INSERT/UPDATE/DELETE all tables)[/green]")
                
                if result["has_db_ddladmin"]:
                    console.print(f"[green]✓ Database role: db_ddladmin (can modify schema)[/green]")
                
                if result["has_db_securityadmin"]:
                    console.print(f"[green]✓ Database role: db_securityadmin (can manage permissions)[/green]")
                
                if result["has_db_backupoperator"]:
                    console.print(f"[green]✓ Database role: db_backupoperator (can backup database)[/green]")
                
                # Show all database roles
                if result["database_roles"]:
                    roles_text = ", ".join(result["database_roles"])
                    console.print(f"\n[dim]All database roles: {roles_text}[/dim]")
                
                # Effective permissions
                if result["effective_permissions"]:
                    eff_rows = []
                    for perm in result["effective_permissions"]:
                        eff_rows.append([perm["permission"], perm["state"]])
                    console.print(print_table(
                        console,
                        ["Permission", "State"],
                        eff_rows,
                        title=f"Effective Permissions (as {effective_user})"
                    ))
                else:
                    if not result["database_user_exists"] and not result["mapped_database_user"]:
                        console.print(f"[yellow]⚠ Cannot check effective permissions (login '{user}' has no database user mapping)[/yellow]")
                        console.print("[dim]User may still have access through guest account or other mechanisms[/dim]")
                    else:
                        console.print(f"[yellow]No effective permissions on this table (checked as {effective_user})[/yellow]")
                
                # Explicit permissions
                if result["role_permissions"]:
                    role_rows = []
                    for perm in result["role_permissions"]:
                        role_rows.append([perm["permission"], perm["state"], perm["grantee"]])
                    console.print(print_table(
                        console,
                        ["Permission", "State", "Grantee"],
                        role_rows,
                        title=f"Explicit Permissions (for {effective_user})"
                    ))
                
                # Public permissions
                if result["public_permissions"]:
                    pub_rows = []
                    for perm in result["public_permissions"]:
                        pub_rows.append([perm["permission"], perm["state"]])
                    console.print(print_table(
                        console,
                        ["Permission", "State"],
                        pub_rows,
                        title="Public Permissions"
                    ))
                
                # Summary
                has_select = any(p["permission"] == "SELECT" for p in result["effective_permissions"])
                has_full_access = (result["is_sysadmin"] or 
                                 result["is_db_owner"] or 
                                 result["has_db_datareader"])
                
                if has_select or has_full_access:
                    console.print("\n[green]✓ User can SELECT from this table[/green]")
                    if has_full_access:
                        reasons = []
                        if result["is_sysadmin"]:
                            reasons.append("sysadmin")
                        if result["is_db_owner"]:
                            reasons.append("db_owner")
                        if result["has_db_datareader"]:
                            reasons.append("db_datareader")
                        console.print(f"[dim](Access via role: {', '.join(reasons)})[/dim]")
                else:
                    console.print("\n[red]✗ User cannot SELECT from this table[/red]")
        
        finally:
            mssql_conn.disconnect()
    
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@user.command("grant")
@click.option("--user", "-u", required=True, help="Username to grant permission to")
@click.option("--permission", "-p", required=True, help="Permission to grant (e.g., SELECT, INSERT, UPDATE, DELETE, ALL)")
@click.option("--table", "-t", required=True, help="Table name")
@click.option("--schema", "-s", default="dbo", show_default=True, help="Schema name")
@click.pass_context
def mssql_user_grant(ctx: click.Context, user: str, permission: str, table: str, schema: str) -> None:
    """Grant permission to user on a table.
    
    Automatically creates database user from login if it doesn't exist.
    
    Examples:
        qadmcli mssql user grant -u GLUESYNC01 -p SELECT -t CUSTOMERS
        qadmcli mssql user grant -u GLUESYNC01 -p SELECT,INSERT,UPDATE -t CUSTOMERS -s dbo
        qadmcli mssql user grant -u GLUESYNC01 -p ALL -t ORDERS
    """
    config_path = ctx.obj["config_path"]
    
    try:
        config = load_config(config_path)
        
        if not config.mssql:
            console.print("[red]Error: MSSQL configuration not found[/red]")
            sys.exit(1)
        
        mssql_conn = MSSQLConnection(config.mssql)
        mssql_conn.connect()
        
        try:
            user_mgr = MSSQLUserManager(mssql_conn)
            
            # Handle multiple permissions (comma-separated)
            permissions = [p.strip() for p in permission.split(",")]
            
            results = []
            for perm in permissions:
                result = user_mgr.grant_permission(user, perm, table, "TABLE", schema)
                results.append(result)
                
                if result["success"]:
                    console.print(f"[green]✓ Granted {perm} on {schema}.{table} to {user}[/green]")
                    console.print(f"[dim]SQL: {result['sql_executed']}[/dim]")
                else:
                    console.print(f"[red]✗ Failed to grant {perm}: {result['error']}[/red]")
            
            success_count = sum(1 for r in results if r["success"])
            console.print(f"\n{success_count}/{len(results)} permission(s) granted successfully")
        
        finally:
            mssql_conn.disconnect()
    
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@mssql.group()
def ct() -> None:
    """MSSQL Change Tracking commands."""
    pass


@ct.command("status")
@click.option("--table", "-t", required=True, help="Table name (e.g., CUSTOMERS)")
@click.option("--schema", "-s", default="dbo", show_default=True, help="Schema name")
@click.option("--format", "-f", "output_format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def mssql_ct_status(ctx: click.Context, table: str, schema: str, output_format: str) -> None:
    """Check if Change Tracking is enabled on database and table.
    
    Examples:
        qadmcli mssql ct status -t CUSTOMERS
        qadmcli mssql ct status -t CUSTOMERS -s dbo
        qadmcli mssql ct status -t CUSTOMERS -s dbo --format json
    """
    config_path = ctx.obj["config_path"]
    
    # Suppress logging for JSON output
    if output_format == "json":
        logging.getLogger("qadmcli").setLevel(logging.WARNING)
    
    try:
        config = load_config(config_path)
        
        if not config.mssql:
            console.print("[red]Error: MSSQL configuration not found in connection.yaml[/red]")
            sys.exit(1)
        
        with MSSQLConnection(config.mssql) as conn:
            ct_mgr = MSSQLChangeTracking(conn)
            status = ct_mgr.get_table_ct_status(table, schema)
            
            if output_format == "json":
                # JSON output for scripting
                print_json_clean({
                    "table": f"{schema}.{table}",
                    "database": status.database_name,
                    "ct_enabled_on_database": status.is_enabled_on_database,
                    "ct_enabled_on_table": status.is_enabled_on_table,
                    "retention_period_days": status.retention_period_days,
                    "auto_cleanup": status.auto_cleanup
                })
            else:
                # Human-readable output
                console.print(f"[bold]Change Tracking Status for {schema}.{table}[/bold]")
                console.print(f"  Database: {status.database_name}")
                console.print(f"  CT Enabled on Database: {'[green]Yes[/green]' if status.is_enabled_on_database else '[red]No[/red]'}")
                
                if status.is_enabled_on_database:
                    console.print(f"  CT Enabled on Table: {'[green]Yes[/green]' if status.is_enabled_on_table else '[red]No[/red]'}")
                    console.print(f"  Retention Period: {status.retention_period_days} days" if status.retention_period_days else "  Retention Period: N/A")
                    console.print(f"  Auto Cleanup: {'Yes' if status.auto_cleanup else 'No'}" if status.auto_cleanup is not None else "  Auto Cleanup: N/A")
                
                if not status.is_enabled_on_database:
                    console.print("\n[yellow]To enable CT on database:[/yellow]")
                    console.print(f"  ALTER DATABASE [{status.database_name}] SET CHANGE_TRACKING = ON")
                    console.print("  (CHANGE_RETENTION = 2 DAYS, AUTO_CLEANUP = ON)")
                elif not status.is_enabled_on_table:
                    console.print("\n[yellow]To enable CT on table:[/yellow]")
                    console.print(f"  ALTER TABLE [{schema}].[{table}] ENABLE CHANGE_TRACKING")
    
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@ct.command("changes")
@click.option("--table", "-t", required=True, help="Table name (e.g., CUSTOMERS)")
@click.option("--schema", "-s", default="dbo", show_default=True, help="Schema name")
@click.option("--since", help="Get changes since timestamp (YYYY-MM-DD HH:MM:SS)")
@click.option("--since-version", type=int, help="Get changes since specific version")
@click.option("--limit", "-l", type=int, default=1000, help="Maximum changes to return (default: 1000)")
@click.option("--format", "-f", "output_format", type=click.Choice(["table", "json", "summary"]), default="table", help="Output format")
@click.pass_context
def mssql_ct_changes(
    ctx: click.Context,
    table: str,
    schema: str,
    since: Optional[str],
    since_version: Optional[int],
    limit: int,
    output_format: str
) -> None:
    """Get Change Tracking changes for a table.
    
    Returns:
        SYS_CHANGE_VERSION, SYS_CHANGE_OPERATION (I/U/D), Primary Key values,
        SYS_CHANGE_CONTEXT (if available)
    
    Use --format summary for operation counts only (useful for comparison with AS400 journal).
    
    Examples:
        qadmcli mssql ct changes -t CUSTOMERS --since "2025-04-09 10:00:00"
        qadmcli mssql ct changes -t CUSTOMERS --since-version 12345
        qadmcli mssql ct changes -t CUSTOMERS --since "2025-04-09" --format summary
        qadmcli mssql ct changes -t CUSTOMERS --format json
    """
    config_path = ctx.obj["config_path"]
    
    # Suppress logging for JSON/summary output
    if output_format in ("json", "summary"):
        logging.getLogger("qadmcli").setLevel(logging.WARNING)
    
    try:
        config = load_config(config_path)
        
        if not config.mssql:
            console.print("[red]Error: MSSQL configuration not found in connection.yaml[/red]")
            sys.exit(1)
        
        # Parse timestamp if provided
        since_timestamp = None
        if since:
            try:
                since_timestamp = datetime.strptime(since, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                try:
                    since_timestamp = datetime.strptime(since, "%Y-%m-%d")
                except ValueError:
                    console.print("[red]Error: Invalid timestamp format. Use YYYY-MM-DD HH:MM:SS or YYYY-MM-DD[/red]")
                    sys.exit(1)
        
        with MSSQLConnection(config.mssql) as conn:
            ct_mgr = MSSQLChangeTracking(conn)
            
            # Check CT status first
            status = ct_mgr.get_table_ct_status(table, schema)
            if not status.is_enabled_on_database:
                console.print("[red]Error: Change Tracking is not enabled on the database[/red]")
                sys.exit(1)
            if not status.is_enabled_on_table:
                console.print(f"[red]Error: Change Tracking is not enabled on table {schema}.{table}[/red]")
                sys.exit(1)
            
            # Get current and min versions
            current_version = ct_mgr.get_current_version()
            min_version = ct_mgr.get_min_valid_version(table, schema)
            
            console.print(f"[dim]Current CT Version: {current_version}, Min Valid Version: {min_version}[/dim]")
            
            # Get changes
            changes = ct_mgr.get_changes(
                table_name=table,
                schema=schema,
                since_version=since_version,
                since_timestamp=since_timestamp
            )
            
            # Limit results
            if len(changes) > limit:
                changes = changes[:limit]
                console.print(f"[yellow]Warning: Limited to {limit} changes (total available: {len(changes)})[/yellow]")
            
            if not changes:
                if output_format == "summary":
                    # Return empty summary
                    summary = {
                        "table": f"{schema}.{table}",
                        "since": since,
                        "since_version": since_version,
                        "current_version": current_version,
                        "total": 0,
                        "inserts": 0,
                        "updates": 0,
                        "deletes": 0,
                        "changes": []
                    }
                    print_json_clean(summary)
                else:
                    console.print("[yellow]No changes found[/yellow]")
                return
            
            # Format and display
            if output_format == "summary":
                # Summary only - for comparison with journal
                op_counts = {"I": 0, "U": 0, "D": 0}
                for change in changes:
                    op = change.sys_change_operation
                    if op in op_counts:
                        op_counts[op] += 1
                
                summary = {
                    "table": f"{schema}.{table}",
                    "since": since,
                    "since_version": since_version,
                    "current_version": current_version,
                    "total": len(changes),
                    "inserts": op_counts["I"],
                    "updates": op_counts["U"],
                    "deletes": op_counts["D"],
                    "changes": [
                        {
                            "version": c.sys_change_version,
                            "operation": c.sys_change_operation,
                            "pk": c.primary_key_values
                        }
                        for c in changes
                    ]
                }
                print_json_clean(summary)
            elif output_format == "json":
                results = []
                for change in changes:
                    result = {
                        "SYS_CHANGE_VERSION": change.sys_change_version,
                        "SYS_CHANGE_OPERATION": change.sys_change_operation,
                        "SYS_CHANGE_COLUMNS": change.sys_change_columns,
                        "SYS_CHANGE_CONTEXT": change.sys_change_context,
                        "PRIMARY_KEY_VALUES": change.primary_key_values
                    }
                    results.append(result)
                print_json_clean(results)
            else:
                # Table output
                formatted = ct_mgr.format_changes_table(changes)
                if formatted:
                    columns = list(formatted[0].keys())
                    rows = [[str(row.get(col, "")) for col in columns] for row in formatted]
                    
                    console.print(print_table(
                        console,
                        columns,
                        rows,
                        title=f"Change Tracking Changes for {schema}.{table} ({len(changes)} rows)"
                    ))
                
                # Summary
                op_counts = {}
                for change in changes:
                    op = change.sys_change_operation
                    op_counts[op] = op_counts.get(op, 0) + 1
                
                summary = ", ".join(f"{op}={count}" for op, count in op_counts.items())
                console.print(f"[green]Operations: {summary}[/green]")
    
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@ct.command("enable-db")
@click.option("--retention", "-r", type=int, default=2, show_default=True, help="Retention period in days")
@click.option("--auto-cleanup/--no-auto-cleanup", default=True, show_default=True, help="Enable auto cleanup")
@click.option("--admin-user", "-U", help="SQL Server admin user with ALTER DATABASE permission")
@click.option("--admin-password", "-P", help="Password for admin user")
@click.pass_context
def mssql_ct_enable_db(
    ctx: click.Context,
    retention: int,
    auto_cleanup: bool,
    admin_user: Optional[str],
    admin_password: Optional[str]
) -> None:
    """Enable Change Tracking on the database.
    
    Requires ALTER DATABASE permission (sysadmin or db_owner).
    
    Examples:
        qadmcli mssql ct enable-db
        qadmcli mssql ct enable-db -r 7 --no-auto-cleanup
        qadmcli mssql ct enable-db -U sa -P <password>
    """
    config_path = ctx.obj["config_path"]
    
    try:
        config = load_config(config_path)
        
        if not config.mssql:
            console.print("[red]Error: MSSQL configuration not found in connection.yaml[/red]")
            sys.exit(1)
        
        # Use admin credentials if provided
        from ..models.connection import MSSQLConnection as MSSQLConnectionModel
        mssql_config = config.mssql
        if admin_user:
            mssql_config = MSSQLConnectionModel(
                host=config.mssql.host,
                port=config.mssql.port,
                username=admin_user,
                password=admin_password or "",
                database=config.mssql.database
            )
        
        with MSSQLConnection(mssql_config) as conn:
            ct_mgr = MSSQLChangeTracking(conn)
            
            # Check current status
            status = ct_mgr.get_database_ct_status()
            if status["is_enabled"]:
                console.print(f"[yellow]Change Tracking is already enabled on database '{status['database_name']}'[/yellow]")
                console.print(f"  Retention Period: {status['retention_period']} {status['retention_period_units']}")
                console.print(f"  Auto Cleanup: {'Yes' if status['auto_cleanup'] else 'No'}")
                return
            
            # Enable CT
            console.print(f"[cyan]Enabling Change Tracking on database '{status['database_name']}'...[/cyan]")
            console.print(f"  Retention: {retention} days")
            console.print(f"  Auto Cleanup: {'Yes' if auto_cleanup else 'No'}")
            
            try:
                ct_mgr.enable_database_ct(retention_days=retention, auto_cleanup=auto_cleanup)
                console.print(f"[green]Change Tracking enabled successfully![/green]")
            except Exception as e:
                error_msg = str(e)
                if "permission" in error_msg.lower() or "denied" in error_msg.lower():
                    console.print("[red]Error: Insufficient permissions to enable Change Tracking[/red]")
                    console.print("[dim]This operation requires ALTER DATABASE permission (sysadmin or db_owner role)[/dim]")
                    if not admin_user:
                        console.print("[dim]Tip: Use -U and -P to provide admin credentials[/dim]")
                raise
    
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@ct.command("disable-db")
@click.confirmation_option(prompt="Are you sure you want to disable Change Tracking on the database?")
@click.option("--admin-user", "-U", help="SQL Server admin user with ALTER DATABASE permission")
@click.option("--admin-password", "-P", help="Password for admin user")
@click.pass_context
def mssql_ct_disable_db(
    ctx: click.Context,
    admin_user: Optional[str],
    admin_password: Optional[str]
) -> None:
    """Disable Change Tracking on the database.
    
    WARNING: This will remove all CT history. Requires ALTER DATABASE permission.
    
    Examples:
        qadmcli mssql ct disable-db
        qadmcli mssql ct disable-db -U sa -P <password>
    """
    config_path = ctx.obj["config_path"]
    
    try:
        config = load_config(config_path)
        
        if not config.mssql:
            console.print("[red]Error: MSSQL configuration not found in connection.yaml[/red]")
            sys.exit(1)
        
        # Use admin credentials if provided
        from ..models.connection import MSSQLConnection as MSSQLConnectionModel
        mssql_config = config.mssql
        if admin_user:
            mssql_config = MSSQLConnectionModel(
                host=config.mssql.host,
                port=config.mssql.port,
                username=admin_user,
                password=admin_password or "",
                database=config.mssql.database
            )
        
        with MSSQLConnection(mssql_config) as conn:
            ct_mgr = MSSQLChangeTracking(conn)
            
            # Check current status
            status = ct_mgr.get_database_ct_status()
            if not status["is_enabled"]:
                console.print(f"[yellow]Change Tracking is already disabled on database '{status['database_name']}'[/yellow]")
                return
            
            # Disable CT
            console.print(f"[cyan]Disabling Change Tracking on database '{status['database_name']}'...[/cyan]")
            
            try:
                ct_mgr.disable_database_ct()
                console.print(f"[green]Change Tracking disabled successfully![/green]")
            except Exception as e:
                error_msg = str(e)
                if "permission" in error_msg.lower() or "denied" in error_msg.lower():
                    console.print("[red]Error: Insufficient permissions to disable Change Tracking[/red]")
                    console.print("[dim]This operation requires ALTER DATABASE permission (sysadmin or db_owner role)[/dim]")
                    if not admin_user:
                        console.print("[dim]Tip: Use -U and -P to provide admin credentials[/dim]")
                raise
    
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@ct.command("enable-table")
@click.option("--table", "-t", required=True, help="Table name (e.g., CUSTOMERS)")
@click.option("--schema", "-s", default="dbo", show_default=True, help="Schema name")
@click.option("--track-columns/--no-track-columns", default=True, show_default=True, help="Track column changes")
@click.option("--admin-user", "-U", help="SQL Server admin user with ALTER permission on the table")
@click.option("--admin-password", "-P", help="Password for admin user")
@click.pass_context
def mssql_ct_enable_table(
    ctx: click.Context,
    table: str,
    schema: str,
    track_columns: bool,
    admin_user: Optional[str],
    admin_password: Optional[str]
) -> None:
    """Enable Change Tracking on a table.
    
    Requires ALTER permission on the table and table must have a primary key.
    
    Examples:
        qadmcli mssql ct enable-table -t CUSTOMERS
        qadmcli mssql ct enable-table -t CUSTOMERS -s dbo --no-track-columns
        qadmcli mssql ct enable-table -t CUSTOMERS -U admin -P <password>
    """
    config_path = ctx.obj["config_path"]
    
    try:
        config = load_config(config_path)
        
        if not config.mssql:
            console.print("[red]Error: MSSQL configuration not found in connection.yaml[/red]")
            sys.exit(1)
        
        # Use admin credentials if provided
        from ..models.connection import MSSQLConnection as MSSQLConnectionModel
        mssql_config = config.mssql
        if admin_user:
            mssql_config = MSSQLConnectionModel(
                host=config.mssql.host,
                port=config.mssql.port,
                username=admin_user,
                password=admin_password or "",
                database=config.mssql.database
            )
        
        with MSSQLConnection(mssql_config) as conn:
            ct_mgr = MSSQLChangeTracking(conn)
            
            # Check database CT status first
            db_status = ct_mgr.get_database_ct_status()
            if not db_status["is_enabled"]:
                console.print(f"[red]Error: Change Tracking is not enabled on the database[/red]")
                console.print(f"[dim]Run 'qadmcli mssql ct enable-db' first[/dim]")
                sys.exit(1)
            
            # Check current table status
            status = ct_mgr.get_table_ct_status(table, schema)
            if status.is_enabled_on_table:
                console.print(f"[yellow]Change Tracking is already enabled on table '{schema}.{table}'[/yellow]")
                return
            
            # Enable CT on table
            console.print(f"[cyan]Enabling Change Tracking on table '{schema}.{table}'...[/cyan]")
            console.print(f"  Track Columns: {'Yes' if track_columns else 'No'}")
            
            try:
                ct_mgr.enable_table_ct(table, schema, track_columns_updated=track_columns)
                console.print(f"[green]Change Tracking enabled successfully on '{schema}.{table}'![/green]")
            except Exception as e:
                error_msg = str(e)
                if "primary key" in error_msg.lower():
                    console.print("[red]Error: Table does not have a primary key[/red]")
                    console.print("[dim]Change Tracking requires the table to have a primary key[/dim]")
                elif "permission" in error_msg.lower() or "denied" in error_msg.lower():
                    console.print("[red]Error: Insufficient permissions to enable Change Tracking on table[/red]")
                    console.print("[dim]This operation requires ALTER permission on the table[/dim]")
                    if not admin_user:
                        console.print("[dim]Tip: Use -U and -P to provide admin credentials[/dim]")
                raise
    
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@ct.command("disable-table")
@click.option("--table", "-t", required=True, help="Table name (e.g., CUSTOMERS)")
@click.option("--schema", "-s", default="dbo", show_default=True, help="Schema name")
@click.confirmation_option(prompt="Are you sure you want to disable Change Tracking on this table?")
@click.option("--admin-user", "-U", help="SQL Server admin user with ALTER permission on the table")
@click.option("--admin-password", "-P", help="Password for admin user")
@click.pass_context
def mssql_ct_disable_table(
    ctx: click.Context,
    table: str,
    schema: str,
    admin_user: Optional[str],
    admin_password: Optional[str]
) -> None:
    """Disable Change Tracking on a table.
    
    Requires ALTER permission on the table.
    
    Examples:
        qadmcli mssql ct disable-table -t CUSTOMERS
        qadmcli mssql ct disable-table -t CUSTOMERS -U admin -P <password>
    """
    config_path = ctx.obj["config_path"]
    
    try:
        config = load_config(config_path)
        
        if not config.mssql:
            console.print("[red]Error: MSSQL configuration not found in connection.yaml[/red]")
            sys.exit(1)
        
        # Use admin credentials if provided
        from ..models.connection import MSSQLConnection as MSSQLConnectionModel
        mssql_config = config.mssql
        if admin_user:
            mssql_config = MSSQLConnectionModel(
                host=config.mssql.host,
                port=config.mssql.port,
                username=admin_user,
                password=admin_password or "",
                database=config.mssql.database
            )
        
        with MSSQLConnection(mssql_config) as conn:
            ct_mgr = MSSQLChangeTracking(conn)
            
            # Check current table status
            status = ct_mgr.get_table_ct_status(table, schema)
            if not status.is_enabled_on_table:
                console.print(f"[yellow]Change Tracking is already disabled on table '{schema}.{table}'[/yellow]")
                return
            
            # Disable CT on table
            console.print(f"[cyan]Disabling Change Tracking on table '{schema}.{table}'...[/cyan]")
            
            try:
                ct_mgr.disable_table_ct(table, schema)
                console.print(f"[green]Change Tracking disabled successfully on '{schema}.{table}'![/green]")
            except Exception as e:
                error_msg = str(e)
                if "permission" in error_msg.lower() or "denied" in error_msg.lower():
                    console.print("[red]Error: Insufficient permissions to disable Change Tracking on table[/red]")
                    console.print("[dim]This operation requires ALTER permission on the table[/dim]")
                    if not admin_user:
                        console.print("[dim]Tip: Use -U and -P to provide admin credentials[/dim]")
                raise
    
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


def register_mssql_commands(cli_group):
    """Register MSSQL commands with the main CLI group."""
    cli_group.add_command(mssql)
