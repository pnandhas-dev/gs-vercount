# QADM CLI - AS400 DB2 for i Database Management Tool

A Python-based CLI tool for managing AS400 DB2 for i database tables with connection management, table creation, journaling control, and journal entry retrieval/decoding capabilities.

## Features

- **Connection Management**: Connect to AS400 via jt400 JDBC driver with SSL support
- **Table Operations**: Create, check, list, drop, empty, and reverse-engineer tables using YAML or SQL schema definitions
- **Library Management**: Create libraries, manage user access, list with wildcard patterns, check privileges and journal status
- **User Management**: List, check, create, modify, delete users with privilege escalation support
- **Journal Management**: Enable/disable journaling, retrieve and decode journal entries
- **Mockup Data Generation**: Generate realistic test data with intelligent field pattern recognition (names, emails, phones, Thai names, etc.)
- **Dual Name Display**: Shows both system names (short) and SQL names (long) for tables
- **Flexible Configuration**: Environment variable substitution, YAML-based configs
- **Rich Output**: Beautiful terminal output with tables, JSON support, and colored logging
- **Container Ready**: Podman/Docker support for portable deployment

## Prerequisites

- Podman (or Docker) installed for container-based usage (recommended)
- Python 3.10+ for direct host usage
- Access to an AS400 system with DB2 for i
- jt400.jar (only needed for host-based agent setup or direct CLI mode)

## Installation

### Local Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd qadmcli
```

2. Download jt400.jar:
```bash
mkdir -p lib
curl -L -o lib/jt400.jar "https://sourceforge.net/projects/jt400/files/latest/download"
```

3. Install in editable mode:
```bash
pip install -e .
```

### Container Installation (Recommended)

The CLI auto-builds container images on first use. No manual build is needed:

```bash
# Just run any command — images build and agent starts automatically
cd /home/ubuntu/_qoder/qadmcli
cp .env.example .env
# Edit .env with your credentials
./qadmcli.sh connection check
```

To build images manually:
```bash
# Slim CLI image (pure Python, ~180MB)
podman build -t qadmcli-cli -f Containerfile.cli .

# Agent image (JVM + JT400 + ODBC, ~692MB)
podman build -t qadmcli-agent -f Containerfile.agent .
```

## Configuration

### 1. Connection Configuration

Copy the example configuration:
```bash
cp config/connection.yaml.example config/connection.yaml
```

Edit `config/connection.yaml`:
```yaml
as400:
  host: "as400.company.com"
  user: "${AS400_USER}"        # Uses environment variable
  password: "${AS400_PASSWORD}" # Uses environment variable
  port: 8471
  ssl: true
  database: "*LOCAL"

defaults:
  library: "QGPL"
  journal_library: "QSYS2"

logging:
  level: "INFO"
```

### 2. Environment Variables

Set credentials via environment variables:
```bash
export AS400_USER="your_username"
export AS400_PASSWORD="your_password"
export JT400_JAR="/path/to/jt400.jar"
```

Or use a `.env` file:
```bash
cp .env.example .env
# Edit .env with your credentials
```

### 3. Global CLI Options

The following options can be used with any command:

```bash
# Border style for panel displays (useful for Windows PowerShell)
qadmcli --border-style ascii table check -n CUSTOMERS -l MYLIB

# Verbose output
qadmcli --verbose table list -l MYLIB

# JSON output
qadmcli user check -u USER001

# Custom config file
qadmcli --config /path/to/connection.yaml table check -n CUSTOMERS -l MYLIB
```

**Note:** Global options must be placed **before** the subcommand:
```bash
# Correct:
qadmcli --border-style ascii user check -u USER001

# Incorrect:
qadmcli user check -u USER001 --border-style ascii  # WRONG
```

### 4. Table Schema Configuration

Create table definitions in YAML or SQL format:

**YAML Format** (`config/tables/mytable.yaml`):
```yaml
table:
  name: "CUSTOMERS"
  library: "MYLIB"
  description: "Customer master table"

columns:
  - name: "CUST_ID"
    type: "DECIMAL"
    length: 10
    scale: 0
    nullable: false
  - name: "CUST_NAME"
    type: "VARCHAR"
    length: 100
    nullable: false

constraints:
  primary_key:
    name: "PK_CUSTOMERS"
    columns: ["CUST_ID"]

journaling:
  enabled: true
```

**SQL Format** (`config/tables/mytable.sql`):
```sql
CREATE TABLE MYLIB.CUSTOMERS (
    CUST_ID DECIMAL(10, 0) NOT NULL,
    CUST_NAME VARCHAR(100) NOT NULL,
    CONSTRAINT PK_CUSTOMERS PRIMARY KEY (CUST_ID)
);
```

## Quick Start Guide

This guide walks you through a complete setup from library creation to journal-enabled table.

### 1. Create Library and User

Create a new library and user with appropriate authorities:

```bash
# Create library
qadmcli library create -n MYLIB

# Create user (requires *SECADM authority - will prompt for admin credentials)
qadmcli user create -u appuser -p SecurePass123 -l MYLIB

# Grant library authority
qadmcli library grant -n MYLIB -u appuser -a *ALL
```

**Privilege Escalation:** If your current user lacks *SECADM authority, you can elevate privileges on-the-fly:

```bash
# Option 1: Provide admin credentials via command line
qadmcli user create -u appuser -p SecurePass123 -l MYLIB -U QSECOFR -P adminpassword

# Option 2: Interactive prompting (will ask for admin credentials)
qadmcli user create -u appuser -p SecurePass123 -l MYLIB
# Output:
# Current user lacks *SECADM (Security Administrator) special authority.
# Administrative credentials required: *SECADM authority required
# Admin user: QSECOFR
# Admin password: ********
```

**Note:** Admin credentials are used only for the specific operation and are not stored.

**Verify user was created:**
```bash
# List users to verify creation
qadmcli user list --filter "appuser"

# Check user details
qadmcli user check -u appuser
```

### 2. Create Table with Journaling

Create a table schema file (`config/tables/orders.yaml`):

```yaml
table:
  name: "ORDERS"
  library: "MYLIB"
  description: "Order master table"

columns:
  - name: "ORDER_ID"
    type: "DECIMAL"
    length: 10
    scale: 0
    nullable: false
  - name: "CUSTOMER_NAME"
    type: "VARCHAR"
    length: 100
    nullable: false
  - name: "ORDER_DATE"
    type: "DATE"
    nullable: false
  - name: "AMOUNT"
    type: "DECIMAL"
    length: 15
    scale: 2

constraints:
  primary_key:
    name: "PK_ORDERS"
    columns: ["ORDER_ID"]

journaling:
  enabled: true
```

Create the table:
```bash
# Preview SQL (dry run)
qadmcli table create -s config/tables/orders.yaml --dry-run

# Create table with journaling
qadmcli table create -s config/tables/orders.yaml
```

### 3. Verify Setup

Check the table and journal status:

```bash
# Check table info (shows row count, journaling status, primary key)
qadmcli table check -t ORDERS -l MYLIB

# Check journal info
qadmcli journal info -t ORDERS -l MYLIB

# List tables in library
qadmcli table list -l MYLIB
```

### 4. Generate Mock Data (Optional)

Populate the table with test data:

```bash
# Dry run - preview generated data
qadmcli mockup generate -t ORDERS -l MYLIB --dry-run -r 10

# Generate 1000 transactions (50% insert, 30% update, 20% delete)
qadmcli mockup generate -t ORDERS -l MYLIB -r 1000

# Custom transaction mix
qadmcli mockup generate -t ORDERS -l MYLIB -r 500 \
  --insert-ratio 60 --update-ratio 30 --delete-ratio 10
```

### 5. View Journal Entries

After data changes, view the journal entries:

```bash
# Show recent journal entries
qadmcli journal entries -t ORDERS -l MYLIB --limit 50

# Show entries as JSON
qadmcli journal entries -t ORDERS -l MYLIB --limit 50
```

---

## Usage

### Connection Commands

Test connection to AS400:
```bash
qadmcli connection test-as400

# With custom credentials
qadmcli connection test-as400 -U ADMIN -P password

