-- TalentScope first-wave tables (mirror of Supabase inventory for company MSSQL)
-- JSON / array columns stored as TEXT JSON text.

CREATE TABLE IF NOT EXISTS public.resumes (
    id            UUID NOT NULL CONSTRAINT PK_resumes PRIMARY KEY DEFAULT gen_random_uuid(),
    filename      VARCHAR(500) NOT NULL,
    text_content  TEXT NULL,
    parsed        TEXT NULL,
    analysis      TEXT NULL,
    enhanced      TEXT NULL,
    report        TEXT NULL,
    error         TEXT NULL,
    created_at    TIMESTAMPTZ NOT NULL CONSTRAINT DF_resumes_created_at DEFAULT (CURRENT_TIMESTAMP),
    file_hash     VARCHAR(128) NULL,
    file_base64   TEXT NULL,
    reset_count   INT NOT NULL CONSTRAINT DF_resumes_reset_count DEFAULT (0)
  );
CREATE TABLE IF NOT EXISTS public.job_descriptions (
    id          UUID NOT NULL CONSTRAINT PK_job_descriptions PRIMARY KEY DEFAULT gen_random_uuid(),
    jd_text     TEXT NOT NULL,
    rm_email    VARCHAR(320) NOT NULL,
    file_name   VARCHAR(500) NULL,
    created_at  TIMESTAMPTZ NOT NULL CONSTRAINT DF_job_descriptions_created_at DEFAULT (CURRENT_TIMESTAMP)
  );
CREATE TABLE IF NOT EXISTS public.portal_settings (
    "key"       VARCHAR(200) NOT NULL CONSTRAINT PK_portal_settings PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL CONSTRAINT DF_portal_settings_updated_at DEFAULT (CURRENT_TIMESTAMP)
  );
CREATE TABLE IF NOT EXISTS public.employees (
    id                  UUID NOT NULL CONSTRAINT PK_employees PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_id         VARCHAR(64) NOT NULL,
    email               VARCHAR(320) NOT NULL,
    full_name           VARCHAR(300) NOT NULL,
    department          VARCHAR(64) NOT NULL CONSTRAINT DF_employees_department DEFAULT ('general'),
    role                VARCHAR(200) NOT NULL CONSTRAINT DF_employees_role DEFAULT (''),
    avatar_url          VARCHAR(1000) NULL,
    xp_points           INT NOT NULL CONSTRAINT DF_employees_xp DEFAULT (0),
    streak_days         INT NOT NULL CONSTRAINT DF_employees_streak DEFAULT (0),
    last_active_date    DATE NULL,
    badges              TEXT NOT NULL CONSTRAINT DF_employees_badges DEFAULT ('[]'),
    skill_level         VARCHAR(32) NOT NULL CONSTRAINT DF_employees_skill_level DEFAULT ('beginner'),
    ai_readiness_score  INT NOT NULL CONSTRAINT DF_employees_ai_score DEFAULT (0),
    is_first_login      BOOLEAN NOT NULL CONSTRAINT DF_employees_first_login DEFAULT TRUE,
    product             VARCHAR(200) NULL,
    password_hash       VARCHAR(500) NULL,
    password_salt       VARCHAR(200) NULL,
    product_qb_eligible BOOLEAN NOT NULL CONSTRAINT DF_employees_qb DEFAULT FALSE,
    assessment_only     BOOLEAN NOT NULL CONSTRAINT DF_employees_assessment_only DEFAULT FALSE,
    created_at          TIMESTAMPTZ NOT NULL CONSTRAINT DF_employees_created_at DEFAULT (CURRENT_TIMESTAMP),
    updated_at          TIMESTAMPTZ NOT NULL CONSTRAINT DF_employees_updated_at DEFAULT (CURRENT_TIMESTAMP),
    CONSTRAINT UQ_employees_employee_id UNIQUE (employee_id)
  );
