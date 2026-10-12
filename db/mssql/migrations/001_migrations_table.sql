-- TalentScope MSSQL mirror — migration bookkeeping
IF OBJECT_ID(N'dbo.__migrations', N'U') IS NULL
BEGIN
  CREATE TABLE dbo.__migrations (
    id            INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    filename      NVARCHAR(260) NOT NULL UNIQUE,
    applied_at    DATETIMEOFFSET NOT NULL CONSTRAINT DF___migrations_applied_at DEFAULT (SYSUTCDATETIME())
  );
END;
GO
