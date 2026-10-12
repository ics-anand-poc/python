-- SQL Server UNIQUE constraints allow a single NULL; Postgres (Supabase) allows many.
-- Filtered unique indexes give the Postgres behaviour for these nullable columns.
IF OBJECT_ID(N'dbo.UQ_cs_code', N'UQ') IS NOT NULL
  ALTER TABLE dbo.candidate_sessions DROP CONSTRAINT UQ_cs_code;
IF OBJECT_ID(N'dbo.UQ_cs_email', N'UQ') IS NOT NULL
  ALTER TABLE dbo.candidate_sessions DROP CONSTRAINT UQ_cs_email;
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'UX_cs_code' AND object_id = OBJECT_ID(N'dbo.candidate_sessions'))
  CREATE UNIQUE INDEX UX_cs_code ON dbo.candidate_sessions (code) WHERE code IS NOT NULL;
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'UX_cs_email' AND object_id = OBJECT_ID(N'dbo.candidate_sessions'))
  CREATE UNIQUE INDEX UX_cs_email ON dbo.candidate_sessions (email) WHERE email IS NOT NULL;
GO