# JSON output
qadmcli connection test-as400 --format json
```

Test connection to MSSQL:
```bash
qadmcli connection test-mssql

# JSON output
qadmcli connection test-mssql --format json
```

### Table Commands

Check if table exists (shows both system and SQL names):
```bash
qadmcli table check -t CUSTOMERS -l MYLIB
```

Create table from YAML schema:
```bash
# Dry run (preview SQL)
qadmcli table create -s config/tables/customers.yaml --dry-run

# Execute creation
qadmcli table create -s config/tables/customers.yaml
```

Create table from SQL file:
```bash
qadmcli table create -s config/tables/orders.sql
```

Drop and recreate table:
```bash
qadmcli table drop-create -t CUSTOMERS -l MYLIB -s config/tables/customers.yaml --force
```

Drop a table:
```bash
qadmcli table drop -t CUSTOMERS -l MYLIB --force
```

Empty table data (DELETE all rows):
```bash
qadmcli table empty -t CUSTOMERS -l MYLIB --force
```

Reverse engineer table to YAML schema:
```bash
qadmcli table reverse -t CUSTOMERS -l MYLIB
qadmcli table reverse -t CUSTOMERS -l MYLIB -o /app/schemas/customers.yaml
```

List tables in a library (shows both system and SQL names):
```bash
qadmcli table list -l MYLIB
qadmcli table list -l MYLIB --format json
```

### Journal Commands

**Prerequisites:** Journal and journal receiver must exist before enabling journaling on tables.

#### Journal Lifecycle Management

**1. Create journal receiver:**
```bash
qadmcli journal create-receiver -n QSQJRN0001 -l MYLIB
qadmcli journal create-receiver -n QSQJRN0001 -l MYLIB --threshold 100000
```

**2. Create journal and attach to receiver:**
```bash
# Same library
qadmcli journal create -n QSQJRN -l MYLIB -r QSQJRN0001

# Cross-library (receiver in different library)
qadmcli journal create -n QSQJRN -l MYLIB -r QSQJRN0001 --receiver-library JRNLIB
```

**3. Rollover to new receiver (for large journals):**
```bash
# Auto-generate new receiver name
qadmcli journal rollover -j QSQJRN -l MYLIB

# Specify receiver name
qadmcli journal rollover -j QSQJRN -l MYLIB -r QSQJRN0002
```

**4. Monitor journal sizes:**
```bash
# Monitor all journals
qadmcli journal monitor

# Monitor specific library with custom threshold
qadmcli journal monitor -l MYLIB -t 500000
```

**5. View receiver chain:**
```bash
qadmcli journal receivers -j QSQJRN -l MYLIB
```

**6. Clean up old receivers:**
```bash
# Dry run first (recommended)
qadmcli journal cleanup -j QSQJRN -l MYLIB --keep 2 --dry-run

# Execute cleanup
qadmcli journal cleanup -j QSQJRN -l MYLIB --keep 2
```

#### Journal Operations

Check journal status:
Check journal status:
```bash
qadmcli journal check -t CUSTOMERS -l MYLIB

# JSON output
qadmcli journal check -t CUSTOMERS -l MYLIB
```

Enable journaling:
```bash
# Use default journal from config
qadmcli journal enable -t CUSTOMERS -l MYLIB

# Specify journal explicitly (supports cross-library)
qadmcli journal enable -t CUSTOMERS -l MYLIB --journal-library JRNLIB --journal-name QSQJRN

# Enable with BEFORE/AFTER images (BOTH) for CDC
qadmcli journal enable -t CUSTOMERS -l MYLIB --images *BOTH
```

Enable/disable journaling for multiple tables (wildcard support):
```bash
# Dry run first to see which tables match
qadmcli journal disable -t "TB_*" -l EZPIPE --dry-run

# Disable journaling for all TB_ tables
qadmcli journal disable -t "TB_*" -l EZPIPE

# Enable with BOTH images for TB_01 to TB_09
qadmcli journal enable -t "TB_0*" -l EZPIPE -j EZPIPE --images *BOTH

# Enable for all TEST tables
qadmcli journal enable -t "TEST*" -l MYLIB --images *AFTER
```

**Wildcard Characters:**
| Character | Meaning | Example |
|-----------|---------|---------|
| `*` | Multiple characters | `TB_*` matches TB_01, TB_02, etc. |
| `%` | Multiple characters (SQL style) | `TB_%` matches TB_01, TB_02, etc. |
| `?` | Single character | `TB_?` matches TB_1, TB_2, etc. |

**Note:** Underscore (`_`) is NOT a wildcard - it's a valid character in IBM i table names (e.g., `TB_01`).

Get journal entries:
```bash
# SQL format (default)
qadmcli journal entries -t CUSTOMERS -l MYLIB --limit 50

# JSON format
qadmcli journal entries -t CUSTOMERS -l MYLIB --limit 50
```

Get detailed journal info:
```bash
# Normal mode (shows entry range - may be slow for large journals)
qadmcli journal info -t CUSTOMERS -l MYLIB

# Fast mode (skips entry range query for better performance)
qadmcli journal info -t CUSTOMERS -l MYLIB --fast

# JSON output
qadmcli journal info -t CUSTOMERS -l MYLIB
```

Get journal info for multiple tables (wildcard support):
```bash
# Check journal status for all TB_ tables (fast mode recommended)
qadmcli journal info -t "TB_*" -l EZPIPE --fast

# Check all TEST tables
qadmcli journal info -t "TEST*" -l MYLIB --fast

# JSON output for multiple tables
qadmcli journal info -t "TB_*" -l EZPIPE --fast
```

**Wildcard batch output format:**
```
Journal info for 9 table(s):

  EZPIPE.TB_01: Journaled | BOTH | EZPIPE.QSQJRN
  EZPIPE.TB_02: Journaled | AFTER | EZPIPE.QSQJRN
  EZPIPE.TB_03: Not Journaled | N/A | N/A
  ...
```

This is useful for:
- Auditing journal status across multiple tables
- Checking write mode (BOTH/AFTER/BEFORE) for CDC setup
- Identifying non-journaled tables in a library

**Example output:**
```
+------ Detailed Journal Information -------+
| Table: MYLIB.CUSTOMERS                    |
|                                           |
| Journal Status:                           |
|   Journaled: Yes                          |
|   Journal: MYLIB.JRN                      |
|   Receiver: MYLIB.JRNRCV0001              |
|   Receiver Attached: 2026-03-05 12:03:30  |
|   Receiver Detached: Still attached       |
|                                           |
| Table Entry Range:                        |
|   Oldest Sequence: 71288177               |
|   Newest Sequence: 71296431               |
|   Oldest Time: 2026-03-05 12:03:30.436000 |
|   Newest Time: 2026-03-05 12:03:30.559808 |
|   Total Entries: 8252                     |
+-------------------------------------------+
```

The entry range shows the oldest and newest journal sequences for this specific table, useful for:
- CDC replication starting points
- Determining how much change data is available
- Troubleshooting replication lag

List all journals:
```bash
qadmcli journal list
qadmcli journal list -l MYLIB
```

> **Note:** The `journal enable` command does NOT auto-create journals. You must explicitly create the journal receiver and journal first using `journal create-receiver` and `journal create` commands.

#### Journal Size Management Best Practices

**Problem:** Large journals with millions of entries cause slow queries (100+ seconds).

**Solution:** Regular receiver rollovers and cleanup

```bash
# 1. Monitor for large journals
qadmcli journal monitor -l MYLIB

# 2. Check receiver chain
qadmcli journal receivers -j QSQJRN -l MYLIB

# 3. Rollover to new receiver (old becomes ONLINE)
qadmcli journal rollover -j QSQJRN -l MYLIB

# 4. Verify the change
qadmcli journal receivers -j QSQJRN -l MYLIB

