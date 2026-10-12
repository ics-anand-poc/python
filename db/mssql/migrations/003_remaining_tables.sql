-- Remaining TalentScope tables (full mirror of Supabase inventory)

IF OBJECT_ID(N'dbo.interview_questions', N'U') IS NULL
BEGIN
  CREATE TABLE dbo.interview_questions (
    id              UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_interview_questions PRIMARY KEY DEFAULT NEWSEQUENTIALID(),
    resume_id       UNIQUEIDENTIFIER NOT NULL,
    question_index  INT NOT NULL,
    question_text   NVARCHAR(MAX) NOT NULL,
    created_at      DATETIMEOFFSET NOT NULL CONSTRAINT DF_iq_created_at DEFAULT (SYSUTCDATETIME()),
    CONSTRAINT FK_iq_resumes FOREIGN KEY (resume_id) REFERENCES dbo.resumes(id) ON DELETE CASCADE
  );
END;
GO

IF OBJECT_ID(N'dbo.interview_attempts', N'U') IS NULL
BEGIN
  CREATE TABLE dbo.interview_attempts (
    id                UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_interview_attempts PRIMARY KEY DEFAULT NEWSEQUENTIALID(),
    resume_id         UNIQUEIDENTIFIER NOT NULL,
    question_index    INT NOT NULL,
    question_text     NVARCHAR(MAX) NOT NULL,
    candidate_answer  NVARCHAR(MAX) NOT NULL,
    mock_score        INT NOT NULL,
    mock_feedback     NVARCHAR(MAX) NOT NULL,
    created_at        DATETIMEOFFSET NOT NULL CONSTRAINT DF_ia_created_at DEFAULT (SYSUTCDATETIME()),
    CONSTRAINT FK_ia_resumes FOREIGN KEY (resume_id) REFERENCES dbo.resumes(id) ON DELETE CASCADE
  );
END;
GO

IF OBJECT_ID(N'dbo.candidate_sessions', N'U') IS NULL
BEGIN
  CREATE TABLE dbo.candidate_sessions (
    id          UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_candidate_sessions PRIMARY KEY DEFAULT NEWSEQUENTIALID(),
    code        NVARCHAR(128) NULL,
    email       NVARCHAR(320) NULL,
    created_at  DATETIMEOFFSET NOT NULL CONSTRAINT DF_cs_created_at DEFAULT (SYSUTCDATETIME()),
    used        BIT NOT NULL CONSTRAINT DF_cs_used DEFAULT (0),
    resume_id   UNIQUEIDENTIFIER NULL,
    used_at     DATETIMEOFFSET NULL,
    CONSTRAINT UQ_cs_code UNIQUE (code),
    CONSTRAINT UQ_cs_email UNIQUE (email),
    CONSTRAINT FK_cs_resumes FOREIGN KEY (resume_id) REFERENCES dbo.resumes(id) ON DELETE CASCADE
  );
END;
GO

IF OBJECT_ID(N'dbo.reset_logs', N'U') IS NULL
BEGIN
  CREATE TABLE dbo.reset_logs (
    id               UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_reset_logs PRIMARY KEY DEFAULT NEWSEQUENTIALID(),
    candidate_email  NVARCHAR(320) NOT NULL,
    reset_by         NVARCHAR(320) NOT NULL,
    source           NVARCHAR(128) NOT NULL,
    created_at       DATETIMEOFFSET NOT NULL CONSTRAINT DF_rl_created_at DEFAULT (SYSUTCDATETIME())
  );
END;
GO

IF OBJECT_ID(N'dbo.learning_subjects', N'U') IS NULL
BEGIN
  CREATE TABLE dbo.learning_subjects (
    id          UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_learning_subjects PRIMARY KEY DEFAULT NEWSEQUENTIALID(),
    title       NVARCHAR(300) NOT NULL,
    description NVARCHAR(MAX) NULL,
    icon        NVARCHAR(64) NOT NULL CONSTRAINT DF_ls_icon DEFAULT (N'BookOpen'),
    color       NVARCHAR(32) NOT NULL CONSTRAINT DF_ls_color DEFAULT (N'#3b82f6'),
    order_index INT NOT NULL CONSTRAINT DF_ls_order DEFAULT (0),
    is_active   BIT NOT NULL CONSTRAINT DF_ls_active DEFAULT (1),
    created_at  DATETIMEOFFSET NOT NULL CONSTRAINT DF_ls_created_at DEFAULT (SYSUTCDATETIME())
  );
END;
GO

IF OBJECT_ID(N'dbo.learning_modules', N'U') IS NULL
BEGIN
  CREATE TABLE dbo.learning_modules (
    id          UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_learning_modules PRIMARY KEY DEFAULT NEWSEQUENTIALID(),
    subject_id  UNIQUEIDENTIFIER NOT NULL,
    title       NVARCHAR(300) NOT NULL,
    description NVARCHAR(MAX) NULL,
    order_index INT NOT NULL CONSTRAINT DF_lm_order DEFAULT (0),
    created_at  DATETIMEOFFSET NOT NULL CONSTRAINT DF_lm_created_at DEFAULT (SYSUTCDATETIME()),
    CONSTRAINT FK_lm_subjects FOREIGN KEY (subject_id) REFERENCES dbo.learning_subjects(id) ON DELETE CASCADE
  );
