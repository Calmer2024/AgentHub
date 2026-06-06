ALTER TABLE sessions ADD COLUMN unread_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE sessions ADD COLUMN last_read_at DATETIME;
ALTER TABLE sessions ADD COLUMN is_muted VARCHAR NOT NULL DEFAULT '0';

CREATE INDEX IF NOT EXISTS idx_sessions_project_unread_updated
ON sessions(project_id, is_active, archived_at, unread_count, updated_at);
