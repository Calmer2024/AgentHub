CREATE TABLE IF NOT EXISTS engine_sessions (
  id VARCHAR PRIMARY KEY,
  session_id VARCHAR NOT NULL REFERENCES sessions(id),
  agent_config_id VARCHAR NOT NULL REFERENCES agent_configs(id),
  cli_tool VARCHAR NOT NULL,
  workspace_path VARCHAR NOT NULL,
  engine_session_id VARCHAR NOT NULL,
  status VARCHAR NOT NULL DEFAULT 'active',
  metadata_json TEXT,
  created_at DATETIME,
  updated_at DATETIME
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_engine_sessions_active_unique
ON engine_sessions(session_id, agent_config_id, cli_tool, workspace_path)
WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_engine_sessions_lookup
ON engine_sessions(session_id, agent_config_id, cli_tool, updated_at);
