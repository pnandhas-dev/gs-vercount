"""SQL Commands Module.

This module contains SQL execution commands:
- sql execute: Execute SQL statement (DDL/DML)
- sql query: Execute SQL query with results
"""

import sys
import os
import logging
from typing import Optional

import click
from rich.console import Console
from rich.text import Text

from ..config import load_config
from ..db.connection import AS400ConnectionManager, ConnectionError
from ..db.mssql import MSSQLConnection
from ..utils.formatters import print_table, print_json_clean
from .utils import print_panel

console = Console()


@click.group()
def sql():
    """SQL execution commands."""
    pass


@sql.command("execute")
@click.option("--query", "-q", required=True, help="SQL query to execute")
@click.option("-t", "--target", type=click.Choice(["as400", "mssql"]), default="as400", help="Target database (default: as400)")
@click.option("--format", "-f", "output_format", type=click.Choice(["table", "json"]), default="table", help="Output format (default: table)")
@click.option("--user", "-u", default=None, help="Override username for connection")
@click.option("--password", "-p", default=None, help="Override password for connection")
@click.pass_context
def sql_execute(ctx: click.Context, query: str, target: str, output_format: str, user: str, password: str) -> None:
    """Execute a SQL query and display results.
    
    Examples:
        qadmcli sql execute -q "CREATE TABLE ..."              # AS400 (default)
        qadmcli sql execute -q "CREATE TABLE ..." -t mssql     # MSSQL
        qadmcli sql execute -q "DROP TABLE ..." --target mssql # MSSQL
    """
    config_path = ctx.obj["config_path"]
    
    try:
        # Warn about trailing semicolon for AS400 (DB2 for i doesn't accept it in JDBC)
        if target == "as400" and query.rstrip().endswith(';'):
            console.print("[yellow]Warning: Trailing semicolon detected. DB2 for i JDBC driver may reject it. Consider removing the ';'.[/yellow]")
        
        if target == "mssql":
            config = load_config(config_path)
            # Execute on MSSQL
            if not config.mssql:
                console.print("[red]Error: MSSQL configuration not found[/red]")
                sys.exit(1)
            
            # Apply credential overrides if provided
            mssql_config = config.mssql
            if user or password:
                mssql_config = config.mssql.copy_with_overrides(username=user, password=password)
                if output_format != "json":  # Suppress in JSON mode
                    console.print(f"[yellow]Using credential override: user={user or '***'}[/yellow]")
            
            if output_format != "json":  # Suppress in JSON mode
                console.print(f"[dim]Executing on MSSQL: {query[:80]}...[/dim]")
            
            with MSSQLConnection(mssql_config) as conn:
                with conn.get_cursor() as cursor:
                    cursor.execute(query)
                    
                    # Check if query returns results (SELECT)
                    if query.strip().upper().startswith("SELECT"):
                        rows = cursor.fetchall()
                        columns = [desc[0] for desc in cursor.description] if cursor.description else []
                        
                        if output_format == "json":
                            import json
                            results = []
                            for row in rows:
                                row_dict = {}
                                for i, col in enumerate(columns):
                                    row_dict[str(col)] = row[i]
                                results.append(row_dict)
                            console.print(json.dumps(results, indent=2, default=str))
                        else:
                            console.print(f"[green]✓ Query executed successfully ({len(rows)} rows)[/green]")
                            if rows:
                                console.print(f"[dim]First 10 rows:[/dim]")
                                for row in rows[:10]:
                                    console.print(f"  {row}")
                    else:
                        # DDL/DML query (CREATE, INSERT, UPDATE, DELETE)
                        row_count = cursor.rowcount
                        if output_format == "json":
                            import json
                            console.print(json.dumps({"status": "success", "rows_affected": row_count}))
                        else:
                            console.print(f"[green]✓ Query executed successfully ({row_count} rows affected)[/green]")
        else:
            # Execute on AS400 (default)
            # Check if agent is available (no JVM needed in CLI)
            agent_url = os.environ.get("QADMCLI_AGENT_URL")
            if agent_url:
                from ..db.agent_client import AS400AgentClient
                client = AS400AgentClient(agent_url)
                if client.is_available():
                    result = client.execute(query)
                    
                    if result.get("columns"):
                        # SELECT query
                        columns = result["columns"]
                        rows = result["rows"]
                        if output_format == "json":
                            from ..utils.formatters import print_json_clean
                            results_list = []
                            for row in rows:
                                row_dict = {}
                                for i, col in enumerate(columns):
                                    row_dict[str(col)] = row[i] if i < len(row) else None
                                results_list.append(row_dict)
                            print_json_clean(results_list)
                        else:
                            if rows:
                                table_rows = [[str(cell) if cell is not None else "NULL" for cell in row] for row in rows]
                                console.print(print_table(console, columns, table_rows, title="Query Results"))
                                console.print(f"[green]{len(rows)} row(s) returned[/green]")
                            else:
                                console.print("[yellow]No rows returned[/yellow]")
                    else:
                        # DDL/DML query
                        rows_affected = result.get("rows_affected", 0)
                        if output_format == "json":
                            import json
                            console.print(json.dumps({"status": "success", "rows_affected": rows_affected}))
                        else:
                            console.print(f"[green]✓ Query executed successfully ({rows_affected} rows affected)[/green]")
                    return
            
            # Fallback to direct JT400 connection
            config = load_config(config_path)
            
            # Apply credential overrides if provided
            as400_config = config.as400
            if user or password:
                as400_config = config.as400.copy_with_overrides(user=user, password=password)
                if output_format != "json":  # Suppress in JSON mode
                    console.print(f"[yellow]Using credential override: user={user or '***'}[/yellow]")
            
            # Create temporary config with overridden AS400 settings
            from copy import deepcopy
            temp_config = deepcopy(config)
            temp_config.as400 = as400_config
            
            if output_format != "json":  # Suppress in JSON mode
                console.print(f"[dim]Executing on AS400: {query[:80]}...[/dim]")
            
            with AS400ConnectionManager(temp_config) as conn:
                cursor = conn.execute(query)
                
                # Check if query returns results (SELECT)
                if query.strip().upper().startswith("SELECT"):
                    # Get column names
                    columns = [desc[0] for desc in cursor.description] if cursor.description else []
                    
                    # Fetch all rows
                    rows = cursor.fetchall()
                    cursor.close()
                    
                    if output_format == "json":
                        # Clean JSON output for scripts (no Rich formatting)
                        from ..utils.formatters import print_json_clean
                        results = []
                        for row in rows:
                            row_dict = {}
                            for i, col in enumerate(columns):
                                row_dict[str(col)] = row[i]
                            results.append(row_dict)
                        print_json_clean(results)
                    else:
                        # Format as table
                        if rows:
                            table_rows = []
                            for row in rows:
                                table_rows.append([str(cell) if cell is not None else "NULL" for cell in row])
                            
                            # Sanitize column names for Windows terminal compatibility
                            def sanitize_column(name: str) -> str:
                                """Sanitize column name for Windows terminal display."""
                                sanitized = str(name)
                                replacements = {
                                    '\u2026': '...',
                                    '\u2018': "'",
                                    '\u2019': "'",
                                    '\u201C': '"',
                                    '\u201D': '"',
                                    '\u2013': '-',
                                    '\u2014': '--',
                                }
                                for unicode_char, ascii_char in replacements.items():
                                    sanitized = sanitized.replace(unicode_char, ascii_char)
                                if len(sanitized) > 30:
                                    sanitized = sanitized[:27] + '...'
                                return sanitized
                            
                            str_columns = [sanitize_column(str(col)) for col in columns]
                            console.print(print_table(
                                console,
                                str_columns,
                                table_rows,
                                title="Query Results"
                            ))
                            console.print(f"[green]{len(rows)} row(s) returned[/green]")
                        else:
                            console.print("[yellow]No rows returned[/yellow]")
                else:
                    # DDL/DML query (CREATE, ALTER, INSERT, UPDATE, DELETE)
                    row_count = cursor.rowcount if cursor.rowcount >= 0 else 0
                    cursor.close()
                    
                    if output_format == "json":
                        import json
                        console.print(json.dumps({"status": "success", "rows_affected": row_count}))
                    else:
                        console.print(f"[green]✓ Query executed successfully ({row_count} rows affected)[/green]")
    
    except ConnectionError as e:
        console.print(f"[red]Connection error: {e.message}[/red]")
        sys.exit(1)
    except Exception as e:
        # Enhanced error reporting - show exception type and details
        error_msg = str(e) if str(e) else "(empty error message)"
        error_type = type(e).__name__
        console.print(f"[red]Error [{error_type}]: {error_msg}[/red]")
        
        # Show traceback in verbose mode (for debugging)
        if os.environ.get('QADMCLI_DEBUG') == '1':
            import traceback
            console.print(f"[dim]Traceback:[/dim]")
            console.print(f"[dim]{traceback.format_exc()}[/dim]")
        
        sys.exit(1)


