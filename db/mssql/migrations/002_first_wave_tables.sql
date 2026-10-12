-- TalentScope first-wave tables (mirror of Supabase inventory for company MSSQL)
-- JSON / array columns stored as NVARCHAR(MAX) JSON text.

IF OBJECT_ID(N'dbo.resumes', N'U') IS NULL
BEGIN
  CREATE TABLE dbo.resumes (
    id            UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_resumes PRIMARY KEY DEFAULT NEWSEQUENTIALID(),
    filename      NVARCHAR(500) NOT NULL,
    text_content  NVARCHAR(MAX) NULL,
    parsed        NVARCHAR(MAX) NULL,
    analysis      NVARCHAR(MAX) NULL,
    enhanced      NVARCHAR(MAX) NULL,
    report        NVARCHAR(MAX) NULL,
    error         NVARCHAR(MAX) NULL,
    created_at    DATETIMEOFFSET NOT NULL CONSTRAINT DF_resumes_created_at DEFAULT (SYSUTCDATETIME()),
    file_hash     NVARCHAR(128) NULL,
    file_base64   NVARCHAR(MAX) NULL,
    reset_count   INT NOT NULL CONSTRAINT DF_resumes_reset_count DEFAULT (0)
  );
END;
GO

IF OBJECT_ID(N'dbo.job_descriptions', N'U') IS NULL
BEGIN
  CREATE TABLE dbo.job_descriptions (
    id          UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_job_descriptions PRIMARY KEY DEFAULT NEWSEQUENTIALID(),
    jd_text     NVARCHAR(MAX) NOT NULL,
    rm_email    NVARCHAR(320) NOT NULL,
    file_name   NVARCHAR(500) NULL,
    created_at  DATETIMEOFFSET NOT NULL CONSTRAINT DF_job_descriptions_created_at DEFAULT (SYSUTCDATETIME())
  );
END;
GO

IF OBJECT_ID(N'dbo.portal_settings', N'U') IS NULL
BEGIN
  CREATE TABLE dbo.portal_settings (
    [key]       NVARCHAR(200) NOT NULL CONSTRAINT PK_portal_settings PRIMARY KEY,
    value       NVARCHAR(MAX) NOT NULL,
    updated_at  DATETIMEOFFSET NOT NULL CONSTRAINT DF_portal_settings_updated_at DEFAULT (SYSUTCDATETIME())
  );
END;
GO

IF OBJECT_ID(N'dbo.employees', N'U') IS NULL
BEGIN
  CREATE TABLE dbo.employees (
    id                  UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_employees PRIMARY KEY DEFAULT NEWSEQUENTIALID(),
    employee_id         NVARCHAR(64) NOT NULL,
    email               NVARCHAR(320) NOT NULL,
    full_name           NVARCHAR(300) NOT NULL,
    department          NVARCHAR(64) NOT NULL CONSTRAINT DF_employees_department DEFAULT (N'general'),
    role                NVARCHAR(200) NOT NULL CONSTRAINT DF_employees_role DEFAULT (N''),
    avatar_url          NVARCHAR(1000) NULL,
    xp_points           INT NOT NULL CONSTRAINT DF_employees_xp DEFAULT (0),
    streak_days         INT NOT NULL CONSTRAINT DF_employees_streak DEFAULT (0),
    last_active_date    DATE NULL,
    badges              NVARCHAR(MAX) NOT NULL CONSTRAINT DF_employees_badges DEFAULT (N'[]'),
    skill_level         NVARCHAR(32) NOT NULL CONSTRAINT DF_employees_skill_level DEFAULT (N'beginner'),
    ai_readiness_score  INT NOT NULL CONSTRAINT DF_employees_ai_score DEFAULT (0),
    is_first_login      BIT NOT NULL CONSTRAINT DF_employees_first_login DEFAULT (1),
    product             NVARCHAR(200) NULL,
    password_hash       NVARCHAR(500) NULL,
    password_salt       NVARCHAR(200) NULL,
    product_qb_eligible BIT NOT NULL CONSTRAINT DF_employees_qb DEFAULT (0),
    assessment_only     BIT NOT NULL CONSTRAINT DF_employees_assessment_only DEFAULT (0),
    created_at          DATETIMEOFFSET NOT NULL CONSTRAINT DF_employees_created_at DEFAULT (SYSUTCDATETIME()),
    updated_at          DATETIMEOFFSET NOT NULL CONSTRAINT DF_employees_updated_at DEFAULT (SYSUTCDATETIME()),
    CONSTRAINT UQ_employees_employee_id UNIQUE (employee_id)
  );
END;
GO

