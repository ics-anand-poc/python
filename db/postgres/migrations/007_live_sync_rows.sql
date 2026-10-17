-- One-way copy TalentScope_DB_Live -> app database (scripts/sync-live-to-dev.ts).
-- SHA-256 of each Live row as it was last copied, so only rows that change in Live are copied again
-- and rows the app edits itself are otherwise left alone.
CREATE TABLE IF NOT EXISTS public.__live_sync_rows (
    table_name VARCHAR(64)  NOT NULL,
    row_key    VARCHAR(200) NOT NULL,
    row_hash   BYTEA NOT NULL,
    synced_at  TIMESTAMP     NOT NULL CONSTRAINT DF___live_sync_rows_synced_at DEFAULT (CURRENT_TIMESTAMP),
    CONSTRAINT PK___live_sync_rows PRIMARY KEY (table_name, row_key)
  );

