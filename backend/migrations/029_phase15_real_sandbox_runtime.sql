CREATE TABLE IF NOT EXISTS runner_nodes (
  id VARCHAR PRIMARY KEY,
  provider VARCHAR NOT NULL,
  region VARCHAR,
  status VARCHAR NOT NULL,
  capacity_json TEXT NOT NULL DEFAULT '{}',
  last_heartbeat_at DATETIME,
  created_at DATETIME NOT NULL
);

CREATE TABLE IF NOT EXISTS workspace_volumes (
  id VARCHAR PRIMARY KEY,
  workspace_id VARCHAR NOT NULL REFERENCES workspaces(id),
  storage_provider VARCHAR NOT NULL,
  storage_uri TEXT NOT NULL,
  status VARCHAR NOT NULL,
  last_synced_at DATETIME,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_workspace_volumes_workspace_id ON workspace_volumes(workspace_id);
CREATE INDEX IF NOT EXISTS idx_runner_nodes_provider_status ON runner_nodes(provider, status);

ALTER TABLE sandboxes ADD COLUMN provider VARCHAR;
ALTER TABLE sandboxes ADD COLUMN external_id VARCHAR;
ALTER TABLE sandboxes ADD COLUMN region VARCHAR;
ALTER TABLE sandboxes ADD COLUMN disposed_at DATETIME;

ALTER TABLE runtime_runs ADD COLUMN queued_at DATETIME;
ALTER TABLE runtime_runs ADD COLUMN sync_completed_at DATETIME;
