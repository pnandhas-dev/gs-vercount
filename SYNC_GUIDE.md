# Sync Guide: Updating gs-vercount from replica-mon

This document outlines the file mappings and custom overrides between the parent repository `replica-mon` and the standalone `gs-vercount` sibling repository. Use this checklist and guide to quickly propagate updates from `replica-mon` to `gs-vercount` without scanning unrelated files.

---

## 1. Directory & File Mapping

When copying updates from `replica-mon` to `gs-vercount`, map them as follows:

| Source File/Folder (`replica-mon/`) | Destination in `gs-vercount/` | Purpose / Handling |
| :--- | :--- | :--- |
| `replica_msdk/` | `replica_msdk/` | Core SDK code (Copy completely) |
| `verify_wss.py` | `gs-vercount/verify_wss.py` | Scheduler daemon entrypoint (Copy, keeping port overrides) |
| `backend/main.py` | `gs-vercount/backend/main.py` | API server (Merge count/scheduler/report endpoints; exclude performance/lag endpoints) |
| `backend/shared.py` | `gs-vercount/backend/shared.py` | Shared utils (Keep custom connection path config override) |
| `index.html` | `gs-vercount/index.html` | Frontend UI (Exclude replication status, lag tables; keep only counts, reports, and settings tabs) |

---

## 2. Core Customizations in `gs-vercount`

When syncing, protect the following overrides in `gs-vercount` to avoid breaking standalone deployments:

### A. Connection Config Path (`gs-vercount/backend/shared.py`)
In `replica-mon`, connection paths point to the external host `qadmcli`. In `gs-vercount`, it is redirected internally:
```python
# Look for connection.yaml under local gs-vercount config
CONFIG_DIR = os.getenv("CONFIG_DIR", os.path.join(os.path.dirname(__file__), "..", "config"))
CONFIG_PATH = os.path.join(CONFIG_DIR, "connection.yaml")
```

### B. Port Binding (`gs-vercount/verify_wss.py` & `Containerfile`)
- The FastAPI server and WebSocket listeners bind to port **`8083`** instead of `8080`.
- Keep the default entrypoint and WebSocket connection scripts on `8083`.

### C. Cleaned-Up Frontend UI (`gs-vercount/index.html`)
- Remove all tabs/UI panels related to:
  - Replication lag monitoring
  - Throughput graphs
  - Table offsets
- Retain only:
  - **Reconciliation/Verify** panel
  - **Report History** panel
  - **Scheduler Configuration** (mailer profiles, report profiles, and cron jobs)

---

## 3. Sync/Copy Command Snippets

To sync core SDK code changes from the parent workspace:
```bash
# Run from workspace root to sync libraries:
rsync -av --delete _qoder/replica-mon/replica_msdk/ _qoder/gs-vercount/replica_msdk/
rsync -av --delete --exclude='.git' _qoder/qadmcli/ _qoder/gs-vercount/qadmcli/
```

---

## 4. Tracked Dependency Library Versions

These are the reference git commit hashes from the original packages that were copied into this standalone directory. Use them to run `git diff` or compare changes in the parent projects:

*   **`qadmcli` Library**:
    *   **Original Commit**: `b448551f2d9ad68d7e05dd7c21503ac486c6b21b` (2026-06-03)
    *   **Description**: `fix: agent delegation for connection testing + CLI performance improvements`
*   **`replica_msdk` Library** (extracted from `replica-mon` repo):
    *   **Original Commit**: `ea39c3ec3037901f08ce9d6b5057449f9bcdcbe8` (2026-06-03)
    *   **Description**: `Implement backend-driven report history filtering with wildcard and exclusion support`

