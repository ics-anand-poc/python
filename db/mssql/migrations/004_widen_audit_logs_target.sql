-- Supabase audit_logs.target is unbounded text (some rows hold ~9.4k chars of bulk-action targets).
ALTER TABLE dbo.audit_logs ALTER COLUMN target NVARCHAR(MAX) NOT NULL;
GO
