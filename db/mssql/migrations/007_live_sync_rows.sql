-- One-way copy TalentScope_DB_Live -> app database (scripts/sync-live-to-dev.ts).
-- SHA-256 of each Live row as it was last copied, so only rows that change in Live are copied again
-- and rows the app edits itself are otherwise left alone.
IF OBJECT_ID(N'dbo.__live_sync_rows', N'U') IS NULL
BEGIN
  CREATE TABLE dbo.__live_sync_rows (
    table_name NVARCHAR(64)  NOT NULL,
    row_key    NVARCHAR(200) NOT NULL,
    row_hash   VARBINARY(32) NOT NULL,
    synced_at  DATETIME2     NOT NULL CONSTRAINT DF___live_sync_rows_synced_at DEFAULT (SYSUTCDATETIME()),
    CONSTRAINT PK___live_sync_rows PRIMARY KEY (table_name, row_key)
  );
END;
GO
