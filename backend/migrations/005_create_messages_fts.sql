CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
    content,
    content_rowid='rowid',
    tokenize='unicode61'
);