@sql.command("query")
@click.option("--query", "-q", required=True, help="SQL SELECT query to execute")
@click.option("--target", "-t", type=click.Choice(["as400", "mssql"]), default="as400", help="Target database (default: as400)")
@click.option("--limit", "-l", type=int, default=100, help="Maximum rows to return (default: 100)")
@click.option("--offset", "-o", type=int, default=0, help="Number of rows to skip (default: 0)")
@click.option("--format", "-f", "output_format", type=click.Choice(["table", "csv", "json"]), default="table", help="Output format")
@click.option("--user", "-u", default=None, help="Override username for connection")
@click.option("--password", "-p", default=None, help="Override password for connection")
@click.pass_context
def sql_query(ctx: click.Context, query: str, target: str, limit: int, offset: int, output_format: str, user: str, password: str) -> None:
    """Execute a SELECT query with formatted output and pagination.
    
    Examples:
        qadmcli sql query -q "SELECT * FROM GSLIBTST.CUSTOMERS"
        qadmcli sql query -q "SELECT * FROM dbo.CUSTOMERS" --target mssql
        qadmcli sql query -q "SELECT * FROM GSLIBTST.CUSTOMERS" --limit 10 --offset 20
        qadmcli sql query -q "SELECT * FROM GSLIBTST.CUSTOMERS" --format csv
        qadmcli sql query -q "SELECT CUST_ID, FIRST_NAME, EMAIL FROM GSLIBTST.CUSTOMERS WHERE STATUS = 'ACTIVE'"
    """
    config_path = ctx.obj["config_path"]
    border_style = ctx.obj.get("border_style", "unicode")
    
    try:
        # Validate query is a SELECT
        query_stripped = query.strip().upper()
        if not query_stripped.startswith("SELECT"):
            console.print("[red]Error: Only SELECT queries are allowed. Use 'sql execute' for other SQL commands.[/red]")
            sys.exit(1)
        
        # Warn about trailing semicolon (DB2 for i doesn't accept it in JDBC)
        if target == "as400" and query.rstrip().endswith(';'):
            if output_format != "json":  # Suppress in JSON mode
                console.print("[yellow]Warning: Trailing semicolon detected. DB2 for i JDBC driver may reject it. Consider removing the ';'.[/yellow]")
        
        # Use appropriate connection based on target
        if target == "as400":
            # Check if agent is available (no JVM needed in CLI)
            agent_url = os.environ.get("QADMCLI_AGENT_URL")
            if agent_url:
                from ..db.agent_client import AS400AgentClient
                client = AS400AgentClient(agent_url)
                if client.is_available():
                    # Add pagination
                    paginated_query = query
                    query_stripped = query.strip().upper()
                    if "FETCH FIRST" not in query_stripped and "LIMIT" not in query_stripped:
                        if "OFFSET" not in query_stripped:
                            paginated_query = f"{query} OFFSET {offset} ROWS FETCH FIRST {limit} ROWS ONLY"
                    
                    result = client.query(paginated_query)
                    
                    columns = result.get("columns", [])
                    rows = result.get("rows", [])
                    
                    if output_format == "json":
                        from ..utils.formatters import print_json_clean
                        results_list = []
                        for row in rows:
                            row_dict = {}
                            for i, col in enumerate(columns):
                                row_dict[str(col)] = row[i] if i < len(row) else None
                            results_list.append(row_dict)
                        print_json_clean(results_list)
                    elif output_format == "csv":
                        import csv, io
                        output = io.StringIO()
                        writer = csv.writer(output)
                        writer.writerow(columns)
                        for row in rows:
                            writer.writerow([str(cell) if cell is not None else "" for cell in row])
                        sys.stdout.write(output.getvalue())
                    else:
                        if rows:
                            table_rows = [[str(cell) if cell is not None else "NULL" for cell in row] for row in rows]
                            console.print(print_table(console, columns, table_rows, title="Query Results"))
                            console.print(f"[green]{len(rows)} row(s) returned[/green]")
                        else:
                            console.print("[yellow]No rows returned[/yellow]")
                    return
            
            # Fallback to direct JT400 connection
            config = load_config(config_path)
            as400_config = config.as400
            if user or password:
                as400_config = config.as400.copy_with_overrides(user=user, password=password)
                if output_format != "json":  # Suppress in JSON mode
                    console.print(f"[yellow]Using credential override: user={user or '***'}[/yellow]")
            from copy import deepcopy
            temp_config = deepcopy(config)
            temp_config.as400 = as400_config
            conn_manager = AS400ConnectionManager(temp_config)
            conn_manager.connect()
        else:
            config = load_config(config_path)
            if not config.mssql:
                console.print("[red]Error: MSSQL configuration not found in connection.yaml[/red]")
                sys.exit(1)
            mssql_config = config.mssql
            if user or password:
                mssql_config = config.mssql.copy_with_overrides(username=user, password=password)
                if output_format != "json":  # Suppress in JSON mode
                    console.print(f"[yellow]Using credential override: user={user or '***'}[/yellow]")
            conn_manager = MSSQLConnection(mssql_config)
            conn_manager.connect()
        
        try:
            # Add pagination if not already present
            paginated_query = query
            if target == "mssql":
                # MSSQL uses TOP syntax for simple pagination
                # Note: OFFSET/FETCH requires ORDER BY, so we only use TOP
                if "TOP" not in query_stripped and "OFFSET" not in query_stripped:
                    # Insert TOP after SELECT
                    query_upper = query.upper()
                    select_pos = query_upper.find("SELECT")
                    if select_pos >= 0:
                        # Insert TOP after SELECT
                        paginated_query = query[:select_pos + 6] + f" TOP {limit}" + query[select_pos + 6:]
            else:
                # DB2/AS400 syntax
                if "FETCH FIRST" not in query_stripped and "LIMIT" not in query_stripped:
                    if "OFFSET" not in query_stripped:
                        paginated_query = f"{query} OFFSET {offset} ROWS FETCH FIRST {limit} ROWS ONLY"
            
            # Get the appropriate cursor/connection
            if target == "mssql":
                cursor = conn_manager._connection.cursor()
                cursor.execute(paginated_query)
            else:
                cursor = conn_manager.execute(paginated_query)
            
            # Get column names
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            
            # Fetch all rows
            rows = cursor.fetchall()
            cursor.close()
            
            if not rows:
                console.print("[yellow]No rows returned[/yellow]")
                return
            
            # Convert rows to list of lists for easier handling
            table_data = []
            for row in rows:
                table_data.append([str(cell) if cell is not None else "NULL" for cell in row])
            
            # Output based on format
            if output_format == "json":
                # Clean JSON output for scripts (no Rich formatting)
                from ..utils.formatters import print_json_clean
                results = []
                for row in rows:
                    row_dict = {}
                    for i, col in enumerate(columns):
                        row_dict[str(col)] = row[i]
                    results.append(row_dict)
                print_json_clean(results)
            elif output_format == "csv":
                # CSV output
                import csv
                import io
                output = io.StringIO()
                writer = csv.writer(output)
                writer.writerow(columns)
                writer.writerows(table_data)
                console.print(output.getvalue())
            else:
                # Table output
                # Sanitize column names for Windows terminal compatibility
                def sanitize_column(name: str) -> str:
                    sanitized = str(name)
                    replacements = {
                        '\u2026': '...',
                        '\u2018': "'",
                        '\u2019': "'",
                        '\u201C': '"',
                        '\u201D': '"',
                        '\u2013': '-',
                        '\u2014': '--',
                    }
                    for unicode_char, ascii_char in replacements.items():
                        sanitized = sanitized.replace(unicode_char, ascii_char)
                    if len(sanitized) > 30:
                        sanitized = sanitized[:27] + '...'
                    return sanitized
                
                str_columns = [sanitize_column(str(col)) for col in columns]
                
                # Use ASCII border style if requested
                if border_style == "ascii":
                    from ..utils.formatters import print_table as format_table
                    console.print(format_table(
                        console,
                        str_columns,
                        table_data,
                        title=f"Query Results ({len(rows)} rows)"
                    ))
                else:
                    from rich.table import Table as RichTable
                    table = RichTable(title=f"Query Results ({len(rows)} rows)", show_header=True, header_style="bold magenta")
                    for col in str_columns:
                        table.add_column(col)
                    for row in table_data[:limit]:
                        table.add_row(*row)
                    console.print(table)
                
                console.print(f"[green]{len(rows)} row(s) returned[/green]")
                if len(rows) == limit:
                    console.print(f"[dim]Use --offset {offset + limit} to see more rows[/dim]")
        
        finally:
            # Always close connection
            conn_manager.disconnect()
    
    except ConnectionError as e:
        console.print(f"[red]Connection error: {e.message}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)




def register_sql_commands(cli_group):
    """Register SQL commands with the main CLI group."""
    cli_group.add_command(sql)
