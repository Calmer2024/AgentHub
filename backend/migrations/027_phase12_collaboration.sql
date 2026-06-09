CREATE TABLE IF NOT EXISTS comments (
    id VARCHAR PRIMARY KEY,
    project_id VARCHAR NOT NULL REFERENCES projects(id),
    target_type VARCHAR NOT NULL,
    target_id VARCHAR NOT NULL,
    author_user_id VARCHAR NOT NULL REFERENCES users(id),
    body TEXT NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_comments_target ON comments(project_id, target_type, target_id, created_at);

CREATE TABLE IF NOT EXISTS attachments (
    id VARCHAR PRIMARY KEY,
    project_id VARCHAR NOT NULL REFERENCES projects(id),
    session_id VARCHAR REFERENCES sessions(id),
    uploaded_by VARCHAR NOT NULL REFERENCES users(id),
    filename VARCHAR NOT NULL,
    mime_type VARCHAR NOT NULL,
    size_bytes INTEGER NOT NULL,
    storage_uri TEXT NOT NULL,
    created_at DATETIME NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_attachments_project_session ON attachments(project_id, session_id, created_at);

CREATE TABLE IF NOT EXISTS artifact_references (
    id VARCHAR PRIMARY KEY,
    source_type VARCHAR NOT NULL,
    source_id VARCHAR NOT NULL,
    artifact_id VARCHAR NOT NULL REFERENCES artifacts(id),
    artifact_version_id VARCHAR,
    relation VARCHAR NOT NULL,
    created_at DATETIME NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_artifact_references_source ON artifact_references(source_type, source_id);

CREATE TABLE IF NOT EXISTS notifications (
    id VARCHAR PRIMARY KEY,
    user_id VARCHAR NOT NULL REFERENCES users(id),
    type VARCHAR NOT NULL,
    resource_type VARCHAR NOT NULL,
    resource_id VARCHAR NOT NULL,
    title VARCHAR NOT NULL,
    body TEXT,
    read_at DATETIME,
    created_at DATETIME NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_notifications_user_read ON notifications(user_id, read_at, created_at);

CREATE TABLE IF NOT EXISTS agent_template_sessions (
    id VARCHAR PRIMARY KEY,
    created_by VARCHAR NOT NULL REFERENCES users(id),
    status VARCHAR NOT NULL,
    draft_json TEXT NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
);

CREATE TABLE IF NOT EXISTS git_sync_jobs (
    id VARCHAR PRIMARY KEY,
    project_id VARCHAR NOT NULL REFERENCES projects(id),
    mode VARCHAR NOT NULL,
    remote TEXT NOT NULL,
    branch VARCHAR NOT NULL,
    status VARCHAR NOT NULL,
    commit_sha VARCHAR,
    error_summary TEXT,
    logs_json TEXT NOT NULL DEFAULT '[]',
    created_at DATETIME NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_git_sync_jobs_project_created ON git_sync_jobs(project_id, created_at);
