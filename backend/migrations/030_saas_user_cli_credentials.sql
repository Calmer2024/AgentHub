ALTER TABLE users ADD COLUMN username VARCHAR;
ALTER TABLE users ADD COLUMN password_hash TEXT;
ALTER TABLE users ADD COLUMN updated_at DATETIME;

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username ON users(username);

CREATE TABLE IF NOT EXISTS cli_credential_configs (
  id VARCHAR PRIMARY KEY,
  scope VARCHAR NOT NULL,
  owner_id VARCHAR NOT NULL,
  cli_tool VARCHAR NOT NULL,
  provider_type VARCHAR NOT NULL,
  provider_id VARCHAR NOT NULL,
  provider_name VARCHAR NOT NULL,
  base_url TEXT,
  model VARCHAR,
  auth_env_key VARCHAR NOT NULL,
  secret_names_json TEXT NOT NULL DEFAULT '[]',
  config_json TEXT NOT NULL DEFAULT '{}',
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  UNIQUE(scope, owner_id, cli_tool)
);

CREATE INDEX IF NOT EXISTS idx_cli_credential_scope_owner ON cli_credential_configs(scope, owner_id);
