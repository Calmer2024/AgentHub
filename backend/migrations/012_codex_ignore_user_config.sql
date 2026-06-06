UPDATE agent_configs
SET init_args = '["exec", "--ignore-user-config", "--skip-git-repo-check", "--sandbox", "workspace-write", "--dangerously-bypass-approvals-and-sandbox", "--color", "never", "--json", "-"]'
WHERE cli_tool = 'codex'
  AND init_args IN (
    '["exec", "--ask-for-approval", "never", "--skip-git-repo-check", "--sandbox", "workspace-write", "--color", "never", "--json", "-"]',
    '["--ask-for-approval", "never", "exec", "--skip-git-repo-check", "--sandbox", "workspace-write", "--color", "never", "--json"]',
    '["exec", "--skip-git-repo-check", "--sandbox", "workspace-write", "--dangerously-bypass-approvals-and-sandbox", "--color", "never", "--json", "-"]'
  );

UPDATE agent_configs
SET env_vars = '{}'
WHERE UPPER(COALESCE(env_vars, '')) LIKE '%API_KEY%';
