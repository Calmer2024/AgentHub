CREATE TEMP TABLE agent_config_keep_ids (id VARCHAR PRIMARY KEY);

UPDATE agent_configs
SET
    cli_tool = 'claude_code',
    executable = 'claude',
    init_args = '["-p", "--verbose", "--output-format", "stream-json", "--include-partial-messages", "--dangerously-skip-permissions"]',
    env_vars = '{}',
    agent_type = 'cli_wrapper',
    is_active = 1
WHERE name = 'Claude Code'
  AND COALESCE(executable, '') = '';

UPDATE agent_configs
SET
    cli_tool = 'codex',
    executable = 'codex',
    init_args = '["exec", "--ignore-user-config", "--skip-git-repo-check", "--sandbox", "workspace-write", "--dangerously-bypass-approvals-and-sandbox", "--color", "never", "--json", "-"]',
    env_vars = '{}',
    agent_type = 'cli_wrapper',
    is_active = 1
WHERE name = 'Codex'
  AND COALESCE(executable, '') = '';

UPDATE agent_configs
SET
    cli_tool = 'opencode',
    executable = 'opencode',
    init_args = '["run", "--pure", "--agent", "build", "--format", "json", "--dangerously-skip-permissions"]',
    env_vars = '{}',
    agent_type = 'cli_wrapper',
    is_active = 1
WHERE name = 'OpenCode'
  AND COALESCE(executable, '') = '';

INSERT INTO agent_config_keep_ids (id)
SELECT id
FROM agent_configs
WHERE COALESCE(is_active, 1) = 1
  AND COALESCE(agent_type, 'cli_wrapper') = 'cli_wrapper'
  AND (
    COALESCE(cli_tool, 'custom') IN ('claude_code', 'codex', 'opencode')
    OR COALESCE(executable, '') <> ''
  );

DELETE FROM session_members
WHERE agent_config_id NOT IN (SELECT id FROM agent_config_keep_ids);

UPDATE sessions
SET agent_config_id = NULL
WHERE agent_config_id IS NOT NULL
  AND agent_config_id NOT IN (SELECT id FROM agent_config_keep_ids);

CREATE TABLE agent_configs_cli_only (
    id VARCHAR PRIMARY KEY,
    name VARCHAR NOT NULL,
    description VARCHAR NOT NULL DEFAULT '',
    system_prompt VARCHAR NOT NULL DEFAULT '',
    agent_type VARCHAR NOT NULL DEFAULT 'cli_wrapper',
    cli_tool VARCHAR NOT NULL DEFAULT 'custom',
    executable VARCHAR,
    init_args TEXT NOT NULL DEFAULT '[]',
    env_vars TEXT NOT NULL DEFAULT '{}',
    is_active BOOLEAN NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO agent_configs_cli_only (
    id, name, description, system_prompt, agent_type, cli_tool,
    executable, init_args, env_vars, is_active, created_at, updated_at
)
SELECT
    id,
    COALESCE(name, 'CLI Agent'),
    COALESCE(description, ''),
    COALESCE(NULLIF(system_prompt, '你是一个有帮助的 AI 助手。'), ''),
    'cli_wrapper',
    COALESCE(cli_tool, 'custom'),
    executable,
    COALESCE(init_args, '[]'),
    CASE
        WHEN UPPER(COALESCE(env_vars, '')) LIKE '%API_KEY%' THEN '{}'
        ELSE COALESCE(env_vars, '{}')
    END,
    1,
    COALESCE(created_at, CURRENT_TIMESTAMP),
    COALESCE(updated_at, CURRENT_TIMESTAMP)
FROM agent_configs
WHERE id IN (SELECT id FROM agent_config_keep_ids);

DROP TABLE agent_configs;

ALTER TABLE agent_configs_cli_only RENAME TO agent_configs;

DROP TABLE agent_config_keep_ids;
