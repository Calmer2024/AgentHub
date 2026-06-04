CREATE TABLE IF NOT EXISTS projects (
    id VARCHAR PRIMARY KEY,
    name VARCHAR NOT NULL,
    workspace_path VARCHAR NOT NULL UNIQUE,
    project_type VARCHAR DEFAULT 'existing',
    status VARCHAR DEFAULT 'creating',
    metadata_json TEXT DEFAULT '{}',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE sessions ADD COLUMN project_id VARCHAR REFERENCES projects(id);

ALTER TABLE artifacts ADD COLUMN project_id VARCHAR REFERENCES projects(id);
ALTER TABLE artifacts ADD COLUMN file_path VARCHAR;
ALTER TABLE artifacts ADD COLUMN preview_id VARCHAR;
ALTER TABLE artifacts ADD COLUMN source VARCHAR;
ALTER TABLE artifacts ADD COLUMN confidence VARCHAR;
ALTER TABLE artifacts ADD COLUMN task_id VARCHAR;
