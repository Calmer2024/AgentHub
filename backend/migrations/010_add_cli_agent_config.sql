ALTER TABLE agent_configs ADD COLUMN agent_type VARCHAR DEFAULT 'cli_wrapper' NOT NULL;
ALTER TABLE agent_configs ADD COLUMN cli_tool VARCHAR DEFAULT 'custom' NOT NULL;
ALTER TABLE agent_configs ADD COLUMN executable VARCHAR;
ALTER TABLE agent_configs ADD COLUMN init_args TEXT DEFAULT '[]' NOT NULL;
ALTER TABLE agent_configs ADD COLUMN env_vars TEXT DEFAULT '{}' NOT NULL;
