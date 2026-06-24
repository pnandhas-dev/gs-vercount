"""MSSQL user management operations."""

import logging
from typing import Any

from .mssql import MSSQLConnection

logger = logging.getLogger("qadmcli")


class MSSQLUserManager:
    """Manages MSSQL user operations."""
    
    def __init__(self, connection: MSSQLConnection):
        self.conn = connection
    
    def check_user(self, username: str) -> dict[str, Any]:
        """Check if user exists in MSSQL server and current database."""
        result = {
            "server_login_exists": False,
            "database_user_exists": False,
            "username": username,
            "server_login_info": None,
            "database_user_info": None,
            "mapped_database_user": None,  # NEW: Find DB user linked to login
            "server_roles": [],
            "database_roles": [],
            "explicit_permissions": []
        }
        
        cursor = self.conn._connection.cursor()
        
        try:
            # Check server login existence
            cursor.execute("""
                SELECT 
                    name,
                    type_desc,
                    is_disabled,
                    create_date,
                    modify_date,
                    default_database_name
                FROM sys.server_principals
                WHERE name = ?
            """, (username,))
            
            row = cursor.fetchone()
            if row:
                result["server_login_exists"] = True
                result["server_login_info"] = {
                    "name": row[0],
                    "type": row[1],
                    "is_disabled": row[2],
                    "create_date": str(row[3]) if row[3] else None,
                    "modify_date": str(row[4]) if row[4] else None,
                    "default_database": row[5]
                }
            
            # Check database user existence
            cursor.execute("""
                SELECT 
                    name,
                    type_desc,
                    create_date,
                    modify_date,
                    default_schema_name
                FROM sys.database_principals
                WHERE name = ?
            """, (username,))
            
            row = cursor.fetchone()
            if row:
                result["database_user_exists"] = True
                result["database_user_info"] = {
                    "name": row[0],
                    "type": row[1],
                    "create_date": str(row[2]) if row[2] else None,
                    "modify_date": str(row[3]) if row[3] else None,
                    "default_schema": row[4]
                }
            
            # NEW: Find database user mapped to this login (via SID matching)
            if result["server_login_exists"]:
                cursor.execute("""
                    SELECT 
                        sp.name AS login_name,
                        sp.sid AS login_sid,
                        dp.name AS database_user_name,
                        dp.type_desc AS user_type,
                        dp.default_schema_name
                    FROM sys.server_principals sp
                    LEFT JOIN sys.database_principals dp ON sp.sid = dp.sid
                    WHERE sp.name = ?
                """, (username,))
                
                mapped_row = cursor.fetchone()
                if mapped_row and mapped_row[2]:  # database_user_name exists
                    result["mapped_database_user"] = {
                        "login_name": mapped_row[0],
                        "login_sid": mapped_row[1].hex() if mapped_row[1] else None,
                        "database_user_name": mapped_row[2],
                        "user_type": mapped_row[3],
                        "default_schema": mapped_row[4]
                    }
            
            # Get server roles (if login exists)
            if result["server_login_exists"]:
                cursor.execute("""
                    SELECT r.name
                    FROM sys.server_role_members rm
                    JOIN sys.server_principals r ON rm.role_principal_id = r.principal_id
                    JOIN sys.server_principals m ON rm.member_principal_id = m.principal_id
                    WHERE m.name = ?
                """, (username,))
                
                result["server_roles"] = [row[0] for row in cursor.fetchall()]
            
            # Get database roles (if user exists)
            if result["database_user_exists"]:
                cursor.execute("""
                    SELECT r.name
                    FROM sys.database_role_members rm
                    JOIN sys.database_principals r ON rm.role_principal_id = r.principal_id
                    JOIN sys.database_principals m ON rm.member_principal_id = m.principal_id
                    WHERE m.name = ?
                """, (username,))
                
                result["database_roles"] = [row[0] for row in cursor.fetchall()]
            
            # Get explicit database permissions
            if result["database_user_exists"]:
                cursor.execute("""
                    SELECT 
                        p.permission_name,
                        p.state_desc,
                        p.class_desc,
                        OBJECT_NAME(p.major_id) AS object_name,
                        SCHEMA_NAME(o.schema_id) AS schema_name
                    FROM sys.database_permissions p
                    JOIN sys.database_principals dp ON p.grantee_principal_id = dp.principal_id
                    LEFT JOIN sys.objects o ON p.major_id = o.object_id
                    WHERE dp.name = ?
                    ORDER BY p.class_desc, object_name
                """, (username,))
                
                for row in cursor.fetchall():
                    result["explicit_permissions"].append({
                        "permission": row[0],
                        "state": row[1],
                        "class": row[2],
                        "object_name": row[3],
                        "schema_name": row[4]
                    })
        
        finally:
            cursor.close()
        
        return result
    
    def check_table_permissions(self, username: str, table: str, schema: str = "dbo") -> dict[str, Any]:
        """Check user permissions for a specific table."""
        result = {
            "username": username,
            "table": f"{schema}.{table}",
            "table_exists": False,
            "server_login_exists": False,
            "database_user_exists": False,
            "mapped_database_user": None,  # NEW: Track mapped user
            "is_sysadmin": False,
            "is_db_owner": False,
            "has_db_datareader": False,  # NEW: Can read all tables
            "has_db_datawriter": False,  # NEW: Can write all tables
            "has_db_ddladmin": False,    # NEW: Can modify schema
            "has_db_securityadmin": False,  # NEW: Can manage permissions
            "has_db_backupoperator": False,  # NEW: Can backup database
            "database_roles": [],  # NEW: All database roles
            "effective_permissions": [],
            "role_permissions": [],
            "public_permissions": []
        }
        
        cursor = self.conn._connection.cursor()
        
        try:
            # Check if table exists
            cursor.execute("""
                SELECT COUNT(*)
                FROM sys.tables t
                JOIN sys.schemas s ON t.schema_id = s.schema_id
                WHERE t.name = ? AND s.name = ?
            """, (table, schema))
            
            if cursor.fetchone()[0] > 0:
                result["table_exists"] = True
            
            # Check if user has login
            cursor.execute("""
                SELECT COUNT(*)
                FROM sys.server_principals
                WHERE name = ?
            """, (username,))
            
            if cursor.fetchone()[0] > 0:
                result["server_login_exists"] = True
            
            # Check if user has database user
            cursor.execute("""
                SELECT COUNT(*)
                FROM sys.database_principals
                WHERE name = ?
            """, (username,))
            
            if cursor.fetchone()[0] > 0:
                result["database_user_exists"] = True
            
            # NEW: Find mapped database user via SID
            if result["server_login_exists"]:
                cursor.execute("""
                    SELECT 
                        sp.name AS login_name,
                        dp.name AS database_user_name,
                        dp.type_desc AS user_type
                    FROM sys.server_principals sp
                    LEFT JOIN sys.database_principals dp ON sp.sid = dp.sid
                    WHERE sp.name = ?
                """, (username,))
                
                mapped_row = cursor.fetchone()
                if mapped_row and mapped_row[1]:  # database_user_name exists
                    result["mapped_database_user"] = {
                        "login_name": mapped_row[0],
                        "database_user_name": mapped_row[1],
                        "user_type": mapped_row[2]
                    }
                    # Use mapped user for permission checks
                    effective_username = mapped_row[1]
                else:
                    effective_username = username
            else:
                effective_username = username
            
            # Check if user is sysadmin (bypasses all permissions)
            cursor.execute("""
                SELECT COUNT(*)
                FROM sys.server_role_members rm
                JOIN sys.server_principals r ON rm.role_principal_id = r.principal_id
                JOIN sys.server_principals m ON rm.member_principal_id = m.principal_id
                WHERE m.name = ? AND r.name = 'sysadmin'
            """, (username,))
            
            if cursor.fetchone()[0] > 0:
                result["is_sysadmin"] = True
            
            # Check if user is db_owner
            if result["database_user_exists"]:
                cursor.execute("""
                    SELECT COUNT(*)
                    FROM sys.database_role_members rm
                    JOIN sys.database_principals r ON rm.role_principal_id = r.principal_id
                    JOIN sys.database_principals m ON rm.member_principal_id = m.principal_id
                    WHERE m.name = ? AND r.name = 'db_owner'
                """, (effective_username,))
                
                if cursor.fetchone()[0] > 0:
                    result["is_db_owner"] = True
            
            # Also check via mapped user if different
            if (result["mapped_database_user"] and 
                result["mapped_database_user"]["database_user_name"] != effective_username):
                mapped_user = result["mapped_database_user"]["database_user_name"]
                cursor.execute("""
                    SELECT COUNT(*)
                    FROM sys.database_role_members rm
                    JOIN sys.database_principals r ON rm.role_principal_id = r.principal_id
                    JOIN sys.database_principals m ON rm.member_principal_id = m.principal_id
                    WHERE m.name = ? AND r.name = 'db_owner'
                """, (mapped_user,))
                
                if cursor.fetchone()[0] > 0:
                    result["is_db_owner"] = True
            
            # Check for other important database roles
            if result["database_user_exists"] or result["mapped_database_user"]:
                # Check specific important roles
                for role_name in ['db_datareader', 'db_datawriter', 'db_ddladmin', 'db_securityadmin', 'db_backupoperator']:
                    cursor.execute("""
                        SELECT COUNT(*)
                        FROM sys.database_role_members rm
                        JOIN sys.database_principals r ON rm.role_principal_id = r.principal_id
                        JOIN sys.database_principals m ON rm.member_principal_id = m.principal_id
                        WHERE m.name = ? AND r.name = ?
                    """, (effective_username, role_name))
                    
                    if cursor.fetchone()[0] > 0:
                        if role_name == 'db_datareader':
                            result["has_db_datareader"] = True
                        elif role_name == 'db_datawriter':
                            result["has_db_datawriter"] = True
                        elif role_name == 'db_ddladmin':
                            result["has_db_ddladmin"] = True
                        elif role_name == 'db_securityadmin':
                            result["has_db_securityadmin"] = True
                        elif role_name == 'db_backupoperator':
                            result["has_db_backupoperator"] = True
                    
                    # Also check mapped user
                    if (result["mapped_database_user"] and 
                        result["mapped_database_user"]["database_user_name"] != effective_username):
                        mapped_user = result["mapped_database_user"]["database_user_name"]
                        cursor.execute("""
                            SELECT COUNT(*)
                            FROM sys.database_role_members rm
                            JOIN sys.database_principals r ON rm.role_principal_id = r.principal_id
                            JOIN sys.database_principals m ON rm.member_principal_id = m.principal_id
                            WHERE m.name = ? AND r.name = ?
                        """, (mapped_user, role_name))
                        
                        if cursor.fetchone()[0] > 0:
                            if role_name == 'db_datareader':
                                result["has_db_datareader"] = True
                            elif role_name == 'db_datawriter':
                                result["has_db_datawriter"] = True
                            elif role_name == 'db_ddladmin':
                                result["has_db_ddladmin"] = True
                            elif role_name == 'db_securityadmin':
                                result["has_db_securityadmin"] = True
                            elif role_name == 'db_backupoperator':
                                result["has_db_backupoperator"] = True
                
                # Get ALL database roles for this user
                cursor.execute("""
                    SELECT r.name
                    FROM sys.database_role_members rm
                    JOIN sys.database_principals r ON rm.role_principal_id = r.principal_id
                    JOIN sys.database_principals m ON rm.member_principal_id = m.principal_id
                    WHERE m.name = ?
                    ORDER BY r.name
                """, (effective_username,))
                
                result["database_roles"] = [row[0] for row in cursor.fetchall()]
                
                # Also get roles for mapped user if different
                if (result["mapped_database_user"] and 
                    result["mapped_database_user"]["database_user_name"] != effective_username):
                    mapped_user = result["mapped_database_user"]["database_user_name"]
                    cursor.execute("""
                        SELECT r.name
                        FROM sys.database_role_members rm
                        JOIN sys.database_principals r ON rm.role_principal_id = r.principal_id
                        JOIN sys.database_principals m ON rm.member_principal_id = m.principal_id
                        WHERE m.name = ?
                        ORDER BY r.name
                    """, (mapped_user,))
                    
                    mapped_roles = [row[0] for row in cursor.fetchall()]
                    # Merge roles (avoid duplicates)
                    result["database_roles"] = list(set(result["database_roles"] + mapped_roles))
                    result["database_roles"].sort()
            
            # Get table object_id
            cursor.execute("""
                SELECT t.object_id
                FROM sys.tables t
                JOIN sys.schemas s ON t.schema_id = s.schema_id
                WHERE t.name = ? AND s.name = ?
            """, (table, schema))
            
            table_row = cursor.fetchone()
            if not table_row:
                return result
            
            object_id = table_row[0]
            
            # Get effective permissions for the user on this table (only if user exists)
            if result["database_user_exists"] or result["mapped_database_user"]:
                try:
                    cursor.execute("""
                        EXECUTE AS USER = ?
                        
                        SELECT 
                            permission_name,
                            state_desc
                        FROM fn_my_permissions(?, 'OBJECT')
                        
                        REVERT
                    """, (effective_username, f"{schema}.{table}"))
                    
                    for row in cursor.fetchall():
                        result["effective_permissions"].append({
                            "permission": row[0],
                            "state": row[1]
                        })
                except Exception as e:
                    logger.warning(f"Could not get effective permissions for {username}: {e}")
            
            # Get explicit permissions granted to user on this table
            cursor.execute("""
                SELECT 
                    p.permission_name,
                    p.state_desc,
                    dp.name AS grantee
                FROM sys.database_permissions p
                JOIN sys.database_principals dp ON p.grantee_principal_id = dp.principal_id
                WHERE p.major_id = ? AND dp.name = ?
            """, (object_id, username))
            
            for row in cursor.fetchall():
                result["role_permissions"].append({
                    "permission": row[0],
                    "state": row[1],
                    "grantee": row[2]
                })
            
            # Get public permissions on this table
            cursor.execute("""
                SELECT 
                    p.permission_name,
                    p.state_desc
                FROM sys.database_permissions p
                JOIN sys.database_principals dp ON p.grantee_principal_id = dp.principal_id
                WHERE p.major_id = ? AND dp.name = 'public'
            """, (object_id,))
            
            for row in cursor.fetchall():
                result["public_permissions"].append({
                    "permission": row[0],
                    "state": row[1]
                })
        
        finally:
            cursor.close()
        
        return result
    
    def grant_permission(
        self,
        username: str,
        permission: str,
        object_name: str,
        object_type: str = "TABLE",
        schema: str = "dbo"
    ) -> dict[str, Any]:
        """Grant permission to user on database object."""
        result = {
            "success": False,
            "username": username,
            "permission": permission,
            "object": f"{schema}.{object_name}",
            "object_type": object_type,
            "sql_executed": None,
            "error": None
        }
        
        cursor = self.conn._connection.cursor()
        
        try:
            # Ensure user exists as database user
            cursor.execute("""
                SELECT COUNT(*) FROM sys.database_principals WHERE name = ?
            """, (username,))
            
            if cursor.fetchone()[0] == 0:
                # Create user from login
                cursor.execute(f"CREATE USER [{username}] FROM LOGIN [{username}]")
                self.conn._connection.commit()
            
            # Build GRANT statement
            if object_type.upper() == "TABLE":
                sql = f"GRANT {permission} ON [{schema}].[{object_name}] TO [{username}]"
            elif object_type.upper() == "SCHEMA":
                sql = f"GRANT {permission} ON SCHEMA::[{object_name}] TO [{username}]"
            elif object_type.upper() == "DATABASE":
                sql = f"GRANT {permission} TO [{username}]"
            else:
                sql = f"GRANT {permission} ON [{object_type}]::[{schema}].[{object_name}] TO [{username}]"
            
            result["sql_executed"] = sql
            
            # Execute GRANT
            cursor.execute(sql)
            self.conn._connection.commit()
            
            result["success"] = True
        
        except Exception as e:
            self.conn._connection.rollback()
            result["error"] = str(e)
            result["success"] = False
        
        finally:
            cursor.close()
        
        return result
