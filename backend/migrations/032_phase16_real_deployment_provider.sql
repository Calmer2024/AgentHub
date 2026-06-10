CREATE TABLE IF NOT EXISTS deployment_targets (
  id VARCHAR PRIMARY KEY,
  scope VARCHAR NOT NULL,
  owner_id VARCHAR NOT NULL,
  provider VARCHAR NOT NULL,
  name VARCHAR NOT NULL,
  config_json TEXT NOT NULL DEFAULT '{}',
  status VARCHAR NOT NULL DEFAULT 'active',
  created_by VARCHAR REFERENCES users(id),
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL
);

CREATE TABLE IF NOT EXISTS deployment_releases (
  id VARCHAR PRIMARY KEY,
  deployment_id VARCHAR NOT NULL REFERENCES deployments(id),
  artifact_id VARCHAR NOT NULL REFERENCES artifacts(id),
  artifact_version_id VARCHAR NOT NULL,
  target_id VARCHAR NOT NULL REFERENCES deployment_targets(id),
  bundle_uri TEXT NOT NULL,
  public_url TEXT,
  status VARCHAR NOT NULL,
  provider_metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at DATETIME NOT NULL
);

ALTER TABLE deployments ADD COLUMN target_id VARCHAR REFERENCES deployment_targets(id);
ALTER TABLE deployments ADD COLUMN active_release_id VARCHAR;
ALTER TABLE deployments ADD COLUMN provider VARCHAR;
ALTER TABLE deployments ADD COLUMN bundle_uri TEXT;
ALTER TABLE deployments ADD COLUMN provider_metadata_json TEXT NOT NULL DEFAULT '{}';
ALTER TABLE deployments ADD COLUMN published_at DATETIME;