# 5. Clean up old receivers
qadmcli journal cleanup -j QSQJRN -l MYLIB --keep 2 --dry-run
qadmcli journal cleanup -j QSQJRN -l MYLIB --keep 2
```

**Journal Size Categories:**
- **Small**: < 10,000 entries - Normal performance
- **Medium**: 10,000 - 1,000,000 entries - Use `--fast` flag for info
- **Large**: > 1,000,000 entries - Use `--fast` flag, consider rollover

**Receiver Status:**
- **ATTACHED**: Currently active receiver (never delete)
- **ONLINE**: Detached receiver (safe to delete after saving)
- **SAVED/PENDING**: Other states (review before deleting)

### User Commands

Check user existence and permissions:
```bash
qadmcli user check -u USER001
qadmcli user check -u USER001 -l MYLIB
qadmcli user check -u USER001 -l MYLIB -n "CUST*"
```

Check permissions for a specific table (includes journal permissions):
```bash
# Check user permissions on table and its related journal objects
qadmcli user check-table -u USER001 -t CUSTOMERS -l MYLIB

# Output shows:
# - Table permission (*FILE) with authority sources
# - Journal permission (*JRN) - even if in different library
# - Journal receiver permission (*JRNRCV)
# - User's special authorities and group profile
```

**Example output:**
```
+------------- Table Permission Check -------------+
| Checking permissions for USER001 on MYLIB.CUSTOMERS |
+--------------------------------------------------+

         User Information
 Attribute           | Value
---------------------+-------------
 Special Authorities | *ALLOBJ

                      Table Permissions
 Property            | Value
---------------------+---------------------------------------
 Object              | MYLIB.CUSTOMERS
 Type                | *FILE
 Effective Authority | *ALL
 Primary Source      | Object Ownership
 Authority Details   |   - Direct User Grant: *ALL
                     |   - *PUBLIC: *EXCLUDE
                     |   - Special Authority (*ALLOBJ): *ALL
                     |   - Object Ownership: *ALL (Owner)

                     Journal Permissions
 Property            | Value
---------------------+---------------------------------------
 Object              | MYLIB.JRN
 Type                | *JRN
 Effective Authority | *ALL
 Primary Source      | Direct User Grant
 Authority Details   |   - Direct User Grant: *ALL
                     |   - *PUBLIC: *ALL
                     |   - Special Authority (*ALLOBJ): *ALL

User has full permissions on table and journal objects.
```

**Authority Sources Explained:**

The command checks multiple authority sources to determine effective permissions:

| Source | Description |
|--------|-------------|
| **Direct User Grant** | Authority explicitly granted to the user via GRTOBJAUT |
| **Group Profile** | Authority inherited from user's group profile membership |
| **\*PUBLIC** | Public authority that applies to all users |
| **Special Authority (\*ALLOBJ)** | All-object special authority grants *ALL on all objects |
| **Object Ownership** | Object owner automatically has *ALL authority |

**IBM i Authority Levels:**

| Authority | Description | Common Uses |
|-----------|-------------|-------------|
| **\*ALL** | Full control - read, add, update, delete, execute, manage | Administrators, object owners |
| **\*CHANGE** | Read, add, update, delete | Power users, application users |
| **\*USE** | Read and execute only | Report users, read-only access |
| **\*EXCLUDE** | No access | Blocked users |

**Authority Hierarchy (highest to lowest):**
```
*ALL > *CHANGE > *USE > *EXCLUDE
```

The effective authority is the highest level from all sources. For example, if:
- Direct grant: *USE
- Group profile: *CHANGE
- *PUBLIC: *EXCLUDE
- *ALLOBJ special authority: *ALL

Then **Effective Authority = *ALL** (from *ALLOBJ)

This is especially useful for CDC and replication scenarios where you need to verify permissions on all related objects.

Create a new user:
```bash
qadmcli user create -u NEWUSER -p password123
qadmcli user create -u NEWUSER -p password123 -l MYLIB
```

**Privilege Escalation for User Creation:**

Creating users requires *SECADM (Security Administrator) special authority. If your current user lacks this authority, you can provide admin credentials using command-line options or interactive prompting:

```bash
# Method 1: Provide admin credentials via command line
qadmcli user create -u NEWUSER -p password123 -U QSECOFR -P adminpassword

# Method 2: Interactive prompting (will ask for admin user/password)
qadmcli user create -u NEWUSER -p password123
# Output:
# Current user lacks *SECADM (Security Administrator) special authority.
# Administrative credentials required: *SECADM authority required
# Admin user: QSECOFR
# Admin password: ********
```

**Options:**
- `-U, --admin-user`: Administrative user with *SECADM authority
- `-P, --admin-password`: Password for administrative user

**Note:** Admin credentials are used only for the user creation operation and are not stored.

Delete a user:
```bash
qadmcli user delete -u OLDUSER --force
```

Grant authority to user:
```bash
# Grant all authority
qadmcli user grant -u USER001 -g "*ALL" -l MYLIB

# Grant read-only authority
qadmcli user grant -u USER001 -g "*USE" -l MYLIB -n "CUST*"
```

Change user password:
```bash
qadmcli user password -u USER001 -p newpassword123
```

List user permissions:
```bash
qadmcli user permission -u USER001
qadmcli user permission -u USER001 -l MYLIB
```

List all users:
```bash
# List all users (first 100)
qadmcli user list

# List with limit
qadmcli user list --limit 50

# List only active users
qadmcli user list --active-only

# Filter users by name (supports wildcards)
qadmcli user list --filter "Q*"
qadmcli user list --filter "*ADMIN*"

# JSON output
qadmcli user list
```

**Output columns:**
- Status indicator (🟢 Active / 🔴 Disabled)
- Username
- User Class (*USER, *PGMR, *SYSOPR, *SECADM, *SECOFR)
- Status (Active, Disabled, Failed Logins, Password Expired)
- Group Profile
- Last Signon

Modify user profile:
```bash
# Change user class
qadmcli user modify -u GSUSER01 --class *PGMR
qadmcli user modify -u GLUEUSR --class *USER

# Enable/disable user
qadmcli user modify -u OLDUSER --status *DISABLED
qadmcli user modify -u NEWUSER --status *ENABLED

# Change group profile
qadmcli user modify -u USER001 --group QPGMR

# Update description
qadmcli user modify -u USER001 --text "Application service account"

# Multiple changes at once
qadmcli user modify -u USER001 --class *PGMR --group QPGMR --text "Developer account"
```

**Privilege Escalation for User Modification:**

Modifying user profiles requires *SECADM authority. If your current user lacks this authority, use the same privilege escalation pattern as user creation:

```bash
# Method 1: Provide admin credentials via command line
qadmcli user modify -u GSUSER01 --class *PGMR -U QSECOFR -P adminpassword

# Method 2: Interactive prompting
qadmcli user modify -u GSUSER01 --class *PGMR
# Output:
# Current user lacks *SECADM (Security Administrator) special authority.
# Administrative credentials required: *SECADM authority required
# Admin user: QSECOFR
# Admin password: ********
```

#### Use Case: Fixing User Permissions

When a user needs access to both tables and journals (required for CDC/replication scenarios):

**Step 1: Check current permissions**
```bash
# Check user has table and journal permissions
qadmcli --border-style ascii user check -u USER001 -l MYLIB

# Output shows:
# - Table permissions (*FILE)
# - Journal permissions (*JRN, *JRNRCV)
```

**Step 2: Grant table permissions (if missing)**
```bash
# Grant all authority on all tables
qadmcli user grant -u USER001 -g "*ALL" -l MYLIB -n "*" -t *FILE

# Or grant specific tables
qadmcli user grant -u USER001 -g "*CHANGE" -l MYLIB -n "CUST*" -t *FILE
```

**Step 3: Grant journal permissions (required for CDC)**
```bash
# First, find the journal name
qadmcli journal info -t CUSTOMERS -l MYLIB
# Output shows: Journal: MYLIB.MYJRN

# Grant authority on the journal
qadmcli user grant -u USER001 -g "*ALL" -l MYLIB -n MYJRN -t *JRN