END;
GO

IF OBJECT_ID(N'dbo.learning_topics', N'U') IS NULL
BEGIN
  CREATE TABLE dbo.learning_topics (
    id                 UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_learning_topics PRIMARY KEY DEFAULT NEWSEQUENTIALID(),
    module_id          UNIQUEIDENTIFIER NOT NULL,
    title              NVARCHAR(300) NOT NULL,
    description        NVARCHAR(MAX) NULL,
    difficulty         NVARCHAR(32) NOT NULL CONSTRAINT DF_lt_difficulty DEFAULT (N'beginner'),
    order_index        INT NOT NULL CONSTRAINT DF_lt_order DEFAULT (0),
    estimated_minutes  INT NOT NULL CONSTRAINT DF_lt_minutes DEFAULT (30),
    created_at         DATETIMEOFFSET NOT NULL CONSTRAINT DF_lt_created_at DEFAULT (SYSUTCDATETIME()),
    CONSTRAINT FK_lt_modules FOREIGN KEY (module_id) REFERENCES dbo.learning_modules(id) ON DELETE CASCADE
  );
END;
GO

IF OBJECT_ID(N'dbo.learning_resources', N'U') IS NULL
BEGIN
  CREATE TABLE dbo.learning_resources (
    id               UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_learning_resources PRIMARY KEY DEFAULT NEWSEQUENTIALID(),
    topic_id         UNIQUEIDENTIFIER NOT NULL,
    type             NVARCHAR(32) NOT NULL CONSTRAINT DF_lr_type DEFAULT (N'article'),
    title            NVARCHAR(500) NOT NULL,
    url              NVARCHAR(1000) NOT NULL,
    source           NVARCHAR(300) NULL,
    duration_minutes INT NULL,
    order_index      INT NOT NULL CONSTRAINT DF_lr_order DEFAULT (0),
    created_at       DATETIMEOFFSET NOT NULL CONSTRAINT DF_lr_created_at DEFAULT (SYSUTCDATETIME()),
    CONSTRAINT FK_lr_topics FOREIGN KEY (topic_id) REFERENCES dbo.learning_topics(id) ON DELETE CASCADE
  );
END;
GO

IF OBJECT_ID(N'dbo.test_questions', N'U') IS NULL
BEGIN
  CREATE TABLE dbo.test_questions (
    id                   UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_test_questions PRIMARY KEY DEFAULT NEWSEQUENTIALID(),
    test_id              UNIQUEIDENTIFIER NOT NULL,
    question_index       INT NOT NULL,
    question_text        NVARCHAR(MAX) NOT NULL,
    options              NVARCHAR(MAX) NOT NULL,
    correct_option_index INT NOT NULL,
    explanation          NVARCHAR(MAX) NOT NULL CONSTRAINT DF_tq_explanation DEFAULT (N''),
    difficulty           NVARCHAR(32) NOT NULL CONSTRAINT DF_tq_difficulty DEFAULT (N'medium'),
    topic_id             NVARCHAR(200) NOT NULL,
    topic_title          NVARCHAR(500) NOT NULL CONSTRAINT DF_tq_topic_title DEFAULT (N''),
    created_at           DATETIMEOFFSET NOT NULL CONSTRAINT DF_tq_created_at DEFAULT (SYSUTCDATETIME()),
    CONSTRAINT FK_tq_tests FOREIGN KEY (test_id) REFERENCES dbo.tests(id) ON DELETE CASCADE,
    CONSTRAINT UQ_tq_test_index UNIQUE (test_id, question_index)
  );
END;
GO

IF OBJECT_ID(N'dbo.test_attempts', N'U') IS NULL
BEGIN
  CREATE TABLE dbo.test_attempts (
    id                    UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_test_attempts PRIMARY KEY DEFAULT NEWSEQUENTIALID(),
    test_id               UNIQUEIDENTIFIER NOT NULL,
    employee_id           UNIQUEIDENTIFIER NOT NULL,
    question_id           UNIQUEIDENTIFIER NOT NULL,
    selected_option_index INT NOT NULL,
    is_correct            BIT NOT NULL,
    time_taken_seconds    INT NOT NULL CONSTRAINT DF_ta_time DEFAULT (0),
    session_key           NVARCHAR(200) NOT NULL CONSTRAINT DF_ta_session DEFAULT (N''),
    created_at            DATETIMEOFFSET NOT NULL CONSTRAINT DF_ta_created_at DEFAULT (SYSUTCDATETIME()),
    CONSTRAINT FK_ta_tests FOREIGN KEY (test_id) REFERENCES dbo.tests(id) ON DELETE CASCADE,
    CONSTRAINT FK_ta_employees FOREIGN KEY (employee_id) REFERENCES dbo.employees(id),
    CONSTRAINT FK_ta_questions FOREIGN KEY (question_id) REFERENCES dbo.test_questions(id)
  );
