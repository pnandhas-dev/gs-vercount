"""Mockup Commands Module.

This module contains mock data generation CLI commands:
- mockup generate: Generate realistic test data
"""

import sys
from typing import Optional

import click
from rich.console import Console

from ..config import load_config
from ..db.connection import AS400ConnectionManager, ConnectionError
from ..db.mockup import MockupManager, MockupConfig, SchemaValidationError
from .utils import print_panel

console = Console()


@click.group()
def mockup():
    """Mockup data generation for testing.
    
    Generate realistic test data with automatic field pattern detection.
    Supports INSERT/UPDATE/DELETE operations with customizable ratios.
    """
    pass


def _load_schema_hints(schema_path: str) -> tuple[dict[str, str], dict]:
    """Load column hints and validation rules from a YAML schema file.

    Returns a tuple of (hints dict, validation dict).
    """
    import yaml
    import re

    hints = {}
    validation = {}
    try:
        with open(schema_path, 'r', encoding='utf-8') as f:
            schema = yaml.safe_load(f)

        if schema and 'columns' in schema:
            for col in schema['columns']:
                col_name = col.get('name')
                description = col.get('description', '')

                # Extract hint from description
                if col_name and description:
                    hint_match = re.search(r'\[hint:([^\]]+)\]', description, re.IGNORECASE)
                    if hint_match:
                        hints[col_name.upper()] = hint_match.group(1).strip()

                # Build validation rules for this column
                if col_name:
                    validation[col_name.upper()] = {
                        'type': col.get('type'),
                        'length': col.get('length'),
                        'scale': col.get('scale'),
                        'nullable': col.get('nullable'),
                    }

    except Exception as e:
        console.print(f"[yellow]Warning: Could not load schema from {schema_path}: {e}[/yellow]")

    return hints, validation


