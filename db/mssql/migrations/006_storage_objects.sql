-- File storage (resumes, recordings, verifications, app-data, docs-ingest) for STORAGE_PROVIDER=mssql.
-- One row per object; (bucket, path) mirrors the object key used on the uploads volume.
IF OBJECT_ID(N'dbo.storage_objects', N'U') IS NULL
BEGIN
  CREATE TABLE dbo.storage_objects (
    id            BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_storage_objects PRIMARY KEY,
    bucket        NVARCHAR(100)  NOT NULL,
    path          NVARCHAR(700)  NOT NULL,
    content       VARBINARY(MAX) NOT NULL,
    content_type  NVARCHAR(200)  NULL,
    size_bytes    BIGINT         NOT NULL,
    created_at    DATETIMEOFFSET NOT NULL CONSTRAINT DF_storage_objects_created_at DEFAULT (SYSUTCDATETIME()),
    updated_at    DATETIMEOFFSET NOT NULL CONSTRAINT DF_storage_objects_updated_at DEFAULT (SYSUTCDATETIME())
  );
  CREATE UNIQUE NONCLUSTERED INDEX UX_storage_objects_bucket_path
    ON dbo.storage_objects (bucket, path) INCLUDE (size_bytes, content_type, created_at, updated_at);
END;
GO

-- Keep file bytes off the data pages so listing a bucket never reads them.
EXEC sp_tableoption N'dbo.storage_objects', 'large value types out of row', 1;
GO
