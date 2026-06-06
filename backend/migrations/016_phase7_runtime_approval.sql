CREATE TABLE IF NOT EXISTS runs (
    id VARCHAR PRIMARY KEY,
    session_id VARCHAR NOT NULL REFERENCES sessions(id),
    project_id VARCHAR REFERENCES projects(id),
    mode VARCHAR NOT NULL,
    status VARCHAR NOT NULL,
    current_message_id VARCHAR REFERENCES messages(id),
    started_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    completed_at DATETIME,
    cancel_reason TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS run_tasks (
    id VARCHAR PRIMARY KEY,
    run_id VARCHAR NOT NULL REFERENCES runs(id),
    session_id VARCHAR NOT NULL REFERENCES sessions(id),
    agent_id VARCHAR REFERENCES agent_configs(id),
    message_id VARCHAR REFERENCES messages(id),
    name VARCHAR NOT NULL,
    role VARCHAR,
    phase INTEGER,
    status VARCHAR NOT NULL,
    depends_on_json TEXT NOT NULL DEFAULT '[]',
    started_at DATETIME,
    completed_at DATETIME,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS run_processes (
    id VARCHAR PRIMARY KEY,
    run_id VARCHAR NOT NULL REFERENCES runs(id),
    task_id VARCHAR REFERENCES run_tasks(id),
    session_id VARCHAR NOT NULL REFERENCES sessions(id),
    agent_id VARCHAR REFERENCES agent_configs(id),
    message_id VARCHAR REFERENCES messages(id),
    process_id VARCHAR NOT NULL,
    pid INTEGER,
    executable VARCHAR,
    cwd VARCHAR,
    status VARCHAR NOT NULL,
    started_at DATETIME NOT NULL,
    completed_at DATETIME,
    exit_code INTEGER
);

CREATE INDEX IF NOT EXISTS idx_runs_session_status ON runs(session_id, status);
CREATE INDEX IF NOT EXISTS idx_run_tasks_run_status ON run_tasks(run_id, status);
CREATE INDEX IF NOT EXISTS idx_run_processes_process_id ON run_processes(process_id);

CREATE TABLE IF NOT EXISTS approval_checkpoints (
    id VARCHAR PRIMARY KEY,
    run_id VARCHAR NOT NULL REFERENCES runs(id),
    task_id VARCHAR NOT NULL REFERENCES run_tasks(id),
    session_id VARCHAR NOT NULL REFERENCES sessions(id),
    message_id VARCHAR REFERENCES messages(id),
    artifact_id VARCHAR REFERENCES artifacts(id),
    artifact_version INTEGER,
    title VARCHAR NOT NULL,
    summary TEXT NOT NULL,
    status VARCHAR NOT NULL,
    reason TEXT,
    created_at DATETIME NOT NULL,
    decided_at DATETIME,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_approval_session_status ON approval_checkpoints(session_id, status);
CREATE INDEX IF NOT EXISTS idx_approval_run_task ON approval_checkpoints(run_id, task_id);
