ALTER TABLE orchestrator_plans ADD COLUMN normalized_plan_json TEXT NOT NULL DEFAULT '{}';
ALTER TABLE orchestrator_plans ADD COLUMN execution_id VARCHAR;
ALTER TABLE orchestrator_plans ADD COLUMN execution_snapshot_json TEXT NOT NULL DEFAULT '{}';
ALTER TABLE orchestrator_plans ADD COLUMN agent_scope_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE orchestrator_plans ADD COLUMN orchestrator_agent_id VARCHAR REFERENCES agent_configs(id);

CREATE INDEX IF NOT EXISTS ix_orchestrator_plans_execution_id
ON orchestrator_plans(execution_id);
