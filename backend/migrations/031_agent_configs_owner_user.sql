ALTER TABLE agent_configs ADD COLUMN owner_user_id VARCHAR;

CREATE INDEX IF NOT EXISTS idx_agent_configs_owner_active
  ON agent_configs(owner_user_id, is_active);

CREATE INDEX IF NOT EXISTS idx_agent_configs_owner_cli_tool
  ON agent_configs(owner_user_id, cli_tool);