END;
GO

IF OBJECT_ID(N'dbo.evaluations', N'U') IS NULL
BEGIN
  CREATE TABLE dbo.evaluations (
    id                      UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_evaluations PRIMARY KEY DEFAULT NEWSEQUENTIALID(),
    employee_id             NVARCHAR(64) NOT NULL,
    employee_name           NVARCHAR(300) NOT NULL,
    department              NVARCHAR(128) NOT NULL,
    subject_id              NVARCHAR(200) NOT NULL,
    subject_title           NVARCHAR(300) NOT NULL,
    pre_test_score          INT NOT NULL CONSTRAINT DF_ev_pre DEFAULT (0),
    post_test_score         INT NOT NULL CONSTRAINT DF_ev_post DEFAULT (0),
    learning_gain_pct       DECIMAL(10,2) NOT NULL CONSTRAINT DF_ev_gain DEFAULT (0),
    reaction_relevance      INT NULL,
    reaction_utility        INT NULL,
    reaction_instructor     INT NULL,
    reaction_nps            INT NULL,
    reaction_comments       NVARCHAR(MAX) NULL,
    reaction_submitted_at   DATETIMEOFFSET NULL,
    bloom_scores            NVARCHAR(MAX) NULL,
    bloom_submissions       NVARCHAR(MAX) NULL,
    bloom_graded            NVARCHAR(MAX) NULL,
    bloom_graded_by         NVARCHAR(320) NULL,
    bloom_graded_at         DATETIMEOFFSET NULL,
    completion_date         DATETIMEOFFSET NULL,
    created_at              DATETIMEOFFSET NOT NULL CONSTRAINT DF_ev_created_at DEFAULT (SYSUTCDATETIME()),
    updated_at              DATETIMEOFFSET NOT NULL CONSTRAINT DF_ev_updated_at DEFAULT (SYSUTCDATETIME()),
    CONSTRAINT UQ_evaluations_emp_subject UNIQUE (employee_id, subject_id)
  );
END;
GO

IF OBJECT_ID(N'dbo.behavior_evaluations', N'U') IS NULL
BEGIN
  CREATE TABLE dbo.behavior_evaluations (
    id                        UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_behavior_evaluations PRIMARY KEY DEFAULT NEWSEQUENTIALID(),
    employee_id               NVARCHAR(64) NOT NULL,
    subject_id                NVARCHAR(200) NOT NULL,
    evaluator_role            NVARCHAR(64) NOT NULL,
    evaluator_email           NVARCHAR(320) NOT NULL,
    interval_days             INT NOT NULL,
    q1_demonstrates_skills    INT NOT NULL,
    q2_independently_applies  INT NOT NULL,
    q3_shares_learning        INT NOT NULL,
    q4_solves_problems        INT NOT NULL,
    q5_measurable_improvement INT NOT NULL,
    comments                  NVARCHAR(MAX) NULL,
    submitted_at              DATETIMEOFFSET NOT NULL CONSTRAINT DF_be_submitted DEFAULT (SYSUTCDATETIME()),
    CONSTRAINT UQ_behavior_eval UNIQUE (employee_id, subject_id, evaluator_role, interval_days)
  );
END;
GO

IF OBJECT_ID(N'dbo.business_impacts', N'U') IS NULL
BEGIN
  CREATE TABLE dbo.business_impacts (
    id                      UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_business_impacts PRIMARY KEY DEFAULT NEWSEQUENTIALID(),
    employee_id             NVARCHAR(64) NOT NULL,
    subject_id              NVARCHAR(200) NOT NULL,
    productivity_before     INT NOT NULL,
    productivity_after      INT NOT NULL,
    productivity_metric     NVARCHAR(200) NOT NULL,
    quality_before          INT NOT NULL,
    quality_after           INT NOT NULL,
    quality_metric          NVARCHAR(200) NOT NULL,
    customer_csat_before    INT NOT NULL,
    customer_csat_after     INT NOT NULL,
    cost_reduction          DECIMAL(12,2) NOT NULL CONSTRAINT DF_bi_cost DEFAULT (0),
    time_saved_hours        DECIMAL(12,2) NOT NULL CONSTRAINT DF_bi_time DEFAULT (0),
    roi_score               DECIMAL(12,2) NOT NULL CONSTRAINT DF_bi_roi DEFAULT (0),
    business_impact_score   INT NOT NULL,
    approved_by_pm          BIT NOT NULL CONSTRAINT DF_bi_pm DEFAULT (0),
    approved_by_rm          BIT NOT NULL CONSTRAINT DF_bi_rm DEFAULT (0),
    created_at              DATETIMEOFFSET NOT NULL CONSTRAINT DF_bi_created_at DEFAULT (SYSUTCDATETIME()),
    updated_at              DATETIMEOFFSET NOT NULL CONSTRAINT DF_bi_updated_at DEFAULT (SYSUTCDATETIME()),
    CONSTRAINT UQ_business_impacts UNIQUE (employee_id, subject_id)
  );
END;
GO
