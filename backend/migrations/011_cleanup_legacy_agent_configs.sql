UPDATE agent_configs
SET is_active = 0
WHERE is_active = 1
  AND (
    COALESCE(agent_type, '') <> 'cli_wrapper'
    OR (
      COALESCE(cli_tool, 'custom') = 'custom'
      AND COALESCE(executable, '') = ''
      AND name NOT IN ('Claude Code', 'Codex', 'OpenCode')
    )
  );

UPDATE agent_configs
SET system_prompt = ''
WHERE system_prompt = '你是一个有帮助的 AI 助手。';

UPDATE agent_configs
SET env_vars = '{}'
WHERE UPPER(COALESCE(env_vars, '')) LIKE '%API_KEY%';
