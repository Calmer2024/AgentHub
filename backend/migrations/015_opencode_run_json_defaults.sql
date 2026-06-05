UPDATE agent_configs
SET init_args = '["run", "--pure", "--agent", "build", "--format", "json", "--dangerously-skip-permissions"]'
WHERE cli_tool = 'opencode'
  AND init_args IN (
    '["--no-color", "--plain"]',
    '["run", "--format", "json"]',
    '["run", "--format", "json", "--dangerously-skip-permissions"]'
  );
