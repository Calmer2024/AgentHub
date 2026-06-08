ALTER TABLE agent_configs ADD COLUMN rules TEXT DEFAULT '' NOT NULL;

UPDATE agent_configs
SET rules = ''
WHERE rules IS NULL;
