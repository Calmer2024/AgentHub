CREATE TABLE IF NOT EXISTS users (
    id VARCHAR PRIMARY KEY,
    email VARCHAR NOT NULL UNIQUE,
    display_name VARCHAR NOT NULL,
    avatar_url TEXT,
    created_at DATETIME NOT NULL
);

CREATE TABLE IF NOT EXISTS teams (
    id VARCHAR PRIMARY KEY,
    name VARCHAR NOT NULL UNIQUE,
    created_by VARCHAR NOT NULL REFERENCES users(id),
    created_at DATETIME NOT NULL
);

CREATE TABLE IF NOT EXISTS team_members (
    id VARCHAR PRIMARY KEY,
    team_id VARCHAR NOT NULL REFERENCES teams(id),
    user_id VARCHAR NOT NULL REFERENCES users(id),
    role VARCHAR NOT NULL,
    created_at DATETIME NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_team_members_team_user ON team_members(team_id, user_id);

ALTER TABLE projects ADD COLUMN workspace_mode VARCHAR NOT NULL DEFAULT 'local';
ALTER TABLE projects ADD COLUMN team_id VARCHAR REFERENCES teams(id);
ALTER TABLE projects ADD COLUMN owner_user_id VARCHAR REFERENCES users(id);

CREATE TABLE IF NOT EXISTS workspaces (
    id VARCHAR PRIMARY KEY,
    project_id VARCHAR NOT NULL REFERENCES projects(id),
    provider VARCHAR NOT NULL,
    status VARCHAR NOT NULL,
    storage_uri TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_workspaces_project_provider ON workspaces(project_id, provider);

ALTER TABLE projects ADD COLUMN workspace_id VARCHAR REFERENCES workspaces(id);

CREATE TABLE IF NOT EXISTS workspace_snapshots (
    id VARCHAR PRIMARY KEY,
    workspace_id VARCHAR NOT NULL REFERENCES workspaces(id),
    label VARCHAR,
    storage_uri TEXT NOT NULL,
    created_by VARCHAR REFERENCES users(id),
    created_at DATETIME NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_workspace_snapshots_workspace_created ON workspace_snapshots(workspace_id, created_at);

CREATE TABLE IF NOT EXISTS workspace_imports (
    id VARCHAR PRIMARY KEY,
    workspace_id VARCHAR NOT NULL REFERENCES workspaces(id),
    source VARCHAR NOT NULL,
    status VARCHAR NOT NULL,
    detail TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_by VARCHAR REFERENCES users(id),
    created_at DATETIME NOT NULL,
    completed_at DATETIME
);

CREATE INDEX IF NOT EXISTS idx_workspace_imports_workspace_created ON workspace_imports(workspace_id, created_at);

CREATE TABLE IF NOT EXISTS workspace_restores (
    id VARCHAR PRIMARY KEY,
    workspace_id VARCHAR NOT NULL REFERENCES workspaces(id),
    snapshot_id VARCHAR NOT NULL REFERENCES workspace_snapshots(id),
    strategy VARCHAR NOT NULL,
    status VARCHAR NOT NULL,
    created_by VARCHAR REFERENCES users(id),
    created_at DATETIME NOT NULL,
    completed_at DATETIME
);

CREATE INDEX IF NOT EXISTS idx_workspace_restores_workspace_created ON workspace_restores(workspace_id, created_at);

CREATE TABLE IF NOT EXISTS audit_logs (
    id VARCHAR PRIMARY KEY,
    actor_user_id VARCHAR REFERENCES users(id),
    team_id VARCHAR REFERENCES teams(id),
    project_id VARCHAR REFERENCES projects(id),
    action VARCHAR NOT NULL,
    resource_type VARCHAR NOT NULL,
    resource_id VARCHAR NOT NULL,
    metadata_json TEXT NOT NULL,
    created_at DATETIME NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_project_created ON audit_logs(project_id, created_at);
CREATE INDEX IF NOT EXISTS idx_audit_logs_team_created ON audit_logs(team_id, created_at);