# Grant authority on journal receivers (use wildcard for all)
qadmcli user grant -u USER001 -g "*ALL" -l MYLIB -n "MYJRN*" -t *JRNRCV
```

**Step 4: Verify permissions**
```bash
# Check-table shows consolidated view
qadmcli user check-table -u USER001 -t CUSTOMERS -l MYLIB
```

**Common Permission Issues:**

| Issue | Solution |
|-------|----------|
| "No journal permissions found" | Grant *JRN and *JRNRCV permissions |
| "User lacks authority" on journal | Use `user grant` with `-t *JRN` |
| "Cannot access journal receiver" | Grant `-t *JRNRCV` with wildcard name |
| Unicode border display issues | Use `--border-style ascii` before subcommand |

### Mockup Data Commands

Generate mock data with automatic field pattern recognition:
```bash
# Dry run - preview SQL statements
qadmcli mockup generate -t CUSTOMERS -l MYLIB --dry-run -r 100

# Execute with default ratios (50% insert, 30% update, 20% delete)
qadmcli mockup generate -t CUSTOMERS -l MYLIB -r 1000

# Custom transaction mix
qadmcli mockup generate -t CUSTOMERS -l MYLIB -r 1000 \
  --insert-ratio 60 --update-ratio 30 --delete-ratio 10

# Large batch with custom batch size
qadmcli mockup generate -t CUSTOMERS -l MYLIB -r 5000 -b 200

# Use schema file for hints and validation
qadmcli mockup generate -t ORDERTRANX -l MYLIB -s config/schema/order.yaml --dry-run -r 100

# Skip schema validation when using schema file
qadmcli mockup generate -t ORDERTRANX -l MYLIB -s config/schema/order.yaml --skip-validation -r 100
```

**Supported Field Patterns:**
- **Names**: `FIRST_NAME`, `LAST_NAME`, `THAI_FIRST_NAME`, `THAI_LAST_NAME`
- **Contact**: `EMAIL`, `PHONE`, `MOBILE`, `MOBILE_NO`
- **Dates**: `DATE`, `CREATED_DATE`, `UPDATED_DATE`, `BIRTH_DATE`
- **Financial**: `AMOUNT`, `PRICE`, `FEE`, `TAX`, `BALANCE`
- **IDs**: `ID`, `CUST_ID`, `ORDER_ID`, `USER_ID`
- **Status**: `STATUS`, `TYPE`, `ORDER_STATUS`

**Thai Data Support:**
Columns containing `THAI`, `TH_`, or `_TH` will generate Thai names:
```sql
-- For columns like THAI_FIRST_NAME, THAI_LAST_NAME
INSERT INTO CUSTOMERS (THAI_FIRST_NAME, THAI_LAST_NAME)
VALUES ('สมชาย', 'แสงสว่าง');
```

#### Schema Hints

When field names are not meaningful or you want to override the default data format, you can add hints to column descriptions using the format `[hint:xxx]` in your table schema.

**How to Add Hints:**

In your YAML schema file, add hints to the `description` field:
```yaml
columns:
  - name: "CUST_NAME"
    type: "VARCHAR"
    length: 100
    description: "Customer full name [hint:full_name]"
  - name: "CONTACT_INFO"
    type: "VARCHAR"
    length: 50
    description: "Contact [hint:email]"
  - name: "STATUS_CODE"
    type: "CHAR"
    length: 2
    description: "Status [hint:choices:AC,IN,PE,DL]"
```

Or when reverse-engineering from an existing table, add the hint to the COLUMN_TEXT in DB2:
```sql
-- Add hint to column description
COMMENT ON COLUMN MYLIB.CUSTOMERS.STATUS_CODE IS 'Status [hint:choices:AC,IN,PE,DL]';
```

**Available Hints:**

| Hint | Description | Example Output |
|------|-------------|----------------|
| **Names** |||
| `first_name` | English first name | "John", "Jane" |
| `last_name` | English last name | "Smith", "Johnson" |
| `full_name` | Full English name | "John Smith" |
| `thai_first_name` | Thai first name | "สมชาย", "สมหญิง" |
| `thai_last_name` | Thai last name | "แสงสว่าง", "รุ่งโรจน์" |
| `thai_full_name` | Full Thai name | "สมชาย แสงสว่าง" |
| **Contact** |||
| `email` | Email address | "john@gmail.com" |
| `phone` / `mobile` | Thai mobile number | "0812345678" |
| **Dates** |||
| `date` / `datetime` / `timestamp` | Random date within last 2 years | `2024-03-15` |
| **Financial** |||
| `amount` / `price` / `fee` / `tax` / `balance` | Monetary amount | 1234.56 |
| **IDs** |||
| `id` | Numeric ID | 123456789 |
| `uuid` | UUID string | "550e8400-e29b-41d4-a716-446655440000" |
| **Status/Type** |||
| `status` / `type` / `code` | Single status code | "A", "I", "P", "D" |
| **Address** |||
| `address` | Street address | "123 Main St" |
| `city` | City name | "Bangkok", "New York" |
| `country` | Country code | "TH", "US", "UK" |
| **Company** |||
| `company` | Company name | "Global Corp" |
| `department` | Department code | "IT", "Sales", "HR" |
| **Text** |||
| `text` / `description` / `notes` / `remarks` | Lorem ipsum text | "Lorem ipsum dolor" |
| **Random** |||
| `random` | Random alphanumeric | "aB3xK9mP2q" |
| `hash` | Hex hash string | "a1b2c3d4e5f6..." |
| **Advanced** |||
| `constant:<value>` | Fixed constant value | As specified |
| `range:<min>:<max>` | Numeric range | Random between min-max |
| `choices:<v1>,<v2>` | Random from list | One of the choices |
| **File-Based** |||
| `file:<path>:<column>` | Read from CSV column | Value from file |
| `paired:<path>:<cols>` | Paired columns from same row | Consistent row data |

**Hint Examples:**

```yaml
# Example schema with various hints
columns:
  # Name fields with explicit hints
  - name: "FNAME"
    type: "VARCHAR"
    length: 50
    description: "First name [hint:first_name]"

  - name: "LNAME"
    type: "VARCHAR"
    length: 50
    description: "Last name [hint:last_name]"

  # Thai name field
  - name: "NAME_TH"
    type: "VARCHAR"
    length: 100
    description: "Thai name [hint:thai_full_name]"

  # Contact info with hint (field name not descriptive)
  - name: "FIELD1"
    type: "VARCHAR"
    length: 100
    description: "Email [hint:email]"

  # Status with specific choices
  - name: "ORDER_STATUS"
    type: "CHAR"
    length: 2
    description: "Status [hint:choices:PE,CF,SH,CA,CM]"

  # Numeric range hint
  - name: "AGE"
    type: "INTEGER"
    description: "Age [hint:range:18:65]"

  # Constant value hint
  - name: "COUNTRY_CODE"
    type: "CHAR"
    length: 2
    description: "Country [hint:constant:TH]"

  # Department with choices
  - name: "DEPT"
    type: "VARCHAR"
    length: 20
    description: "Department [hint:choices:IT,Sales,Marketing,HR,Finance]"
```

**Priority:**
Hints override automatic field name pattern detection. If a hint is present, it will be used regardless of the column name.

#### Schema Validation

When using `--schema` with mockup generation, the tool validates that the actual table structure matches the schema file:

```bash
# Validate schema before generating data
qadmcli mockup generate -t ORDERTRANX -l MYLIB -s config/schema/order.yaml --dry-run -r 100

# Skip validation if needed
qadmcli mockup generate -t ORDERTRANX -l MYLIB -s config/schema/order.yaml --skip-validation -r 100
```

**Validation Checks:**
- Column existence
- Data type compatibility (e.g., VARCHAR vs CHAR)
- Length and scale
- Nullable constraints

**Error Example:**
```
Schema validation failed:
  - Column 'FUND_NAME_EN' nullable mismatch: expected True, got False
  - Column 'CREATED_DATE' type mismatch: expected TIMESTAMP, got TIMESTMP
```

#### File-Based Data Generation

For realistic test data, you can use external CSV files with the `file:` or `paired:` hints:

**Single Column from File:**
```yaml
columns:
  - name: "FUND_CODE"
    type: "CHAR"
    length: 10
    description: "Fund code [hint:file:/app/config/data/funds.csv:FUND_CODE]"
