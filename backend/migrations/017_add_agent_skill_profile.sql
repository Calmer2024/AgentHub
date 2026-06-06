ALTER TABLE agent_configs ADD COLUMN primary_skill VARCHAR DEFAULT 'general_coding' NOT NULL;
ALTER TABLE agent_configs ADD COLUMN auxiliary_skills TEXT DEFAULT '[]' NOT NULL;
ALTER TABLE agent_configs ADD COLUMN context_policy VARCHAR DEFAULT 'workspace_coding' NOT NULL;

UPDATE agent_configs
SET
    primary_skill = CASE
        WHEN COALESCE(primary_skill, '') = '' THEN 'general_coding'
        ELSE primary_skill
    END,
    auxiliary_skills = CASE
        WHEN COALESCE(auxiliary_skills, '') = '' THEN '[]'
        ELSE auxiliary_skills
    END,
    context_policy = CASE
        WHEN COALESCE(context_policy, '') = '' THEN 'workspace_coding'
        ELSE context_policy
    END;
