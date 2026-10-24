IF OBJECT_ID(N'dbo.question_sets', N'U') IS NULL
BEGIN
  CREATE TABLE dbo.question_sets (
    resume_id     UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_question_sets PRIMARY KEY,
    status        NVARCHAR(16)     NOT NULL CONSTRAINT DF_question_sets_status DEFAULT (N'queued'),
    language      NVARCHAR(32)     NULL,
    served        NVARCHAR(16)     NULL,
    items         NVARCHAR(MAX)    NULL,
    attempts      INT              NOT NULL CONSTRAINT DF_question_sets_attempts DEFAULT (0),
    last_error    NVARCHAR(500)    NULL,
    queued_at     DATETIMEOFFSET   NOT NULL CONSTRAINT DF_question_sets_queued_at DEFAULT (SYSUTCDATETIME()),
    updated_at    DATETIMEOFFSET   NOT NULL CONSTRAINT DF_question_sets_updated_at DEFAULT (SYSUTCDATETIME()),
    CONSTRAINT FK_question_sets_resumes FOREIGN KEY (resume_id) REFERENCES dbo.resumes(id) ON DELETE CASCADE
  );
  CREATE INDEX IX_question_sets_status ON dbo.question_sets (status, updated_at);
END;
GO

IF OBJECT_ID(N'dbo.interview_question_bank', N'U') IS NULL
BEGIN
  CREATE TABLE dbo.interview_question_bank (
    id            UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_interview_question_bank PRIMARY KEY DEFAULT NEWSEQUENTIALID(),
    bank_key      NVARCHAR(64)     NOT NULL,
    kind          NVARCHAR(16)     NOT NULL,
    language      NVARCHAR(32)     NULL,
    difficulty    NVARCHAR(16)     NULL,
    question_text NVARCHAR(MAX)    NOT NULL,
    text_hash     NVARCHAR(40)     NOT NULL,
    created_at    DATETIMEOFFSET   NOT NULL CONSTRAINT DF_iqb_created_at DEFAULT (SYSUTCDATETIME())
  );
  CREATE UNIQUE INDEX UX_iqb_key_hash ON dbo.interview_question_bank (bank_key, kind, text_hash);
  CREATE INDEX IX_iqb_lookup ON dbo.interview_question_bank (bank_key, kind, language);
END;
GO