```

**Paired Columns (Consistent Row Selection):**
```yaml
columns:
  - name: "FUND_CODE"
    type: "CHAR"
    length: 10
    description: "Fund code [hint:paired:/app/config/data/funds.csv:FUND_CODE,FUND_NAME_TH,FUND_NAME_EN]"

  - name: "FUND_NAME_TH"
    type: "VARCHAR"
    length: 200
    description: "Thai fund name [hint:paired:/app/config/data/funds.csv:FUND_CODE,FUND_NAME_TH,FUND_NAME_EN]"

  - name: "FUND_NAME_EN"
    type: "VARCHAR"
    length: 100
    description: "English fund name [hint:paired:/app/config/data/funds.csv:FUND_CODE,FUND_NAME_TH,FUND_NAME_EN]"
```

**CSV File Format:**
```csv
FUND_CODE,FUND_NAME_TH,FUND_NAME_EN
SCBSET50,กองทุนเปิดไทยพาณิชย์หุ้นบัวหลวง SET50,SCB Bualuang SET50 Fund
KTAGRO,กองทุนเปิดกรุงไทยหุ้นเกษตร,KT Agri Equity Fund
TMBGOLD,กองทุนเปิดทีเอ็มบี โกลด์,TMB Gold Fund
```

**Benefits of Paired Hints:**
- All columns with the same `paired:` hint get values from the **same row**
- Ensures data consistency (e.g., fund code matches fund name)
- Perfect for master data like products, customers, or funds

### SQL Commands

#### SQL Query (SELECT with formatted output)

Execute SELECT queries with formatted output, pagination, and multiple output formats:

```bash
# AS400/DB2 queries (default)
qadmcli sql query -q "SELECT * FROM GSLIBTST.CUSTOMERS FETCH FIRST 10 ROWS ONLY"
qadmcli sql query -q "SELECT COUNT(*) FROM GSLIBTST.CUSTOMERS"
qadmcli sql query -q "SELECT CUST_ID, FIRST_NAME, EMAIL FROM GSLIBTST.CUSTOMERS WHERE CUST_ID < 200"

# MSSQL queries
qadmcli sql query -q "SELECT TOP 10 * FROM dbo.CUSTOMERS ORDER BY CREATED_AT DESC" --target mssql
qadmcli sql query -q "SELECT COUNT(*) FROM dbo.CUSTOMERS" --target mssql
qadmcli sql query -q "SELECT TOP 10 * FROM dbo.CUSTOMERS WHERE CREATED_AT > DATEADD(minute, -5, GETDATE())" --target mssql

# Output formats
qadmcli sql query -q "SELECT * FROM GSLIBTST.CUSTOMERS" --format json
qadmcli sql query -q "SELECT * FROM GSLIBTST.CUSTOMERS" --format csv
qadmcli sql query -q "SELECT * FROM GSLIBTST.CUSTOMERS" --format table  # default

# Pagination (AS400 uses FETCH FIRST, MSSQL uses TOP)
qadmcli sql query -q "SELECT * FROM GSLIBTST.CUSTOMERS" --limit 20 --offset 10
qadmcli sql query -q "SELECT * FROM dbo.CUSTOMERS" --target mssql --limit 50

# ASCII border style for Windows PowerShell
qadmcli --border-style ascii sql query -q "SELECT * FROM GSLIBTST.CUSTOMERS FETCH FIRST 5 ROWS ONLY"
```

**Features:**
- **Multi-database support**: AS400/DB2 (default) and MSSQL (`--target mssql`)
- **Output formats**: Table (default), JSON, CSV
- **Pagination**: `--limit` and `--offset` options
- **SELECT-only**: Only SELECT queries allowed (use `sql execute` for other SQL)

#### SQL Execute (General SQL)

Execute any SQL query directly:

```bash
# Execute a simple query
qadmcli sql execute -q "SELECT * FROM EZPIPE.TB_01 FETCH FIRST 10 ROWS ONLY"

# Query with current user
qadmcli sql execute -q "SELECT CURRENT_USER FROM SYSIBM.SYSDUMMY1"

# Check user permissions
qadmcli sql execute -q "SELECT OBJECT_AUTHORITY FROM QSYS2.OBJECT_PRIVILEGES WHERE AUTHORIZATION_NAME = 'USER001' AND OBJECT_SCHEMA = 'EZPIPE' AND OBJECT_NAME = 'TB_01'"

# Check journal info
qadmcli sql execute -q "SELECT * FROM QSYS2.JOURNALED_OBJECTS WHERE OBJECT_LIBRARY = 'EZPIPE'"

# Multi-line query (use quotes carefully)
qadmcli sql execute -q "SELECT JOURNAL_NAME, JOURNAL_LIBRARY, JOURNAL_IMAGES FROM QSYS2.JOURNALED_OBJECTS WHERE OBJECT_NAME = 'TB_01' AND OBJECT_LIBRARY = 'EZPIPE'"
```

**Use Cases:**
- Quick ad-hoc queries for troubleshooting
- Checking system views (QSYS2.*)
- Verifying permissions and authorities
- Testing SQL before using in applications
- Exploring database metadata

> **Note:** Use with caution on production systems. The SQL commands run with the credentials configured in your connection.yaml.

### Global Options

```bash
# Verbose output
qadmcli -v connection test-as400

# JSON output
qadmcli table check -t CUSTOMERS -l MYLIB --format json

# Custom config file
qadmcli -c /custom/path/connection.yaml table list -l MYLIB
```

### Library Management

Library commands help you manage AS400 libraries (schemas) and their security settings.

#### Create a Library

```bash
# Create a new library
qadmcli library create -n NEWLIB

# Create and grant authority to a user
qadmcli library create -n NEWLIB -u USER001

# Create with specific authority level
qadmcli library create -n NEWLIB -u USER001 -a *CHANGE
```

**Authority Levels:**
- `*USE` - Read-only access
- `*CHANGE` - Read/write access
- `*ALL` - Full control

#### Grant Library Access

```bash
# Grant read access
qadmcli library grant -n MYLIB -u USER001

# Grant full control
qadmcli library grant -n MYLIB -u USER001 -a *ALL
```

#### List Libraries

```bash
# List all libraries
qadmcli library list

# List libraries matching pattern (quote wildcards!)
qadmcli library list -p "GS*"
qadmcli library list -p "GSLIB*"
qadmcli library list -p "*PROD*"
qadmcli library list -p "TEST?"

# JSON output
qadmcli library list -p "GS*" -f json
```

> **Important:** Always quote wildcard patterns (`"GS*"`) to prevent shell expansion!

#### Check Library Privileges & Journal Status

```bash
# Check all users with privileges on a library
qadmcli library check -l GSLIBTST

# Check specific user's privileges
qadmcli library check -l GSLIBTST -u USER001

