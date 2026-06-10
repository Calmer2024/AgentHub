CREATE TABLE IF NOT EXISTS auth_identities (
    id VARCHAR PRIMARY KEY,
    user_id VARCHAR NOT NULL REFERENCES users(id),
    provider VARCHAR NOT NULL,
    subject VARCHAR NOT NULL,
    email VARCHAR,
    created_at DATETIME NOT NULL,
    last_login_at DATETIME,
    UNIQUE(provider, subject)
);

CREATE INDEX IF NOT EXISTS idx_auth_identities_user ON auth_identities(user_id);

CREATE TABLE IF NOT EXISTS auth_sessions (
    id VARCHAR PRIMARY KEY,
    user_id VARCHAR NOT NULL REFERENCES users(id),
    refresh_token_hash TEXT NOT NULL,
    user_agent TEXT,
    ip_hash TEXT,
    expires_at DATETIME NOT NULL,
    revoked_at DATETIME,
    created_at DATETIME NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_auth_sessions_user ON auth_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_refresh_hash ON auth_sessions(refresh_token_hash);

ALTER TABLE users ADD COLUMN status VARCHAR NOT NULL DEFAULT 'active';
ALTER TABLE users ADD COLUMN last_login_at DATETIME;
