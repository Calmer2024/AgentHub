ALTER TABLE messages ADD COLUMN content_type VARCHAR DEFAULT 'text';
ALTER TABLE messages ADD COLUMN source_type VARCHAR DEFAULT 'agent';
ALTER TABLE messages ADD COLUMN source_id VARCHAR;
ALTER TABLE messages ADD COLUMN source_name VARCHAR;
ALTER TABLE messages ADD COLUMN metadata_json TEXT;
UPDATE messages
SET source_type = CASE
    WHEN role = 'user' THEN 'user'
    WHEN agent_name IS NOT NULL AND agent_name != '' THEN 'agent'
    ELSE 'assistant'
END,
source_name = CASE
    WHEN role = 'user' THEN '用户'
    WHEN agent_name IS NOT NULL AND agent_name != '' THEN agent_name
    ELSE source_name
END
WHERE source_type IS NULL OR source_type = 'agent';