# JSON output
qadmcli library check -l GSLIBTST -f json
```

**Output includes:**
- User privileges (who has access and what authority)
- Journal status (enabled/disabled)
- Journal name and library (if journaling is enabled)

## Development Workflow with Podman

### Why Podman over Docker?

- **Rootless containers**: Better security, runs without root privileges
- **Daemonless architecture**: No background service required
- **Native systemd integration**: Better Linux integration
- **Docker-compatible CLI**: Same commands work

### Setup Steps

1. **Install Podman**:
   - **Linux**: `sudo apt install podman podman-compose` (Ubuntu/Debian)
   - **Windows**: Install [Podman Desktop](https://podman-desktop.io/)
   - **macOS**: `brew install podman podman-compose`

2. **Start Podman machine** (macOS/Windows):
   ```bash
   podman machine init
   podman machine start
   ```

3. **Build and run**:
   ```bash
   # Build image
   podman build -t qadmcli -f Containerfile .
   
   # Run interactive container
   podman run -it --rm \
     -e AS400_USER=$AS400_USER \
     -e AS400_PASSWORD=$AS400_PASSWORD \
     -v $(pwd)/config:/app/config:Z \
     qadmcli connection test-as400
   
   # Or use podman-compose
   podman-compose up -d
   podman exec -it qadmcli-dev qadmcli connection test-as400
   ```

4. **Development with hot-reload**:
   ```bash
   podman-compose up -d
   # Edit source files locally, changes reflect immediately
   podman exec -it qadmcli-dev qadmcli table list -l MYLIB
   ```

### Volume Mounts Explained

- `:Z` suffix: Required for rootless Podman to handle SELinux labeling
- `./src:/app/src`: Mount source code for development
- `./config:/app/config`: Mount configuration files

## CLI Command Reference

| Command | Description |
|---------|-------------|
| **Connection** | |
| `connection test-as400` | Test AS400 DB2 connection |
| `connection test-mssql` | Test MSSQL connection |
| **Table** | |
| `table check` | Check if table exists (shows system & SQL names) |
| `table create` | Create table from schema |
| `table drop-create` | Drop and recreate table |
| `table drop` | Drop a table |
| `table empty` | Delete all data from table |
| `table reverse` | Generate YAML schema from existing table |
| `table list` | List tables in library (shows system & SQL names) |
| **Journal** | |
| `journal check` | Check journal status |
| `journal cleanup` | Clean up old journal receivers |
| `journal create` | Create a journal |
| `journal create-receiver` | Create a journal receiver |
| `journal enable` | Enable journaling for a table |
| `journal entries` | Get journal entries |
| `journal info` | Get detailed journal info |
| `journal list` | List all journals with sizes |
| `journal monitor` | Monitor journal sizes and alert |
| `journal receivers` | Show receiver chain |
| `journal rollover` | Rollover to new receiver |
| **SQL** | |
| `sql execute` | Execute SQL queries |
| **User** | |
| `user check` | Check user existence and permissions |
| `user check-table` | Check permissions on table + journal + receiver |
| `user create` | Create a new user |
| `user delete` | Delete a user |
| `user grant` | Grant authority to user |
| `user password` | Change user password |
| `user permission` | List user permissions |
| **Mockup** | |
| `mockup generate` | Generate mock data with INSERT/UPDATE/DELETE |
| `mockup generate -s <schema>` | Generate with schema hints and validation |
| `mockup generate --skip-validation` | Skip schema validation |
| `mockup hint` | Show mockup schema file format and available hints |
| **Library** | |
| `library create` | Create a new library and optionally grant user authority |
| `library grant` | Grant authority to a user on a library |
| `library list` | List libraries with wildcard pattern support |
| `library check` | Check library privileges and journal status |
| **Cross-Database** | |
| `table convert` | Convert schema between DB2 and MSSQL |
| `table create-mssql` | Create table on MSSQL from schema |
| `table compare-schemas` | Compare schemas between DB2 and MSSQL |

## Cross-Database Schema Support

qadmcli supports creating tables on both DB2 for i (AS400) and MSSQL from the same schema file, with automatic type conversion.

### Type Mappings

| DB2 for i Type | MSSQL Type | Notes |
|---------------|-----------|-------|
| `DECIMAL(p,0)` + identity | `BIGINT IDENTITY` | Auto-increment PK |
| `DECIMAL(p,s)` | `DECIMAL(p,s)` | Exact match |
| `INTEGER` | `INT` | Direct mapping |
| `VARCHAR(n)` | `VARCHAR(n)` | Direct mapping |
| `NVARCHAR(n)` | `NVARCHAR(n)` | Unicode support |
| `TIMESTAMP` | `DATETIME2` | Higher precision |
| `DATE` | `DATE` | Direct mapping |
| `CLOB` | `VARCHAR(MAX)` | Large text |

### Converting Schema

```bash
# Convert DB2 schema to MSSQL format
qadmcli table convert -s config/schema/subscriber.yaml \
  --source-db DB2 --target-db MSSQL \
  -o config/schema/subscriber_mssql.yaml

# Preview conversion
qadmcli table convert -s config/schema/subscriber.yaml \
  --source-db DB2 --target-db MSSQL
```

### Creating Tables on MSSQL

```bash
# Create table on MSSQL from DB2 schema
qadmcli table create-mssql -t subscribers \
  -s config/schema/subscriber.yaml \
  -d mydatabase --schema-name dbo

# Dry run to preview SQL
qadmcli table create-mssql -t subscribers \
  -s config/schema/subscriber.yaml \
  -d mydatabase --dry-run

# Drop and recreate
qadmcli table create-mssql -t subscribers \
  -s config/schema/subscriber.yaml \
  -d mydatabase --drop-if-exists
```

### Comparing Schemas

```bash
# Compare DB2 table with MSSQL table
qadmcli table compare-schemas \
  --db2-table GSLIBTST.SUBSCRIBER \
  --mssql-table dbo.subscribers
```

### Testing Schema Roundtrip

```bash
# 1. Create table on DB2 from schema
qadmcli table create -t SUBSCRIBER -l TESTLIB \
  -s config/schema/subscriber.yaml

# 2. Reverse engineer the table back to YAML
qadmcli table reverse -t SUBSCRIBER -l TESTLIB \
  -o reversed_subscriber.yaml

# 3. Compare original with reversed
diff config/schema/subscriber.yaml reversed_subscriber.yaml

# 4. Create on MSSQL from same schema
qadmcli table create-mssql -t subscribers \
  -s config/schema/subscriber.yaml -d targetdb
```

## Journal Entry Types

| Code | Meaning | SQL Operation |
|------|---------|---------------|
| PT | Put | INSERT |
| UP | Update | UPDATE |
| DL | Delete | DELETE |
| BR | Before Image | - |
| UR | After Image | - |

## Troubleshooting

### Connection Issues

**"Connection refused"**:
- Verify AS400 hostname/IP
- Check DRDA port (8471) is open
- Confirm AS400 is online

**"Authentication failed"**:
- Verify username/password
- Check user profile is enabled
- Confirm user has *IOSYSCFG authority if needed

**"jt400.jar not found"**:
- Download from https://sourceforge.net/projects/jt400/
- Set `JT400_JAR` environment variable
- Place in `lib/jt400.jar`

### SSL Issues

If SSL connection fails:
```yaml
as400:
  ssl: false  # Use only in development/trusted networks
```

### Journal Issues

**"Journal does not exist"**:
- Create journal first: `CRTJRN JRN(MYLIB/QSQJRN)`
- Or use existing journal library

### Useful Diagnostic Queries

Use these SQL queries with `qadmcli sql execute` to troubleshoot issues:

**Check current user and session:**
```bash
qadmcli sql execute -q "SELECT CURRENT_USER, SESSION_USER FROM SYSIBM.SYSDUMMY1"
```

**Check user special authorities:**
```bash
qadmcli sql execute -q "SELECT AUTHORIZATION_NAME, SPECIAL_AUTHORITIES FROM QSYS2.USER_INFO WHERE AUTHORIZATION_NAME = 'USER001'"
```

**Check object permissions:**
```bash
# Direct permissions
qadmcli sql execute -q "SELECT OBJECT_NAME, OBJECT_TYPE, OBJECT_AUTHORITY FROM QSYS2.OBJECT_PRIVILEGES WHERE AUTHORIZATION_NAME = 'USER001' AND OBJECT_SCHEMA = 'EZPIPE'"

