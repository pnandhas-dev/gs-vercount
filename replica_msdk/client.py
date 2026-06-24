import requests
import sys

class GlueSyncClient:
    def __init__(self, base_url: str, username: str, password: str, verify_ssl: bool = False):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.verify = verify_ssl
        
        # Strip shell/dotenv single/double quotes if present
        if username and (username.startswith("'") or username.startswith('"')) and (username.endswith("'") or username.endswith('"')):
            username = username[1:-1]
        if password and (password.startswith("'") or password.startswith('"')) and (password.endswith("'") or password.endswith('"')):
            password = password[1:-1]

        resp = self.session.post(f"{base_url}/authentication/login",
                                 json={"username": username, "password": password})
        if resp.status_code != 200:
            raise Exception(f"Auth failed: {resp.text}")
        self.token = resp.json()["apiToken"]
    
    def request(self, method: str, path: str, **kwargs):
        url = f"{self.base_url}{path}"
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        return self.session.request(method, url, headers=headers, **kwargs)
    
    def list_pipelines(self):
        resp = self.request("GET", "/pipelines")
        return resp.json() if resp.status_code == 200 else []
    
    def get_pipeline(self, pipeline_id: str):
        resp = self.request("GET", f"/pipelines/{pipeline_id}")
        return resp.json() if resp.status_code == 200 else None
    
    def list_entities(self, pipeline_id: str):
        resp = self.request("GET", f"/pipelines/{pipeline_id}/entities")
        if resp.status_code != 200:
            return []
            
        data = resp.json()
        results = []
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and 'entity' in item:
                    ent = item['entity'].copy()
                    # Inject top-level properties (like status) into the entity dict
                    for k, v in item.items():
                        if k != 'entity':
                            ent[k] = v
                    results.append(ent)
                else:
                    results.append(item)
            return results
        return data
    
    def list_groups(self, pipeline_id: str):
        resp = self.request("GET", f"/pipelines/{pipeline_id}/config/groups")
        return resp.json() if resp.status_code == 200 else []
    
    def list_agents(self, pipeline_id: str):
        resp = self.request("GET", f"/pipelines/{pipeline_id}/agents")
        return resp.json() if resp.status_code == 200 else []
    
    def get_agent(self, pipeline_id: str, agent_id: str):
        pipeline = self.get_pipeline(pipeline_id)
        if pipeline:
            agents = pipeline.get('agents', [])
            for agent in agents:
                if agent.get('agentId') == agent_id:
                    return agent
        for agent_type in ['SOURCE', 'TARGET']:
            resp = self.request("GET", f"/pipelines/{pipeline_id}/agents/{agent_id}?agentType={agent_type}")
            if resp.status_code == 200:
                return resp.json()
        return None
    
    def initialize_agent(self, pipeline_id: str, agent_id: str, agent_type: str):
        resp = self.request("PUT", f"/pipelines/{pipeline_id}/agents/{agent_id}?agentType={agent_type}")
        return resp.status_code in (200, 202)
    
    def configure_agent_credentials(self, pipeline_id: str, agent_id: str, credentials: dict):
        resp = self.request("PUT", f"/pipelines/{pipeline_id}/agents/{agent_id}/config/credentials", json=credentials)
        return resp.status_code in (200, 202), resp.text
    
    def configure_agent_specific(self, pipeline_id: str, agent_id: str, config: dict = None):
        payload = {"configuration": config or {}}
        resp = self.request("PUT", f"/pipelines/{pipeline_id}/agents/{agent_id}/config/specific", json=payload)
        return resp.status_code in (200, 202)
    
    def get_agent_node_info(self, pipeline_id: str, agent_id: str):
        resp = self.request("GET", f"/pipelines/{pipeline_id}/agents/{agent_id}/discovery/node-info")
        return resp.json() if resp.status_code == 200 else None
    
    def get_agent_discovery_schemas(self, pipeline_id: str, agent_id: str):
        resp = self.request("GET", f"/pipelines/{pipeline_id}/agents/{agent_id}/discovery/schemas")
        return resp.json() if resp.status_code == 200 else []
    
    def enter_maintenance_mode(self, pipeline_id: str):
        resp = self.request("POST", f"/pipelines/{pipeline_id}/commands/maintenance/enter")
        return resp.status_code == 202
    
    def exit_maintenance_mode(self, pipeline_id: str):
        resp = self.request("POST", f"/pipelines/{pipeline_id}/commands/maintenance/exit")
        return resp.status_code == 202
    
    def get_entity(self, pipeline_id: str, entity_id: str):
        entities = self.list_entities(pipeline_id)
        for e in entities:
            if e.get('entityId') == entity_id:
                return e
        return None
    
    def delete_pipeline(self, pipeline_id: str):
        resp = self.request("DELETE", f"/pipelines/{pipeline_id}")
        return resp.status_code == 200
    
    def delete_entity(self, pipeline_id: str, entity_id: str):
        payload = {"entities": [entity_id]}
        resp = self.request("DELETE", f"/pipelines/{pipeline_id}/config/entities", json=payload)
        return resp.status_code in [200, 202, 204]
    
    def get_discovery_schemas(self, pipeline_id: str, agent_id: str):
        resp = self.request("GET", f"/pipelines/{pipeline_id}/agents/{agent_id}/discovery/schemas")
        return resp.json() if resp.status_code == 200 else {"schemas": []}
    
    def get_discovery_tables(self, pipeline_id: str, agent_id: str, schema: str):
        resp = self.request("GET", f"/pipelines/{pipeline_id}/agents/{agent_id}/discovery/tables",
                           params={"schema": schema})
        return resp.json() if resp.status_code == 200 else {"tables": []}
    
    def get_discovery_columns(self, pipeline_id: str, agent_id: str, schema: str, table: str):
        resp = self.request("GET", f"/pipelines/{pipeline_id}/agents/{agent_id}/discovery/columns",
                           params={"tableschema": schema, "tablename": table})
        return resp.json() if resp.status_code == 200 else {"columns": [], "keys": []}
    
    def get_udf(self, pipeline_id: str, udf_name: str):
        resp = self.request("GET", f"/pipelines/{pipeline_id}/config/entities/mapping-functions/{udf_name}")
        return resp.json() if resp.status_code == 200 else None

    # Control API wrapper methods based on scheduler module implementation
    def start_entity(self, pipeline_id: str, entity_id: str, with_snapshot: bool = False, snapshot_write_method: str = 'UPSERT'):
        """Start a specific entity in a pipeline"""
        path = f'/pipelines/{pipeline_id}/commands/sync/start'
        params = {
            'entity': entity_id,
            'withSnapshot': 'true' if with_snapshot else 'false',
            'snapshotWriteMethod': snapshot_write_method
        }
        resp = self.request('POST', path, params=params)
        return resp.status_code in (200, 202)

    def stop_entity(self, pipeline_id: str, entity_id: str):
        """Stop a specific entity in a pipeline"""
        path = f'/pipelines/{pipeline_id}/commands/sync/stop'
        params = {'entity': entity_id}
        resp = self.request('POST', path, params=params)
        return resp.status_code in (200, 202)
        
    def resync_entity(self, pipeline_id: str, entity_id: str, snapshot_write_method: str = 'UPSERT'):
        """Trigger a one-time snapshot for a specific entity"""
        path = f'/pipelines/{pipeline_id}/commands/sync/one-time-snapshot'
        params = {
            'entity': entity_id,
            'snapshotWriteMethod': snapshot_write_method
        }
        resp = self.request('POST', path, params=params)
        return resp.status_code in (200, 202)
