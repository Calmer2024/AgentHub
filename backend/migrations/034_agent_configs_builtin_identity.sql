ALTER TABLE agent_configs ADD COLUMN is_builtin BOOLEAN NOT NULL DEFAULT 0;

UPDATE agent_configs
SET is_builtin = 1
WHERE cli_tool IN ('claude_code', 'codex', 'opencode')
  AND name IN ('Claude Code', 'Codex', 'OpenCode')
  AND system_prompt = ''
  AND rules = ''
  AND toolset IN ('[]', '')
  AND avatar IN ('', 'preset:blue');