# Public permissions
qadmcli sql execute -q "SELECT OBJECT_NAME, OBJECT_TYPE, OBJECT_AUTHORITY FROM QSYS2.OBJECT_PRIVILEGES WHERE AUTHORIZATION_NAME = '*PUBLIC' AND OBJECT_SCHEMA = 'EZPIPE'"
```

**Check journal status for tables:**
```bash
qadmcli sql execute -q "SELECT OBJECT_NAME, OBJECT_LIBRARY, JOURNAL_NAME, JOURNAL_LIBRARY, JOURNAL_IMAGES FROM QSYS2.JOURNALED_OBJECTS WHERE OBJECT_LIBRARY = 'EZPIPE'"
```

**Check journal receivers:**
```bash
qadmcli sql execute -q "SELECT JOURNAL_NAME, JOURNAL_LIBRARY, RECEIVER_NAME, RECEIVER_LIBRARY, NUMBER_OF_JOURNAL_ENTRIES, SIZE FROM QSYS2.JOURNAL_RECEIVER_INFO WHERE JOURNAL_LIBRARY = 'EZPIPE'"
```

**Check table metadata:**
```bash
qadmcli sql execute -q "SELECT TABLE_NAME, TABLE_SCHEMA, NUMBER_ROWS, NUMBER_PARTITIONS FROM QSYS2.SYSTABLES WHERE TABLE_SCHEMA = 'EZPIPE'"
```

**Check object statistics (includes journal status):**
```bash
qadmcli sql execute -q "SELECT OBJNAME, OBJTYPE, OBJOWNER, JOURNALED, JOURNAL_NAME, JOURNAL_LIBRARY FROM TABLE(QSYS2.OBJECT_STATISTICS('EZPIPE', '*FILE', '*ALL'))"
```

**Find tables by pattern:**
```bash
qadmcli sql execute -q "SELECT TABLE_NAME FROM QSYS2.SYSTABLES WHERE TABLE_SCHEMA = 'EZPIPE' AND TABLE_NAME LIKE 'TB_%'"
```

**Check library ownership:**
```bash
qadmcli sql execute -q "SELECT OBJNAME, OBJOWNER FROM TABLE(QSYS2.OBJECT_STATISTICS('QSYS', '*LIB', 'EZPIPE'))"
```

### Useful MSSQL Queries

**Check if table has primary key:**
```bash
qadmcli sql query -q "SELECT tc.table_name, kc.column_name, tc.constraint_name FROM information_schema.table_constraints tc JOIN information_schema.key_column_usage kc ON tc.constraint_name = kc.constraint_name WHERE tc.constraint_type = 'PRIMARY KEY' AND tc.table_name = 'CUSTOMERS'" --target mssql
```

**List all tables with primary keys:**
```bash
qadmcli sql query -q "SELECT t.TABLE_NAME, c.COLUMN_NAME FROM INFORMATION_SCHEMA.TABLES t LEFT JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE c ON t.TABLE_NAME = c.TABLE_NAME AND OBJECTPROPERTY(OBJECT_ID(c.CONSTRAINT_SCHEMA + '.' + c.CONSTRAINT_NAME), 'IsPrimaryKey') = 1 WHERE t.TABLE_SCHEMA = 'dbo' AND t.TABLE_TYPE = 'BASE TABLE' ORDER BY t.TABLE_NAME" --target mssql
```

**Check if CDC is enabled on database:**
```bash
qadmcli sql query -q "SELECT name, is_cdc_enabled FROM sys.databases WHERE name = 'GSTargetDB'" --target mssql
```

**Check CDC enabled tables:**
```bash
qadmcli sql query -q "SELECT name, is_tracked_by_cdc FROM sys.tables WHERE is_tracked_by_cdc = 1" --target mssql
```

**Check table row counts:**
```bash
qadmcli sql query -q "SELECT t.name AS table_name, p.rows AS row_count FROM sys.tables t INNER JOIN sys.partitions p ON t.object_id = p.object_id WHERE p.index_id IN (0, 1) AND t.name = 'CUSTOMERS'" --target mssql
```

**Check column data types:**
```bash
qadmcli sql query -q "SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, IS_NULLABLE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'CUSTOMERS' AND TABLE_SCHEMA = 'dbo'" --target mssql
```

**Find tables containing a specific column:**
```bash
qadmcli sql query -q "SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE COLUMN_NAME LIKE '%CUST%' AND TABLE_SCHEMA = 'dbo' ORDER BY TABLE_NAME" --target mssql
```

**Find column by exact name across all tables:**
```bash
qadmcli sql query -q "SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH FROM INFORMATION_SCHEMA.COLUMNS WHERE COLUMN_NAME = 'CUST_ID' AND TABLE_SCHEMA = 'dbo' ORDER BY TABLE_NAME" --target mssql
```

### MSSQL User Management

Check user existence, login-to-user mapping, and permissions:

```bash
# Check if user exists and get permissions
qadmcli mssql user check -u GLUESYNC01

# Output shows:
# - Server login existence and details
# - Database user existence
# - Login-to-user mapping (via SID)
# - Server roles (sysadmin, etc.)
# - Database roles (db_owner, db_datareader, etc.)
# - Explicit permissions
```

**Check table permissions:**
```bash
# Check user permissions on specific table
qadmcli mssql user check-table -u GLUESYNC01 -t CUSTOMERS -s dbo

# Output shows:
# - Table existence
# - Server login status
# - Login-to-database-user mapping
# - Database roles (db_datareader, db_datawriter, etc.)
# - Effective permissions (as mapped user)
# - Explicit grants
# - Public permissions
```

**Example output:**
```
╭────────────── MSSQL Table Permission Check ─────────────╮
│ Checking permissions for gstgdblogin on dbo.Customers2  │
╰─────────────────────────────────────────────────────────╯

✓ Table dbo.Customers2 exists
✓ Server login: gstgdblogin
✓ Mapped to database user: gstgdbuser (type: SQL_USER)
✓ Database role: db_datareader (can SELECT from all tables)
✓ Database role: db_datawriter (can INSERT/UPDATE/DELETE all tables)
✓ Database role: db_ddladmin (can modify schema)

All database roles: db_datareader, db_datawriter, db_ddladmin, db_owner

✓ User can SELECT from this table
(Access via role: db_datareader)
```

**Grant permissions:**
```bash
# Grant SELECT permission
qadmcli mssql user grant -u GLUESYNC01 -p SELECT -t CUSTOMERS

# Grant multiple permissions
qadmcli mssql user grant -u GLUESYNC01 -p SELECT,INSERT,UPDATE -t ORDERS

# Grant ALL permissions
qadmcli mssql user grant -u GLUESYNC01 -p ALL -t PRODUCTS

# Custom schema
qadmcli mssql user grant -u GLUESYNC01 -p SELECT -t CUSTOMERS -s sales
```

**Common Database Roles:**

| Role | Permissions | Use Case |
|------|------------|----------|
| `db_owner` | Full database access | Database administrators |
| `db_datareader` | SELECT on all tables | Read-only access, reporting |
| `db_datawriter` | INSERT/UPDATE/DELETE on all tables | Data modification |
| `db_ddladmin` | CREATE/ALTER/DROP objects | Schema management |
| `db_securityadmin` | Manage permissions | Security administration |
| `db_backupoperator` | Backup database | Backup operations |

**Login-to-User Mapping:**

MSSQL uses a two-level security model:
1. **Server Login** - Authenticates to SQL Server
2. **Database User** - Authorizes access within a database

The `check` and `check-table` commands automatically trace the mapping via SID (Security Identifier) and report which database user context is being checked.

### MSSQL Change Tracking (CT)

**Check CT status on database and table:**
```bash
# Check if Change Tracking is enabled
qadmcli mssql ct status -t CUSTOMERS -s dbo

# Output shows:
# - Database CT status
# - Table CT status
# - Retention period
# - Auto cleanup setting
```

**Query changes using version:**
```bash
# Get all changes since version 0
qadmcli mssql ct changes -t CUSTOMERS -s dbo --since-version 0

# Get changes since specific version
qadmcli mssql ct changes -t CUSTOMERS -s dbo --since-version 12345

# Limit results
qadmcli mssql ct changes -t CUSTOMERS -s dbo --since-version 0 --limit 100
```

**Query changes using timestamp:**
```bash
# Get changes since specific timestamp
qadmcli mssql ct changes -t CUSTOMERS -s dbo --since "2025-04-09 10:00:00"

# Date only (defaults to 00:00:00)
qadmcli mssql ct changes -t CUSTOMERS -s dbo --since "2025-04-09"
```

**Output format options:**
```bash
# Table format (default)
qadmcli mssql ct changes -t CUSTOMERS -s dbo --since-version 0

# JSON format
qadmcli mssql ct changes -t CUSTOMERS -s dbo --since-version 0 --format json
```

**CT Change Tracking Workflow:**
```bash
# 1. Check CT is enabled
qadmcli mssql ct status -t CUSTOMERS

# 2. Get current version as baseline
qadmcli mssql ct changes -t CUSTOMERS --since-version 0 --limit 1
# Note: Current CT Version: 100

# 3. After application changes, query new changes
qadmcli mssql ct changes -t CUSTOMERS --since-version 100

