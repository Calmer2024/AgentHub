CREATE TABLE IF NOT EXISTS build_runs (
    id VARCHAR PRIMARY KEY,
    project_id VARCHAR NOT NULL REFERENCES projects(id),
    status VARCHAR NOT NULL,
    command TEXT NOT NULL,
    install_command TEXT,
    artifact_path TEXT,
    exit_code INTEGER,
    error_summary TEXT,
    started_at DATETIME,
    finished_at DATETIME,
    created_at DATETIME NOT NULL
);

CREATE TABLE IF NOT EXISTS build_logs (
    id VARCHAR PRIMARY KEY,
    build_id VARCHAR NOT NULL REFERENCES build_runs(id),
    sequence INTEGER NOT NULL,
    stream VARCHAR NOT NULL,
    text TEXT NOT NULL,
    created_at DATETIME NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_build_runs_project_status ON build_runs(project_id, status);
CREATE INDEX IF NOT EXISTS idx_build_logs_build_sequence ON build_logs(build_id, sequence);

CREATE TABLE IF NOT EXISTS context_pack_snapshots (
    id VARCHAR PRIMARY KEY,
    session_id VARCHAR NOT NULL REFERENCES sessions(id),
    purpose VARCHAR NOT NULL,
    payload_json TEXT NOT NULL,
    created_at DATETIME NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_context_pack_session_purpose ON context_pack_snapshots(session_id, purpose);

CREATE TABLE IF NOT EXISTS orchestrator_plans (
    id VARCHAR PRIMARY KEY,
    session_id VARCHAR NOT NULL REFERENCES sessions(id),
    status VARCHAR NOT NULL,
    steps_json TEXT NOT NULL,
    current_step_id VARCHAR,
    run_id VARCHAR REFERENCES runs(id),
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_orchestrator_plans_session_status ON orchestrator_plans(session_id, status);