IF OBJECT_ID(N'dbo.tests', N'U') IS NULL
BEGIN
  CREATE TABLE dbo.tests (
    id                     UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_tests PRIMARY KEY DEFAULT NEWSEQUENTIALID(),
    employee_id            UNIQUEIDENTIFIER NOT NULL,
    employee_code          NVARCHAR(64) NOT NULL CONSTRAINT DF_tests_employee_code DEFAULT (N''),
    topic_id               NVARCHAR(200) NOT NULL,
    subject_id             NVARCHAR(200) NOT NULL,
    topic_title            NVARCHAR(500) NULL,
    subject_title          NVARCHAR(500) NULL,
    difficulty             NVARCHAR(32) NOT NULL CONSTRAINT DF_tests_difficulty DEFAULT (N'medium'),
    total_questions        INT NOT NULL CONSTRAINT DF_tests_total_q DEFAULT (25),
    time_limit_seconds     INT NOT NULL CONSTRAINT DF_tests_time_limit DEFAULT (1800),
    status                 NVARCHAR(32) NOT NULL CONSTRAINT DF_tests_status DEFAULT (N'pending'),
    current_question_index INT NOT NULL CONSTRAINT DF_tests_q_index DEFAULT (0),
    started_at             DATETIMEOFFSET NULL,
    completed_at           DATETIMEOFFSET NULL,
    in_progress            NVARCHAR(MAX) NULL,
    session_recording_url  NVARCHAR(1000) NULL,
    proctoring             NVARCHAR(MAX) NULL,
    score_correct          INT NULL,
    score_total            INT NULL,
    score_percent          DECIMAL(5,2) NULL,
    ai_analysis            NVARCHAR(MAX) NULL,
    created_at             DATETIMEOFFSET NOT NULL CONSTRAINT DF_tests_created_at DEFAULT (SYSUTCDATETIME()),
    CONSTRAINT FK_tests_employees FOREIGN KEY (employee_id) REFERENCES dbo.employees(id) ON DELETE CASCADE,
    CONSTRAINT UQ_tests_employee_topic UNIQUE (employee_id, topic_id)
  );
END;
GO

IF OBJECT_ID(N'dbo.audit_logs', N'U') IS NULL
BEGIN
  CREATE TABLE dbo.audit_logs (
    id            UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_audit_logs PRIMARY KEY DEFAULT NEWSEQUENTIALID(),
    actor_email   NVARCHAR(320) NOT NULL,
    action        NVARCHAR(200) NOT NULL,
    target        NVARCHAR(500) NOT NULL,
    details       NVARCHAR(MAX) NULL,
    ip_address    NVARCHAR(64) NULL,
    created_at    DATETIMEOFFSET NOT NULL CONSTRAINT DF_audit_logs_created_at DEFAULT (SYSUTCDATETIME())
  );
END;
GO

IF OBJECT_ID(N'dbo.simulated_emails', N'U') IS NULL
BEGIN
  CREATE TABLE dbo.simulated_emails (
    id              UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_simulated_emails PRIMARY KEY DEFAULT NEWSEQUENTIALID(),
    candidate_email NVARCHAR(320) NOT NULL,
    full_name       NVARCHAR(300) NULL,
    subject         NVARCHAR(500) NULL,
    body            NVARCHAR(MAX) NULL,
    status          NVARCHAR(64) NULL,
    rm_email        NVARCHAR(320) NOT NULL,
    created_at      DATETIMEOFFSET NOT NULL CONSTRAINT DF_simulated_emails_created_at DEFAULT (SYSUTCDATETIME())
  );
END;
GO

IF OBJECT_ID(N'dbo.candidate_interview_data', N'U') IS NULL
BEGIN
  CREATE TABLE dbo.candidate_interview_data (
    id                    UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_candidate_interview_data PRIMARY KEY DEFAULT NEWSEQUENTIALID(),
    candidate_name        NVARCHAR(300) NULL,
    email                 NVARCHAR(320) NULL,
    interview_status      NVARCHAR(64) NOT NULL CONSTRAINT DF_cid_status DEFAULT (N'Pending'),
    score                 DECIMAL(10,2) NULL,
    warning_count         INT NOT NULL CONSTRAINT DF_cid_warnings DEFAULT (0),
    evaluation            NVARCHAR(MAX) NULL,
    interview_started_at  DATETIMEOFFSET NULL,
    completed_at          DATETIMEOFFSET NULL,
    created_at            DATETIMEOFFSET NOT NULL CONSTRAINT DF_cid_created_at DEFAULT (SYSUTCDATETIME()),
    updated_at            DATETIMEOFFSET NOT NULL CONSTRAINT DF_cid_updated_at DEFAULT (SYSUTCDATETIME())
  );
END;
GO
