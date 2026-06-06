ALTER TABLE sessions ADD COLUMN is_pinned VARCHAR NOT NULL DEFAULT '0';
ALTER TABLE sessions ADD COLUMN archived_at DATETIME;

CREATE INDEX IF NOT EXISTS idx_sessions_project_pinned_updated
ON sessions(project_id, is_active, archived_at, is_pinned, updated_at);
