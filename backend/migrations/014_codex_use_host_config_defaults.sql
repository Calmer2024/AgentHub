UPDATE agent_configs
SET init_args = '["exec", "--skip-git-repo-check", "--dangerously-bypass-approvals-and-sandbox", "--color", "never", "--json", "-"]'
WHERE cli_tool = 'codex'
  AND init_args IN (
    '["exec", "--ignore-user-config", "--skip-git-repo-check", "--sandbox", "workspace-write", "--dangerously-bypass-approvals-and-sandbox", "--color", "never", "--json", "-"]',
    '["exec", "--skip-git-repo-check", "--sandbox", "workspace-write", "--dangerously-bypass-approvals-and-sandbox", "--color", "never", "--json", "-"]',
    '["exec", "--ask-for-approval", "never", "--skip-git-repo-check", "--sandbox", "workspace-write", "--color", "never", "--json", "-"]',
    '["--ask-for-approval", "never", "exec", "--skip-git-repo-check", "--sandbox", "workspace-write", "--color", "never", "--json"]'
  );