CREATE TABLE IF NOT EXISTS public.tests (
    id                     UUID NOT NULL CONSTRAINT PK_tests PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_id            UUID NOT NULL,
    employee_code          VARCHAR(64) NOT NULL CONSTRAINT DF_tests_employee_code DEFAULT (''),
    topic_id               VARCHAR(200) NOT NULL,
    subject_id             VARCHAR(200) NOT NULL,
    topic_title            VARCHAR(500) NULL,
    subject_title          VARCHAR(500) NULL,
    difficulty             VARCHAR(32) NOT NULL CONSTRAINT DF_tests_difficulty DEFAULT ('medium'),
    total_questions        INT NOT NULL CONSTRAINT DF_tests_total_q DEFAULT (25),
    time_limit_seconds     INT NOT NULL CONSTRAINT DF_tests_time_limit DEFAULT (1800),
    status                 VARCHAR(32) NOT NULL CONSTRAINT DF_tests_status DEFAULT ('pending'),
    current_question_index INT NOT NULL CONSTRAINT DF_tests_q_index DEFAULT (0),
    started_at             TIMESTAMPTZ NULL,
    completed_at           TIMESTAMPTZ NULL,
    in_progress            TEXT NULL,
    session_recording_url  VARCHAR(1000) NULL,
    proctoring             TEXT NULL,
    score_correct          INT NULL,
    score_total            INT NULL,
    score_percent          DECIMAL(5,2) NULL,
    ai_analysis            TEXT NULL,
    created_at             TIMESTAMPTZ NOT NULL CONSTRAINT DF_tests_created_at DEFAULT (CURRENT_TIMESTAMP),
    CONSTRAINT FK_tests_employees FOREIGN KEY (employee_id) REFERENCES public.employees(id) ON DELETE CASCADE,
    CONSTRAINT UQ_tests_employee_topic UNIQUE (employee_id, topic_id)
  );
CREATE TABLE IF NOT EXISTS public.audit_logs (
    id            UUID NOT NULL CONSTRAINT PK_audit_logs PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_email   VARCHAR(320) NOT NULL,
    action        VARCHAR(200) NOT NULL,
    target        VARCHAR(500) NOT NULL,
    details       TEXT NULL,
    ip_address    VARCHAR(64) NULL,
    created_at    TIMESTAMPTZ NOT NULL CONSTRAINT DF_audit_logs_created_at DEFAULT (CURRENT_TIMESTAMP)
  );
CREATE TABLE IF NOT EXISTS public.simulated_emails (
    id              UUID NOT NULL CONSTRAINT PK_simulated_emails PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_email VARCHAR(320) NOT NULL,
    full_name       VARCHAR(300) NULL,
    subject         VARCHAR(500) NULL,
    body            TEXT NULL,
    status          VARCHAR(64) NULL,
    rm_email        VARCHAR(320) NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL CONSTRAINT DF_simulated_emails_created_at DEFAULT (CURRENT_TIMESTAMP)
  );
CREATE TABLE IF NOT EXISTS public.candidate_interview_data (
    id                    UUID NOT NULL CONSTRAINT PK_candidate_interview_data PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_name        VARCHAR(300) NULL,
    email                 VARCHAR(320) NULL,
    interview_status      VARCHAR(64) NOT NULL CONSTRAINT DF_cid_status DEFAULT ('Pending'),
    score                 DECIMAL(10,2) NULL,
    warning_count         INT NOT NULL CONSTRAINT DF_cid_warnings DEFAULT (0),
    evaluation            TEXT NULL,
    interview_started_at  TIMESTAMPTZ NULL,
    completed_at          TIMESTAMPTZ NULL,
    created_at            TIMESTAMPTZ NOT NULL CONSTRAINT DF_cid_created_at DEFAULT (CURRENT_TIMESTAMP),
    updated_at            TIMESTAMPTZ NOT NULL CONSTRAINT DF_cid_updated_at DEFAULT (CURRENT_TIMESTAMP)
  );

