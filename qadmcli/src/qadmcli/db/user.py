"""User management operations."""

import logging
from typing import Any

from .connection import AS400ConnectionManager

logger = logging.getLogger("qadmcli")


class UserManager:
    """Manages AS400 user operations."""
    
    def __init__(self, connection: AS400ConnectionManager):
        self.conn = connection
    
    def check_user(self, username: str, library: str | None = None, object_name: str | None = None) -> dict[str, Any]:
        """Check if user exists and get permissions."""
        result = {
            "exists": False,
            "user": username.upper(),
            "permissions": [],
            "journal_permissions": []
        }
        
        # Check user existence
        sql = """
            SELECT 
                AUTHORIZATION_NAME,
                USER_CLASS_NAME,
                STATUS,
                GROUP_PROFILE_NAME,
                SPECIAL_AUTHORITIES
            FROM QSYS2.USER_INFO
            WHERE AUTHORIZATION_NAME = ?
        """
        cursor = self.conn.execute(sql, (username.upper(),))
        row = cursor.fetchone()
        cursor.close()
        
        if row:
            result["exists"] = True
            result["user_class"] = row[1]
            result["status"] = row[2]
            result["group_profile"] = row[3]
            result["special_authorities"] = row[4]
        
        # Get permissions if library specified
        if library and result["exists"]:
            obj_filter = object_name.upper() if object_name else "*ALL"
            
            # Query object privileges using OBJECT_STATISTICS
            perm_sql = """
                SELECT *
                FROM TABLE(QSYS2.OBJECT_STATISTICS(?, 'FILE', ?))
            """
            cursor = self.conn.execute(perm_sql, (library.upper(), obj_filter))
            
            for row in cursor.fetchall():
                result["permissions"].append({
                    "object": str(row[0]) if row[0] else "",  # OBJNAME
                    "object_type": str(row[1]) if row[1] else "*FILE",  # OBJTYPE
                    "authority": "*CHANGE"  # Default assumption for accessible objects
                })
            cursor.close()
            
            # Query journal and journal receiver permissions
            journal_sql = """
                SELECT 
                    OBJECT_NAME,
                    OBJECT_TYPE,
                    OBJECT_AUTHORITY
                FROM QSYS2.OBJECT_PRIVILEGES
                WHERE AUTHORIZATION_NAME = ?
                  AND OBJECT_SCHEMA = ?
                  AND OBJECT_TYPE IN ('*JRN', '*JRNRCV')
                ORDER BY OBJECT_TYPE, OBJECT_NAME
            """
            cursor = self.conn.execute(journal_sql, (username.upper(), library.upper()))
            
            for row in cursor.fetchall():
                result["journal_permissions"].append({
                    "object": str(row[0]) if row[0] else "",
                    "object_type": str(row[1]) if row[1] else "",
                    "authority": str(row[2]) if row[2] else "*NONE"
                })
            cursor.close()
        
        return result
    
    def _get_object_authority_with_source(
        self, 
        username: str, 
        object_library: str, 
        object_name: str, 
        object_type: str
    ) -> dict[str, Any]:
        """Get object authority with detailed source information.
        
        Checks multiple authority sources:
        1. Direct user authority from OBJECT_PRIVILEGES
        2. Group profile authority
        3. *PUBLIC authority
        4. Special authorities (*ALLOBJ)
        5. Ownership
        
        Returns dict with authority and source information.
        """
        result = {
            "authority": None,
            "source": None,
            "effective_authority": None,
            "details": []
        }
        
        # 1. Check direct user authority
        direct_sql = """
            SELECT OBJECT_AUTHORITY
            FROM QSYS2.OBJECT_PRIVILEGES
            WHERE AUTHORIZATION_NAME = ?
              AND OBJECT_SCHEMA = ?
              AND OBJECT_NAME = ?
              AND OBJECT_TYPE = ?
        """
        try:
            cursor = self.conn.execute(direct_sql, (
                username.upper(),
                object_library.upper(),
                object_name.upper(),
                object_type
            ))
            row = cursor.fetchone()
            cursor.close()
            if row and row[0]:
                result["details"].append({
                    "source": "Direct User Grant",
                    "authority": str(row[0])
                })
        except Exception as e:
            logger.debug(f"Could not get direct permission: {e}")
        
        # 2. Check group profile authority
        group_sql = """
            SELECT 
                g.GROUP_PROFILE_NAME,
                p.OBJECT_AUTHORITY
            FROM QSYS2.USER_INFO u
            JOIN QSYS2.OBJECT_PRIVILEGES p ON p.AUTHORIZATION_NAME = u.GROUP_PROFILE_NAME
            WHERE u.AUTHORIZATION_NAME = ?
              AND p.OBJECT_SCHEMA = ?
              AND p.OBJECT_NAME = ?
              AND p.OBJECT_TYPE = ?
              AND u.GROUP_PROFILE_NAME IS NOT NULL
              AND u.GROUP_PROFILE_NAME <> '*NONE'
        """
        try:
            cursor = self.conn.execute(group_sql, (
                username.upper(),
                object_library.upper(),
                object_name.upper(),
                object_type
            ))
            row = cursor.fetchone()
            cursor.close()
            if row and row[1]:
                result["details"].append({
                    "source": f"Group Profile ({row[0]})",
                    "authority": str(row[1])
                })
        except Exception as e:
            logger.debug(f"Could not get group permission: {e}")
        
        # 3. Check *PUBLIC authority
        public_sql = """
            SELECT OBJECT_AUTHORITY
            FROM QSYS2.OBJECT_PRIVILEGES
            WHERE AUTHORIZATION_NAME = '*PUBLIC'
              AND OBJECT_SCHEMA = ?
              AND OBJECT_NAME = ?
              AND OBJECT_TYPE = ?
        """
        try:
            cursor = self.conn.execute(public_sql, (
                object_library.upper(),
                object_name.upper(),
                object_type
            ))
            row = cursor.fetchone()
            cursor.close()
            if row and row[0]:
                result["details"].append({
                    "source": "*PUBLIC",
                    "authority": str(row[0])
                })
        except Exception as e:
            logger.debug(f"Could not get public permission: {e}")
        
        # 4. Check special authorities (*ALLOBJ)
        special_sql = """
            SELECT SPECIAL_AUTHORITIES
            FROM QSYS2.USER_INFO
            WHERE AUTHORIZATION_NAME = ?
        """
        try:
            cursor = self.conn.execute(special_sql, (username.upper(),))
            row = cursor.fetchone()
            cursor.close()
            if row and row[0]:
                special_auths = str(row[0])
                if '*ALLOBJ' in special_auths:
                    result["details"].append({
                        "source": "Special Authority (*ALLOBJ)",
                        "authority": "*ALL"
                    })
        except Exception as e:
            logger.debug(f"Could not get special authorities: {e}")
        
        # 5. Check ownership
        owner_sql = """
            SELECT OBJOWNER
            FROM TABLE(QSYS2.OBJECT_STATISTICS(?, ?, ?))
        """
        try:
            cursor = self.conn.execute(owner_sql, (
                object_library.upper(),
                object_type,
                object_name.upper()
            ))
            row = cursor.fetchone()
            cursor.close()
            if row and row[0]:
                owner = str(row[0])
                if owner.upper() == username.upper():
                    result["details"].append({
                        "source": "Object Ownership",
                        "authority": "*ALL (Owner)"
                    })
        except Exception as e:
            logger.debug(f"Could not get ownership: {e}")
        
        # Determine effective authority (highest level wins)
        authority_hierarchy = ["*EXCLUDE", "*USE", "*CHANGE", "*ALL"]
        effective_auth = None
        effective_source = None
        
        for detail in result["details"]:
            auth = detail["authority"]
            # Handle owner authority
            if "Owner" in auth:
                effective_auth = "*ALL"
                effective_source = detail["source"]
                break
            # Handle standard authorities
            for i, level in enumerate(authority_hierarchy):
                if level in auth:
                    if effective_auth is None or authority_hierarchy.index(effective_auth) < i:
                        effective_auth = level
                        effective_source = detail["source"]
                    break
        
        result["authority"] = effective_auth
        result["source"] = effective_source
        result["effective_authority"] = effective_auth if effective_auth else "*NONE"
        
        return result
    
    def check_table_permissions_with_journal(
        self, 
        username: str, 
        table_name: str, 
        table_library: str
    ) -> dict[str, Any]:
        """Check user permissions for a specific table and its related journal objects.
        
        Returns a consolidated view showing:
        - Table permissions with authority sources
        - Journal permissions (even if journal is in different library)
        - Journal receiver permissions
        - Group profile and special authority information
        """
        result = {
            "user": username.upper(),
            "user_info": {
                "group_profile": None,
                "special_authorities": None
            },
            "table": {
                "name": table_name.upper(),
                "library": table_library.upper(),
                "authority": None,
                "source": None,
                "details": []
            },
            "journal": {
                "name": None,
                "library": None,
                "authority": None,
                "source": None,
                "details": []
            },
            "journal_receiver": {
                "name": None,
                "library": None,
                "authority": None,
                "source": None,
                "details": []
            }
        }
        
        # Get user info (group profile and special authorities)
        user_sql = """
            SELECT GROUP_PROFILE_NAME, SPECIAL_AUTHORITIES
            FROM QSYS2.USER_INFO
            WHERE AUTHORIZATION_NAME = ?
        """
        try:
            cursor = self.conn.execute(user_sql, (username.upper(),))
            row = cursor.fetchone()
            cursor.close()
            if row:
                result["user_info"]["group_profile"] = str(row[0]) if row[0] else "*NONE"
                result["user_info"]["special_authorities"] = str(row[1]) if row[1] else "*NONE"
        except Exception as e:
            logger.debug(f"Could not get user info: {e}")
        
        # 1. Check table permission with all sources
        table_auth = self._get_object_authority_with_source(
            username, table_library, table_name, "*FILE"
        )
        result["table"]["authority"] = table_auth["effective_authority"]
        result["table"]["source"] = table_auth["source"]
        result["table"]["details"] = table_auth["details"]
        
        # 2. Get journal info for this table
        journal_sql = """
            SELECT 
                j.JOURNAL_NAME,
                j.JOURNAL_LIBRARY,
                r.ATTACHED_JOURNAL_RECEIVER_NAME,
                r.ATTACHED_JOURNAL_RECEIVER_LIBRARY
            FROM QSYS2.SYSTABLES t
            LEFT JOIN QSYS2.JOURNALED_OBJECTS j ON (
                t.TABLE_SCHEMA = j.OBJECT_LIBRARY 
                AND t.SYSTEM_TABLE_NAME = j.OBJECT_NAME
            )
            LEFT JOIN QSYS2.JOURNAL_INFO r ON (
                j.JOURNAL_LIBRARY = r.JOURNAL_LIBRARY
                AND j.JOURNAL_NAME = r.JOURNAL_NAME
            )
            WHERE t.TABLE_SCHEMA = ?
              AND t.TABLE_NAME = ?
            FETCH FIRST 1 ROW ONLY
        """
        try:
            cursor = self.conn.execute(journal_sql, (
                table_library.upper(),
                table_name.upper()
            ))
            row = cursor.fetchone()
            cursor.close()
            
            if row:
                journal_name = str(row[0]) if row[0] else None
                journal_library = str(row[1]) if row[1] else None
                receiver_name = str(row[2]) if row[2] else None
                receiver_library = str(row[3]) if row[3] else None
                
                result["journal"]["name"] = journal_name
                result["journal"]["library"] = journal_library
                result["journal_receiver"]["name"] = receiver_name
                result["journal_receiver"]["library"] = receiver_library
                
                # 3. Check journal permission with all sources
                if journal_name and journal_library:
                    jrn_auth = self._get_object_authority_with_source(
                        username, journal_library, journal_name, "*JRN"
                    )
                    result["journal"]["authority"] = jrn_auth["effective_authority"]
                    result["journal"]["source"] = jrn_auth["source"]
                    result["journal"]["details"] = jrn_auth["details"]
                
                # 4. Check journal receiver permission with all sources
                if receiver_name and receiver_library:
                    rcv_auth = self._get_object_authority_with_source(
                        username, receiver_library, receiver_name, "*JRNRCV"
                    )
                    result["journal_receiver"]["authority"] = rcv_auth["effective_authority"]
                    result["journal_receiver"]["source"] = rcv_auth["source"]
                    result["journal_receiver"]["details"] = rcv_auth["details"]
                        
        except Exception as e:
            logger.debug(f"Could not get journal info: {e}")
        
        return result
    
    def create_library(self, library_name: str) -> dict[str, Any]:
        """Create a new library.
        
        Args:
            library_name: Name of the library to create
            
        Returns:
            Dictionary with creation results
        """
        cmd = f"CRTLIB LIB({library_name.upper()})"
        
        sql = "CALL QSYS2.QCMDEXC(?, ?)"
        cmd_bytes = cmd.encode('utf-8')
        cursor = self.conn.execute(sql, (cmd, len(cmd_bytes)))
        cursor.close()
        
        logger.info(f"Created library {library_name.upper()}")
        return {
            "library": library_name.upper(),
            "created": True
        }
    
    def create_user(self, username: str, password: str | None = None) -> dict[str, Any]:
        """Create a new user profile."""
        # Use CRTUSRPRF command via QCMDEXC
        # Note: Password must be enclosed in quotes if it contains special characters
        if password:
            password_param = f"PASSWORD('{password}')"
        else:
            password_param = ""
        
        # Specify JOBD(QGPL/QDFTJOBD) to avoid CPF2242 error
        cmd = f"CRTUSRPRF USRPRF({username.upper()}) {password_param} STATUS(*ENABLED) JOBD(QGPL/QDFTJOBD)"
        
        logger.debug(f"Executing command: CRTUSRPRF USRPRF({username.upper()}) ...")
        
        # Execute via QCMDEXC
        sql = "CALL QSYS2.QCMDEXC(?, ?)"
        cmd_bytes = cmd.encode('utf-8')
        cursor = self.conn.execute(sql, (cmd, len(cmd_bytes)))
        cursor.close()
        
        logger.info(f"Created user {username}")
        return {"user": username.upper(), "created": True}
    
    def delete_user(self, username: str) -> dict[str, Any]:
        """Delete a user profile."""
        cmd = f"DLTUSRPRF USRPRF({username.upper()})"
        
        sql = "CALL QSYS2.QCMDEXC(?, ?)"
        cmd_bytes = cmd.encode('utf-8')
        cursor = self.conn.execute(sql, (cmd, len(cmd_bytes)))
        cursor.close()
        
        logger.info(f"Deleted user {username}")
        return {"user": username.upper(), "deleted": True}
    
    def change_password(self, username: str, password: str) -> dict[str, Any]:
        """Change user password."""
        cmd = f"CHGUSRPRF USRPRF({username.upper()}) PASSWORD({password})"
        
        sql = "CALL QSYS2.QCMDEXC(?, ?)"
        cmd_bytes = cmd.encode('utf-8')
        cursor = self.conn.execute(sql, (cmd, len(cmd_bytes)))
        cursor.close()
        
        logger.info(f"Changed password for user {username}")
        return {"user": username.upper(), "password_changed": True}
    
    def modify_user(
        self,
        username: str,
        user_class: str | None = None,
        status: str | None = None,
        group_profile: str | None = None,
        text_description: str | None = None
    ) -> dict[str, Any]:
        """Modify user profile attributes.
        
        Args:
            username: User to modify
            user_class: User class (*USER, *PGMR, *SYSOPR, *SECADM, *SECOFR)
            status: User status (*ENABLED or *DISABLED)
            group_profile: Group profile name or *NONE
            text_description: Text description (up to 50 characters)
            
        Returns:
            Dictionary with modification results
        """
        changes = []
        params = []
        
        # Build the CHGUSRPRF command
        if user_class:
            params.append(f"USRCLS({user_class.upper()})")
            changes.append(f"User class set to {user_class.upper()}")
        
        if status:
            params.append(f"STATUS({status.upper()})")
            changes.append(f"Status set to {status.upper()}")
        
        if group_profile:
            if group_profile.upper() == "*NONE":
                params.append("GRPPRF(*NONE)")
                changes.append("Group profile removed")
            else:
                params.append(f"GRPPRF({group_profile.upper()})")
                changes.append(f"Group profile set to {group_profile.upper()}")
        
        if text_description:
            # Truncate to 50 chars if needed
            desc = text_description[:50]
            params.append(f"TEXT('{desc}')")
            changes.append(f"Description updated")
        
        # Build and execute command
        cmd = f"CHGUSRPRF USRPRF({username.upper()}) {' '.join(params)}"
        
        sql = "CALL QSYS2.QCMDEXC(?, ?)"
        cmd_bytes = cmd.encode('utf-8')
        cursor = self.conn.execute(sql, (cmd, len(cmd_bytes)))
        cursor.close()
        
        logger.info(f"Modified user {username}: {', '.join(changes)}")
        return {
            "user": username.upper(),
            "modified": True,
            "changes": changes
        }
    
    def grant_object_authority(self, username: str, library: str, object_name: str, authority: str, object_type: str = "*FILE") -> dict[str, Any]:
        """Grant object authority to user.
        
        Args:
            username: User to grant authority to
            library: Library containing the object
            object_name: Object name or *ALL
            authority: Authority level (*USE, *CHANGE, *ALL, etc.)
            object_type: Object type (*FILE, *JRN, *JRNRCV, *LIB, *ALL)
        """
        # For libraries, the object name is the library name itself
        # and the format is just LIBNAME not LIBNAME/LIBNAME
        if object_type == "*LIB":
            cmd = f"GRTOBJAUT OBJ({library.upper()}) OBJTYPE({object_type}) USER({username.upper()}) AUT({authority})"
        else:
            cmd = f"GRTOBJAUT OBJ({library.upper()}/{object_name}) OBJTYPE({object_type}) USER({username.upper()}) AUT({authority})"
        
        sql = "CALL QSYS2.QCMDEXC(?, ?)"
        cmd_bytes = cmd.encode('utf-8')
        cursor = self.conn.execute(sql, (cmd, len(cmd_bytes)))
        cursor.close()
        
        logger.info(f"Granted {authority} authority to {username} on {library}/{object_name} ({object_type})")
        return {
            "user": username.upper(),
            "library": library.upper(),
            "object": object_name,
            "object_type": object_type,
            "authority": authority
        }
    
    def grant_library_permissions(self, username: str, library: str, object_name: str | None = None) -> dict[str, Any]:
        """Grant permissions on library objects."""
        obj_filter = object_name.upper() if object_name else "*ALL"
        
        # Grant on library
        cmd = f"GRTOBJAUT OBJ({library.upper()}) OBJTYPE(*LIB) USER({username.upper()}) AUT(*USE)"
        sql = "CALL QSYS2.QCMDEXC(?, ?)"
        cmd_bytes = cmd.encode('utf-8')
        cursor = self.conn.execute(sql, (cmd, len(cmd_bytes)))
        cursor.close()
        
        # Grant on objects
        cmd = f"GRTOBJAUT OBJ({library.upper()}/{obj_filter}) OBJTYPE(*ALL) USER({username.upper()}) AUT(*CHANGE)"
        cmd_bytes = cmd.encode('utf-8')
        cursor = self.conn.execute(sql, (cmd, len(cmd_bytes)))
        cursor.close()
        
        logger.info(f"Granted permissions to {username} on {library}/{obj_filter}")
        return {
            "user": username.upper(),
            "library": library.upper(),
            "objects": obj_filter
        }
    
    def list_users(self, filter_name: str | None = None, only_active: bool = False) -> list[dict[str, Any]]:
        """List all user profiles with status and default library information.
        
        Args:
            filter_name: Optional filter to search for specific user names (supports wildcards)
            only_active: If True, only return enabled users
            
        Returns:
            List of user dictionaries with profile information
        """
        users = []
        
        # Build the WHERE clause based on filters
        where_conditions = []
        params = []
        
        if filter_name:
            # Support SQL wildcards: % for multiple chars, _ for single char
            where_conditions.append("AUTHORIZATION_NAME LIKE ?")
            params.append(filter_name.upper())
        
        if only_active:
            where_conditions.append("STATUS = '*ENABLED'")
        
        where_clause = ""
        if where_conditions:
            where_clause = "WHERE " + " AND ".join(where_conditions)
        
        sql = f"""
            SELECT 
                AUTHORIZATION_NAME,
                USER_CLASS_NAME,
                STATUS,
                PREVIOUS_SIGNON,
                SIGN_ON_ATTEMPTS_NOT_VALID,
                GROUP_PROFILE_NAME,
                SPECIAL_AUTHORITIES,
                TEXT_DESCRIPTION
            FROM QSYS2.USER_INFO
            {where_clause}
            ORDER BY AUTHORIZATION_NAME
        """
        
        cursor = self.conn.execute(sql, tuple(params) if params else ())
        
        for row in cursor.fetchall():
            # Determine account status
            status = row[2] if row[2] else "*UNKNOWN"
            signon_attempts = row[4] if row[4] is not None else 0
            
            # Build status description
            status_desc = []
            if status == "*ENABLED":
                status_desc.append("Active")
            elif status == "*DISABLED":
                status_desc.append("Disabled")
            
            if signon_attempts > 0:
                status_desc.append(f"Failed Logins: {signon_attempts}")
            
            user_info = {
                "username": row[0],
                "user_class": row[1] if row[1] else "*NONE",
                "status": status,
                "status_description": ", ".join(status_desc) if status_desc else "Unknown",
                "last_signon": row[3],
                "failed_signon_attempts": signon_attempts,
                "group_profile": row[5] if row[5] else "*NONE",
                "special_authorities": row[6] if row[6] else "",
                "description": row[7] if row[7] else ""
            }
            users.append(user_info)
        
        cursor.close()
        return users
    
    def list_permissions(self, username: str, library: str | None = None) -> dict[str, Any]:
        """List user permissions and authorities."""
        result = {
            "user": username.upper(),
            "object_authorities": []
        }
        
        # Get user info
        sql = """
            SELECT 
                USER_CLASS_NAME,
                GROUP_PROFILE_NAME,
                SPECIAL_AUTHORITIES
            FROM QSYS2.USER_INFO
            WHERE AUTHORIZATION_NAME = ?
        """
        cursor = self.conn.execute(sql, (username.upper(),))
        row = cursor.fetchone()
        cursor.close()
        
        if row:
            result["user_class"] = row[0]
            result["group_profile"] = row[1]
            # Parse special authorities
            spec_auths = row[2] if row[2] else ""
            result["special_authorities"] = [a.strip() for a in spec_auths.split() if a.strip()]
        
        # Get object authorities using OBJECT_STATISTICS
        lib_filter = library.upper() if library else "*ALL"
        
        perm_sql = """
            SELECT *
            FROM TABLE(QSYS2.OBJECT_STATISTICS(?, 'FILE', '*ALL'))
        """
        cursor = self.conn.execute(perm_sql, (lib_filter,))
        for row in cursor.fetchall():
            result["object_authorities"].append({
                "library": library.upper() if library else "*ALL",
                "object": str(row[0]) if row[0] else "",  # OBJNAME
                "object_type": str(row[1]) if row[1] else "*FILE",  # OBJTYPE
                "authority": "*CHANGE"  # Default for accessible objects
            })
        cursor.close()
        
        return result
