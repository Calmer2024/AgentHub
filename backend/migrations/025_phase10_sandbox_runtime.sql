CREATE TABLE IF NOT EXISTS sandboxes (
    id VARCHAR PRIMARY KEY,
    workspace_id VARCHAR NOT NULL REFERENCES workspaces(id),
    status VARCHAR NOT NULL,
    image VARCHAR NOT NULL,
    runner_node_id VARCHAR,
    resource_limits_json TEXT NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    stopped_at DATETIME
);

CREATE INDEX IF NOT EXISTS idx_sandboxes_workspace_status ON sandboxes(workspace_id, status);

CREATE TABLE IF NOT EXISTS runtime_runs (
    id VARCHAR PRIMARY KEY,
    session_id VARCHAR NOT NULL REFERENCES sessions(id),
    agent_id VARCHAR NOT NULL REFERENCES agent_configs(id),
    sandbox_id VARCHAR REFERENCES sandboxes(id),
    runtime_mode VARCHAR NOT NULL,
    status VARCHAR NOT NULL,
    started_at DATETIME,
    finished_at DATETIME,
    error_summary TEXT
);

CREATE INDEX IF NOT EXISTS idx_runtime_runs_session_status ON runtime_runs(session_id, status);
CREATE INDEX IF NOT EXISTS idx_runtime_runs_sandbox ON runtime_runs(sandbox_id);

CREATE TABLE IF NOT EXISTS runtime_logs (
    id VARCHAR PRIMARY KEY,
    run_id VARCHAR NOT NULL REFERENCES runtime_runs(id),
    sequence INTEGER NOT NULL,
    stream VARCHAR NOT NULL,
    text TEXT NOT NULL,
    created_at DATETIME NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_runtime_logs_run_sequence ON runtime_logs(run_id, sequence);

CREATE TABLE IF NOT EXISTS secrets (
    id VARCHAR PRIMARY KEY,
    scope VARCHAR NOT NULL,
    owner_id VARCHAR NOT NULL,
    name VARCHAR NOT NULL,
    encrypted_value TEXT NOT NULL,
    created_at DATETIME NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_secrets_scope_owner_name ON secrets(scope, owner_id, name);

CREATE TABLE IF NOT EXISTS quota_usages (
    id VARCHAR PRIMARY KEY,
    subject_type VARCHAR NOT NULL,
    subject_id VARCHAR NOT NULL,
    quota_type VARCHAR NOT NULL,
    used INTEGER NOT NULL,
    limit_value INTEGER NOT NULL,
    window_started_at DATETIME NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_quota_usages_subject_type ON quota_usages(subject_type, subject_id, quota_type);