@mockup.command("generate")
@click.option("--table", "-t", required=True, help="Table name (e.g., TB_02)")
@click.option("--library", "-l", required=True, help="Library/schema name (e.g., EZPIPE)")
@click.option("--schema", "-s", help="Schema YAML file for column hints and validation")
@click.option("--skip-validation", is_flag=True, help="Skip schema validation when using --schema")
@click.option("--number", "-r", default=1000, show_default=True, help="Number of rows/transactions to generate")
@click.option("--insert-ratio", default=60, show_default=True, help="Percentage of INSERT operations (0-100)")
@click.option("--update-ratio", default=20, show_default=True, help="Percentage of UPDATE operations (0-100)")
@click.option("--delete-ratio", default=20, show_default=True, help="Percentage of DELETE operations (0-100)")
@click.option("--batch-size", "-b", default=100, show_default=True, help="Number of operations per batch commit")
@click.option("--dry-run", is_flag=True, help="Preview SQL statements without executing")
@click.option("--random", is_flag=True, help="Fetch random PKs from database instead of reusing inserts")
@click.pass_context
def mockup_generate(
    ctx: click.Context,
    table: str,
    library: str,
    schema: Optional[str],
    skip_validation: bool,
    number: int,
    insert_ratio: int,
    update_ratio: int,
    delete_ratio: int,
    batch_size: int,
    dry_run: bool,
    random: bool
) -> None:
    """Generate mock data with INSERT/UPDATE/DELETE operations.

    Generates realistic test data by automatically detecting field patterns based on column names.
    Supports tables with single or composite primary keys.
    """
    config_path = ctx.obj["config_path"]

    # Validate ratios
    total_ratio = insert_ratio + update_ratio + delete_ratio
    if total_ratio != 100:
        console.print(f"[red]Error: Ratios must sum to 100, got {total_ratio}[/red]")
        sys.exit(1)

    try:
        config = load_config(config_path)

        mockup_config = MockupConfig(
            insert_ratio=insert_ratio,
            update_ratio=update_ratio,
            delete_ratio=delete_ratio,
            total_transactions=number,
            batch_size=batch_size,
            dry_run=dry_run,
            random_pks=random
        )

        # Load schema hints and validation if provided
        schema_hints = {}
        schema_validation = {}
        if schema:
            schema_hints, schema_validation = _load_schema_hints(schema)
            console.print(f"[blue]Loaded hints from schema: {schema}[/blue]")
            if skip_validation:
                console.print(f"[yellow]Schema validation skipped[/yellow]")
                schema_validation = {}  # Clear validation rules

        with AS400ConnectionManager(config) as conn:
            mock_mgr = MockupManager(conn, schema_hints, schema_validation)

            console.print(f"[blue]Generating mock data for {library}.{table}...[/blue]")
            console.print(f"  Transactions: {number} (Insert: {insert_ratio}%, Update: {update_ratio}%, Delete: {delete_ratio}%)")
            console.print(f"  Batch size: {batch_size}")
            if dry_run:
                console.print(f"  [yellow]Dry run mode - generating SQL only[/yellow]")

            results = mock_mgr.generate_mock_data(table, library, mockup_config)
            
            if dry_run:
                # Output SQL statements
                sql_count = len(results["sql_statements"])
                console.print(f"\n[green]Generated {sql_count} SQL statements:[/green]")
                
                # Show first 10 statements
                for i, sql in enumerate(results["sql_statements"][:10]):
                    console.print(sql)
                
                if sql_count > 10:
                    console.print(f"\n... and {sql_count - 10} more statements")
            else:
                # Show statistics
                stats = results["stats"]
                console.print(f"\n[green]Mock data generation complete:[/green]")
                console.print(f"  Inserted: {stats['inserted']} rows")
                console.print(f"  Updated: {stats['updated']} rows")
                console.print(f"  Deleted: {stats['deleted']} rows")

    except SchemaValidationError as e:
        console.print(f"[red]Schema validation error:[/red]")
        console.print(f"[yellow]{e}[/yellow]")
        console.print(f"\n[blue]Tip: Use --dry-run to preview without validation, or fix the table schema to match.[/blue]")
        sys.exit(1)
    except ConnectionError as e:
        console.print(f"[red]Connection error: {e.message}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@mockup.command("hint")
def mockup_hint() -> None:
    """Show mockup schema file format and available hints.
    
    Explains how to create a YAML schema file for custom column hints
    and schema validation during mock data generation.
    """
    from rich.panel import Panel
    from rich.markdown import Markdown
    
    hint_guide = """
# Mockup Schema File Guide

Schema files allow you to provide **custom hints** for column data generation and **validate** table structure before generating data.

## Basic Structure

```yaml
columns:
  - name: COLUMN_NAME
    type: VARCHAR
    length: 100
    nullable: true
    description: "Customer first name [hint:first_name]"
```

## Available Hints

Hints are specified in the column description using `[hint:hint_name]`:

### Personal Information
- `first_name` - Generates realistic first names (e.g., "John", "สมชาย")
- `last_name` - Generates realistic last names (e.g., "Smith", "วงศ์สว่าง")
- `email` - Generates email addresses (e.g., "john.smith@example.com")
- `phone` - Generates phone numbers (e.g., "+1-555-0123")

### Financial Data
- `credit_card` - Generates 16-digit credit card numbers (Luhn-compliant)
- `amount` - Generates monetary values (e.g., 1234.56)
- `price` - Generates product prices
- `cost` - Generates cost values
- `fee` - Generates fee amounts
- `tax` - Generates tax amounts

### Identifiers
- `id` - Generates sequential IDs
- `uuid` - Generates UUIDs
- `code` - Generates alphanumeric codes

### Dates & Times
- `date` - Generates random dates
- `datetime` - Generates random timestamps
- `created_date` - Generates past dates (creation timestamps)
- `updated_date` - Generates recent dates (update timestamps)

### Status & Types
- `status` - Generates status values (ACTIVE, INACTIVE, PENDING)
- `type` - Generates type classifications
- `category` - Generates category names

### Text Data
- `string` - Generates random strings (default fallback)
- `text` - Generates longer text content
- `description` - Generates descriptive text

## Example Schema File

```yaml
# schema.yaml - Complete example for CUSTOMERS table
columns:
  - name: CUST_ID
    type: INTEGER
    nullable: false
    description: "Customer unique identifier [hint:id]"
    
  - name: FIRST_NAME
    type: VARCHAR
    length: 50
    nullable: false
    description: "Customer first name [hint:first_name]"
    
  - name: LAST_NAME
    type: VARCHAR
    length: 50
    nullable: false
    description: "Customer last name [hint:last_name]"
    
  - name: EMAIL
    type: VARCHAR
    length: 100
    nullable: true
    description: "Email address [hint:email]"
    
  - name: PHONE
    type: VARCHAR
    length: 20
    nullable: true
    description: "Contact phone number [hint:phone]"
    
  - name: CREDIT_CARD
    type: CHAR
    length: 19
    nullable: true
    description: "Credit card number [hint:credit_card]"
    
  - name: BALANCE
    type: DECIMAL
    length: 10
    scale: 2
    nullable: true
    description: "Account balance [hint:amount]"
    
  - name: STATUS
    type: VARCHAR
    length: 20
    nullable: false
    description: "Account status [hint:status]"
    
  - name: CREATED_AT
    type: TIMESTAMP
    nullable: false
    description: "Account creation date [hint:created_date]"
    
  - name: UPDATED_AT
    type: TIMESTAMP
    nullable: true
    description: "Last update timestamp [hint:updated_date]"
```

## Usage Examples

### Generate with schema hints
```bash
qadmcli mockup generate -t CUSTOMERS -l MYLIB \\
    -s config/schema/customers.yaml \\
    -r 1000
```

### Skip validation, use hints only
```bash
qadmcli mockup generate -t CUSTOMERS -l MYLIB \\
    -s config/schema/customers.yaml \\
    --skip-validation \\
    -r 500
```

### Dry run with schema
```bash
qadmcli mockup generate -t CUSTOMERS -l MYLIB \\
    -s config/schema/customers.yaml \\
    --dry-run \\
    -r 10
```

## How It Works

1. **Auto-detection**: Mockup automatically detects patterns from column names
   - `FIRST_NAME` → automatically uses `first_name` hint
   - `EMAIL` → automatically uses `email` hint

2. **Schema override**: Schema file hints override auto-detection
   - Column named `NAME1` with `[hint:first_name]` → generates first names

3. **Validation**: Schema validates column types and lengths match the actual table
   - Catches mismatches before generating data
   - Use `--skip-validation` to bypass checks

## Tips

- Hints are **case-insensitive** in descriptions
- Multiple words: use underscores (`first_name`, `credit_card`)
- Schema files are **optional** - mockup works without them
- Use `--dry-run` to preview generated SQL before executing
"""
    
    console.print(Panel(
        Markdown(hint_guide),
        title="Mockup Schema File Guide",
        border_style="cyan",
        padding=(1, 2)
    ))


def register_mockup_commands(cli_group):
    """Register mockup commands with the main CLI group."""
    cli_group.add_command(mockup)