# 4. Process changes by operation type:
#    I = Insert (add new records)
#    U = Update (modify existing records)
#    D = Delete (remove records)
```

**Enable/Disable Change Tracking via CLI:**

```bash
# Enable CT on database (requires ALTER DATABASE permission)
qadmcli mssql ct enable-db
qadmcli mssql ct enable-db -r 7 --no-auto-cleanup

# Enable CT with admin credentials
qadmcli mssql ct enable-db -U sa -P <password>

# Enable CT on table (requires ALTER permission, table must have PK)
qadmcli mssql ct enable-table -t CUSTOMERS
qadmcli mssql ct enable-table -t CUSTOMERS -s dbo --no-track-columns

# Enable CT on table with admin credentials
qadmcli mssql ct enable-table -t CUSTOMERS -U admin -P <password>

# Disable CT on table
qadmcli mssql ct disable-table -t CUSTOMERS

# Disable CT on database (removes all CT history)
qadmcli mssql ct disable-db
```

**Enable Change Tracking via SQL (alternative):**
```sql
-- Enable CT on database
ALTER DATABASE [GSTargetDB] SET CHANGE_TRACKING = ON
(CHANGE_RETENTION = 2 DAYS, AUTO_CLEANUP = ON);

-- Enable CT on table
ALTER TABLE [dbo].[CUSTOMERS] ENABLE CHANGE_TRACKING
WITH (TRACK_COLUMNS_UPDATED = ON);
```

## Project Structure

```
qadmcli/
├── src/qadmcli/           # Main CLI source code
│   ├── cli.py            # CLI entry point (click)
│   ├── config.py         # Configuration loader
│   ├── db/               # Database modules
│   │   ├── connection.py # AS400 connection (lazy jpype/jaydebeapi)
│   │   ├── agent_client.py # HTTP client for agent API
│   │   ├── schema.py     # Table operations
│   │   ├── journal.py    # Journal operations
│   │   ├── user.py       # User management
│   │   ├── mockup.py     # Mockup data generation (routes to agent)
│   │   ├── mssql.py      # MSSQL connection (lazy pyodbc)
│   │   ├── oracle.py     # Oracle connection (lazy oracledb)
│   │   └── mssql_ct.py   # MSSQL Change Tracking
│   ├── models/           # Data models
│   │   ├── connection.py
│   │   ├── table.py
│   │   └── journal.py
│   ├── cli_commands/     # CLI command groups
│   │   └── agent_commands.py  # Agent sub-command registration
│   └── utils/            # Utilities
│       ├── logger.py
│       ├── formatters.py
│       └── data_generator.py  # Mockup data patterns
├── qadmcli_agent/        # Agent daemon (heavy deps)
│   ├── server.py         # FastAPI REST server
│   ├── connection_pool.py # JT400 connection pool
│   ├── jvm_manager.py    # JVM lifecycle (jpype)
│   ├── cli.py            # Agent CLI commands (start/stop/status)
│   ├── mockup.py         # Bulk mockup via JDBC batch
│   └── utils/            # Agent utilities
│       ├── data_generator.py
│       ├── db_types.py
│       └── formatters.py
├── config/               # Configuration files
│   ├── connection.yaml.example
│   ├── schema/           # Table schema examples
│   └── data/             # Sample data files for mockup (CSV)
├── schemas/              # Schema definitions for mockup
├── scripts/              # Helper scripts
├── tests/                # Test suite
├── Containerfile         # Slim CLI image (symlink to Containerfile.cli)
├── Containerfile.cli     # Slim CLI container build
├── Containerfile.agent   # Agent container build
├── qadmcli.sh            # Shell wrapper (auto-start + detection)
└── pyproject.toml        # Python project config
```

## Example Schemas

- [Insurance Domain Schema](docs/insurance-schema.md) - Complete insurance business schema with customers, products, subscriptions, payments, and claims

## Changelog

### v0.4.0 (2025-04-20)

#### Split-Container Architecture
- **Dual container images**: `qadmcli-cli` (~180MB, pure Python) and `qadmcli-agent` (~692MB, JVM + JT400 + ODBC)
- **Auto-start agent**: `qadmcli.sh` automatically detects or starts the agent daemon
- **Lazy imports**: jpype, jaydebeapi, pyodbc, oracledb deferred to prevent CLI import failures without heavy deps
- **Optional dependency groups**: Agent deps in `pyproject.toml` `[agent]` group
- **PEP 563 future annotations**: `from __future__ import annotations` for deferred type hints
- **5x smaller CLI image**: 180MB vs 900MB monolithic
- **20x faster bulk operations**: ~200 rows/sec via persistent agent + connection pool

#### New Files
- `Containerfile.cli` — Slim CLI image definition
- `Containerfile.agent` — Agent image definition (JVM + ODBC + JT400)
- `qadmcli.sh` — Shell wrapper with agent auto-start, detection, and .env support
- `src/qadmcli/db/agent_client.py` — HTTP client for agent REST API
- `src/qadmcli/cli_commands/agent_commands.py` — Agent CLI registration
- `qadmcli_agent/` — Agent daemon package (server, connection_pool, jvm_manager, mockup)

### v0.3.1 (2025-04-09)

#### New Features
- **MSSQL Change Tracking Support**: New `qadmcli mssql ct` commands for monitoring data changes
  - `qadmcli mssql ct status` - Check CT enabled status on database and tables
  - `qadmcli mssql ct changes` - Query CHANGETABLE for INSERT/UPDATE/DELETE operations
  - `qadmcli mssql ct enable-db` / `disable-db` - Enable/disable CT on database with `-U`/`-P` admin credentials
  - `qadmcli mssql ct enable-table` / `disable-table` - Enable/disable CT on tables with admin credentials
  - Supports version-based and timestamp-based change queries
  - JSON and table output formats
- **FK-Aware Mockup Wrapper** (`scripts/mockup_with_fk.py`): Generate mock data with valid foreign key references
  - Schema registry with YAML support
  - Automatic dependency ordering
  - SQL-based generation for child tables with FK constraints

#### Improvements
- **Mockup Generate Options**: Changed `-n` (name) → `-t` (table), `-t` (transactions) → `-n` (number) for clarity
- **Admin Credential Support**: MSSQL CT commands support `-U` and `-P` options for privilege escalation (similar to AS400 commands)
- **Smart Credential Routing**: `qadmcli.ps1` automatically detects target database type and only requires relevant credentials (AS400 or MSSQL)
- **New MSSQL Commands**: Added `mssql test` and `mssql query` for more intuitive MSSQL operations (alternative to `sql query --target mssql`)

### v0.2.0 (2025-04-09)

#### New Features
- **SQL Name Auto-Resolution**: `table check` and related commands now automatically resolve SQL names to system names. Use either `INSURANCE_PRODUCTS` or `INSUR00001` - both work!
- **Insurance Domain Schema**: Added complete insurance domain example with CUSTOMERS, INSURANCE_PRODUCTS, SUBSCRIPTIONS, PAYMENTS, CLAIMS, and CLAIM_DOCUMENTS tables
- **Thai Name Support**: CUSTOMERS table now supports Thai first and last names with CCSID 838

#### Improvements
- **Table Check Display**: Fixed system name display to show actual short name from database
- **ASCII Border Style**: PK and ID indicators now use `[PK]` and `[ID]` instead of Unicode emojis when using `--border-style ascii`

#### Commands Enhanced
- `table check` - Now accepts both SQL names and system names
- `table_exists()` - Auto-resolves SQL names
- `get_table_info()` - Auto-resolves SQL names
- `get_columns()` - Auto-resolves SQL names
- `get_primary_key()` - Auto-resolves SQL names
- `get_table_row_count()` - Auto-resolves SQL names

### v0.1.0 (Initial Release)

- Connection management with jt400 JDBC driver
- Table operations (create, check, list, drop, empty, reverse)
- User management (list, check, create, modify, delete) with privilege escalation
- Journal management (enable/disable, retrieve entries, monitor)
- Mockup data generation with pattern recognition
- Container support (Podman/Docker)

## License

MIT License

## Contributing

Contributions welcome! Please follow the existing code style and add tests for new features.

## Support

For issues and questions:
- GitHub Issues: https://github.com/qoder/qadmcli/issues
- Documentation: See examples in `config/tables/`
