import os
import sys
import sqlite3
import threading
import logging
from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Ensure replica-msdk can be imported
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    stream=sys.stdout,
    force=True
)
logger = logging.getLogger("gs_vercount.main")

try:
    from backend.shared import (
        get_db,
        get_gluesync_client,
        get_all_cached_statuses,
        get_all_agent_health,
        init_comparison_tables,
        REPORTS_DIR,
        METRICS_DB_PATH,
    )
    from backend.verify_wss import router as verify_wss_router
except ModuleNotFoundError:
    from shared import (
        get_db,
        get_gluesync_client,
        get_all_cached_statuses,
        get_all_agent_health,
        init_comparison_tables,
        REPORTS_DIR,
        METRICS_DB_PATH,
    )
    from verify_wss import router as verify_wss_router

app = FastAPI(title="GS-VerCount Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static reports directory
os.makedirs(REPORTS_DIR, exist_ok=True)
app.mount("/reports", StaticFiles(directory=REPORTS_DIR), name="reports")

# Include verify router
app.include_router(verify_wss_router)

def init_metrics_db():
    """Initialize the SQLite database schema on startup."""
    os.makedirs(os.path.dirname(METRICS_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(METRICS_DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ws_metrics (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            captured_at TEXT NOT NULL,
            pipeline_id TEXT NOT NULL,
            entity_name TEXT NOT NULL,
            inserts     INTEGER DEFAULT 0,
            updates     INTEGER DEFAULT 0,
            deletes     INTEGER DEFAULT 0,
            total_ops   INTEGER DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS entity_status_cache (
            pipeline_id TEXT NOT NULL,
            entity_name TEXT NOT NULL,
            status      TEXT NOT NULL,
            updated_at  TEXT NOT NULL,
            PRIMARY KEY (pipeline_id, entity_name)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS agent_health_cache (
            pipeline_id       TEXT NOT NULL,
            agent_id          TEXT NOT NULL,
            agent_type        TEXT,
            connection_status TEXT NOT NULL,
            health_status     TEXT NOT NULL,
            connected_db_host TEXT,
            connected_db_name TEXT,
            connection_error  TEXT,
            updated_at        TEXT NOT NULL,
            PRIMARY KEY (pipeline_id, agent_id)
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_entity_time
        ON ws_metrics(entity_name, captured_at)
    """)
    
    # Scheduler & Profiling System Tables
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scheduler_settings (
            key   TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS report_profiles (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            name              TEXT NOT NULL,
            pipeline_id       TEXT NOT NULL,
            entities          TEXT NOT NULL, -- JSON array of entity names
            skip_if_all_pass  INTEGER DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mailer_profiles (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT NOT NULL,
            emails        TEXT NOT NULL, -- Comma-separated
            subject       TEXT NOT NULL,
            body_header   TEXT,
            body_ending   TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scheduler_jobs (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            name              TEXT NOT NULL,
            pipeline_id       TEXT NOT NULL,
            cron_expression   TEXT NOT NULL,
            report_profile_id INTEGER,
            mailer_profile_id INTEGER,
            enabled           INTEGER DEFAULT 1,
            FOREIGN KEY(report_profile_id) REFERENCES report_profiles(id),
            FOREIGN KEY(mailer_profile_id) REFERENCES mailer_profiles(id)
        )
    """)
    
    # Set default global log path (internal container path)
    conn.execute("""
        INSERT OR IGNORE INTO scheduler_settings (key, value)
        VALUES ('log_path', '/app/gs-vercount/logs/scheduler.log')
    """)
    conn.commit()
    conn.close()

# Initialize schemas on startup
init_metrics_db()
init_comparison_tables()

# Serve UI at / and /tool
_ui_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

@app.get("/", include_in_schema=False)
@app.get("/tool", include_in_schema=False)
def serve_dashboard():
    html_path = os.path.join(_ui_dir, "index.html")
    if os.path.exists(html_path):
        return FileResponse(html_path, media_type="text/html")
    raise HTTPException(status_code=404, detail="index.html not found")

@app.get("/api/pipelines")
def get_pipelines():
    try:
        client = get_gluesync_client()
        pipelines = client.list_pipelines()
        normalized = []
        for p in (pipelines if isinstance(pipelines, list) else []):
            if isinstance(p, dict):
                p.setdefault('pipelineId', p.get('id', ''))
                p.setdefault('name', p.get('pipelineName', p.get('id', '')))
            normalized.append(p)
        return normalized
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/pipelines/{pipeline_id}/entities")
def get_entities(pipeline_id: str):
    try:
        client = get_gluesync_client()
        entities = client.list_entities(pipeline_id)
        
        try:
            groups = client.list_groups(pipeline_id)
            group_name_map = {}
            for g in (groups if isinstance(groups, list) else []):
                gid = g.get('groupId') or g.get('id')
                gname = g.get('groupName') or g.get('name') or gid
                if gid:
                    group_name_map[gid] = gname
        except Exception:
            group_name_map = {}

        cached_statuses = get_all_cached_statuses(pipeline_id)
        agent_health_list = get_all_agent_health(pipeline_id)
        agent_health_map = {ah['agent_id']: ah for ah in agent_health_list}
        
        try:
            agents_config = client.list_agents(pipeline_id)
        except:
            agents_config = []
        src_agent_id = next((a['agentId'] for a in agents_config if a.get('agentType') == 'SOURCE'), None)
        tgt_agent_id = next((a['agentId'] for a in agents_config if a.get('agentType') == 'TARGET'), None)
        
        tgt_health = agent_health_map.get(tgt_agent_id, {}) if tgt_agent_id else {}
        src_health = agent_health_map.get(src_agent_id, {}) if src_agent_id else {}
        
        for ent in (entities or []):
            if isinstance(ent, dict):
                name = ent.get('entityName')
                gid = ent.get('groupId')
                ent['groupName'] = group_name_map.get(gid, gid or 'default')

                if name in cached_statuses:
                    ent['status'] = cached_statuses[name]
                else:
                    ent['status'] = 'STOPPED'

                ent['targetAgentHealth'] = {
                    'connectionStatus': tgt_health.get('connection_status', 'UNKNOWN'),
                    'healthStatus': tgt_health.get('health_status', 'UNKNOWN'),
                    'connectedDbHost': tgt_health.get('connected_db_host'),
                    'connectedDbName': tgt_health.get('connected_db_name'),
                    'connectionError': tgt_health.get('connection_error'),
                    'updatedAt': tgt_health.get('updated_at'),
                } if tgt_health else None
                ent['sourceAgentHealth'] = {
                    'connectionStatus': src_health.get('connection_status', 'UNKNOWN'),
                    'healthStatus': src_health.get('health_status', 'UNKNOWN'),
                    'connectedDbHost': src_health.get('connected_db_host'),
                    'connectedDbName': src_health.get('connected_db_name'),
                    'connectionError': src_health.get('connection_error'),
                    'updatedAt': src_health.get('updated_at'),
                } if src_health else None
        
        return entities
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8083, reload=True)
