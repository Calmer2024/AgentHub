ALTER TABLE runtime_runs ADD COLUMN actor_user_id VARCHAR REFERENCES users(id);

ALTER TABLE sandboxes ADD COLUMN actor_user_id VARCHAR REFERENCES users(id);

UPDATE runtime_runs
SET actor_user_id = (
    SELECT projects.owner_user_id
    FROM sessions
    JOIN projects ON projects.id = sessions.project_id
    WHERE sessions.id = runtime_runs.session_id
)
WHERE actor_user_id IS NULL;

UPDATE sandboxes
SET actor_user_id = (
    SELECT projects.owner_user_id
    FROM workspaces
    JOIN projects ON projects.id = workspaces.project_id
    WHERE workspaces.id = sandboxes.workspace_id
)
WHERE actor_user_id IS NULL;

CREATE INDEX IF NOT EXISTS idx_runtime_runs_actor_status ON runtime_runs(actor_user_id, runtime_mode, status);

CREATE INDEX IF NOT EXISTS idx_sandboxes_actor_status ON sandboxes(actor_user_id, status);
