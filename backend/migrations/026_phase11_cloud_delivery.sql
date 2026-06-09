CREATE TABLE IF NOT EXISTS preview_sessions (
    id VARCHAR PRIMARY KEY,
    artifact_id VARCHAR NOT NULL REFERENCES artifacts(id),
    artifact_version_id VARCHAR,
    workspace_id VARCHAR NOT NULL REFERENCES workspaces(id),
    source VARCHAR NOT NULL,
    status VARCHAR NOT NULL,
    url TEXT NOT NULL,
    visibility VARCHAR NOT NULL,
    auth_token VARCHAR,
    expires_at DATETIME,
    created_by VARCHAR REFERENCES users(id),
    created_at DATETIME NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_preview_sessions_artifact ON preview_sessions(artifact_id, status);
CREATE INDEX IF NOT EXISTS idx_preview_sessions_workspace ON preview_sessions(workspace_id);

CREATE TABLE IF NOT EXISTS deployments (
    id VARCHAR PRIMARY KEY,
    artifact_id VARCHAR NOT NULL REFERENCES artifacts(id),
    artifact_version_id VARCHAR NOT NULL,
    project_id VARCHAR NOT NULL REFERENCES projects(id),
    target VARCHAR NOT NULL,
    visibility VARCHAR NOT NULL,
    status VARCHAR NOT NULL,
    stage VARCHAR NOT NULL,
    url TEXT,
    error_summary TEXT,
    created_by VARCHAR REFERENCES users(id),
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_deployments_artifact_version ON deployments(artifact_id, artifact_version_id, status);
CREATE INDEX IF NOT EXISTS idx_deployments_project ON deployments(project_id, created_at);

CREATE TABLE IF NOT EXISTS deployment_logs (
    id VARCHAR PRIMARY KEY,
    deployment_id VARCHAR NOT NULL REFERENCES deployments(id),
    sequence INTEGER NOT NULL,
    stream VARCHAR NOT NULL,
    text TEXT NOT NULL,
    created_at DATETIME NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_deployment_logs_deployment_sequence ON deployment_logs(deployment_id, sequence);
