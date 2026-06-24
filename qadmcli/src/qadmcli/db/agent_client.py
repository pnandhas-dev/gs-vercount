"""AS400 Agent Client - HTTP client for communicating with AS400 Agent."""

import os
import logging
import requests
from typing import Optional

logger = logging.getLogger(__name__)


class AS400AgentClient:
    """HTTP client for AS400 Agent API."""
    
    def __init__(self, agent_url: Optional[str] = None):
        """Initialize agent client.
        
        Args:
            agent_url: Agent URL (auto-detected from QADMCLI_AGENT_URL env var if not provided)
        """
        self.agent_url = agent_url or os.getenv('QADMCLI_AGENT_URL')
        self._available = False
        
        if self.agent_url:
            self._available = self._check_health()
            if self._available:
                logger.info(f"✅ AS400 Agent available at {self.agent_url}")
            else:
                logger.warning(f"⚠️  AS400 Agent at {self.agent_url} is not healthy")
        else:
            logger.debug("No agent URL configured")
    
    def is_available(self) -> bool:
        """Check if agent is available."""
        return self._available
    
    def query(self, sql: str, library: str = "", params: list | None = None) -> dict:
        """Execute a SELECT query via agent and return structured results.
        
        Args:
            sql: SELECT SQL statement
            library: Library name
            params: Optional list of positional parameter values
            
        Returns:
            dict with columns, rows, row_count, execution_time_ms
        """
        if not self._available:
            raise Exception("Agent not available")
        
        payload = {
            "sql": sql,
            "library": library,
        }
        if params:
            payload["params"] = params
        
        try:
            response = requests.post(
                f"{self.agent_url}/sql/query",
                json=payload,
                timeout=60
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                raise Exception(f"Agent error {response.status_code}: {response.text}")
        except requests.exceptions.Timeout:
            raise Exception("Agent query timed out")
        except requests.exceptions.ConnectionError:
            self._available = False
            raise Exception("Lost connection to agent")
    
    def _check_health(self) -> bool:
        """Check agent health."""
        try:
            response = requests.get(f"{self.agent_url}/health", timeout=2)
            return response.status_code == 200
        except Exception as e:
            logger.debug(f"Agent health check failed: {e}")
            return False
    
    def execute(self, sql: str, library: str = "", params: list | None = None) -> dict:
        """Execute a SQL statement (DDL/DML/SELECT) via agent.
        
        Args:
            sql: SQL statement to execute
            library: Library name
            params: Optional list of positional parameter values
            
        Returns:
            dict with status, columns (empty for DML), rows (empty for DML),
            rows_affected (0 for SELECT), execution_time_ms
        """
        if not self._available:
            raise Exception("Agent not available")
        
        payload = {
            "sql": sql,
            "library": library,
        }
        if params:
            payload["params"] = params
        
        try:
            response = requests.post(
                f"{self.agent_url}/sql/execute",
                json=payload,
                timeout=60
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                raise Exception(f"Agent error {response.status_code}: {response.text}")
        except requests.exceptions.Timeout:
            raise Exception("Agent request timed out")
        except requests.exceptions.ConnectionError:
            self._available = False
            raise Exception("Lost connection to agent")
    
    def execute_batch(self, sql: str, params: list, library: str = "") -> dict:
        """Execute batch SQL via agent.
        
        Args:
            sql: SQL statement with ? placeholders
            params: List of parameter dicts, e.g. [{"1": val1, "2": val2}, ...]
            library: Library name
            
        Returns:
            dict with status, rows_affected, execution_time_ms
        """
        if not self._available:
            raise Exception("Agent not available")
        
        payload = {
            "sql": sql,
            "params": params,
            "library": library
        }
        
        try:
            response = requests.post(
                f"{self.agent_url}/sql/batch",
                json=payload,
                timeout=300  # 5 minutes for large batches
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                raise Exception(f"Agent error {response.status_code}: {response.text}")
        except requests.exceptions.Timeout:
            raise Exception("Agent request timed out")
        except requests.exceptions.ConnectionError:
            self._available = False
            raise Exception("Lost connection to agent")
    
    def mockup_insert(self, sql: str, rows: list, library: str) -> dict:
        """Execute bulk insert for mockup.
        
        Args:
            sql: INSERT statement with ? placeholders
            rows: List of row tuples
            library: Library name
            
        Returns:
            dict with status, rows_affected, execution_time_ms
        """
        # Convert rows to params format
        params = []
        for row in rows:
            param_dict = {str(i+1): val for i, val in enumerate(row)}
            params.append(param_dict)
        
        return self.execute_batch(sql, params, library)
    
    def mockup_update(self, sql: str, updates: list, library: str) -> dict:
        """Execute bulk update for mockup.
        
        Args:
            sql: UPDATE statement with ? placeholders
            updates: List of update dicts
            library: Library name
            
        Returns:
            dict with status, rows_affected, execution_time_ms
        """
        return self.execute_batch(sql, updates, library)
    
    def mockup_delete(self, sql: str, ids: list, library: str) -> dict:
        """Execute bulk delete for mockup.
        
        Args:
            sql: DELETE statement with ? placeholder for ID
            ids: List of ID values
            library: Library name
            
        Returns:
            dict with status, rows_affected, execution_time_ms
        """
        params = [{"1": pk} for pk in ids]
        return self.execute_batch(sql, params, library)
