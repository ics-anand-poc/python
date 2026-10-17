-- Remaining TalentScope tables (full mirror of Supabase inventory)

CREATE TABLE IF NOT EXISTS public.interview_questions (
    id              UUID NOT NULL CONSTRAINT PK_interview_questions PRIMARY KEY DEFAULT gen_random_uuid(),
    resume_id       UUID NOT NULL,
    question_index  INT NOT NULL,
    question_text   TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL CONSTRAINT DF_iq_created_at DEFAULT (CURRENT_TIMESTAMP),
    CONSTRAINT FK_iq_resumes FOREIGN KEY (resume_id) REFERENCES public.resumes(id) ON DELETE CASCADE
  );
CREATE TABLE IF NOT EXISTS public.interview_attempts (
    id                UUID NOT NULL CONSTRAINT PK_interview_attempts PRIMARY KEY DEFAULT gen_random_uuid(),
    resume_id         UUID NOT NULL,
    question_index    INT NOT NULL,
    question_text     TEXT NOT NULL,
    candidate_answer  TEXT NOT NULL,
    mock_score        INT NOT NULL,
    mock_feedback     TEXT NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL CONSTRAINT DF_ia_created_at DEFAULT (CURRENT_TIMESTAMP),
    CONSTRAINT FK_ia_resumes FOREIGN KEY (resume_id) REFERENCES public.resumes(id) ON DELETE CASCADE
  );
CREATE TABLE IF NOT EXISTS public.candidate_sessions (
    id          UUID NOT NULL CONSTRAINT PK_candidate_sessions PRIMARY KEY DEFAULT gen_random_uuid(),
    code        VARCHAR(128) NULL,
    email       VARCHAR(320) NULL,
    created_at  TIMESTAMPTZ NOT NULL CONSTRAINT DF_cs_created_at DEFAULT (CURRENT_TIMESTAMP),
    used        BOOLEAN NOT NULL CONSTRAINT DF_cs_used DEFAULT FALSE,
    resume_id   UUID NULL,
    used_at     TIMESTAMPTZ NULL,
    CONSTRAINT UQ_cs_code UNIQUE (code),
    CONSTRAINT UQ_cs_email UNIQUE (email),
    CONSTRAINT FK_cs_resumes FOREIGN KEY (resume_id) REFERENCES public.resumes(id) ON DELETE CASCADE
  );
CREATE TABLE IF NOT EXISTS public.reset_logs (
    id               UUID NOT NULL CONSTRAINT PK_reset_logs PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_email  VARCHAR(320) NOT NULL,
    reset_by         VARCHAR(320) NOT NULL,
    source           VARCHAR(128) NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL CONSTRAINT DF_rl_created_at DEFAULT (CURRENT_TIMESTAMP)
  );
CREATE TABLE IF NOT EXISTS public.learning_subjects (
    id          UUID NOT NULL CONSTRAINT PK_learning_subjects PRIMARY KEY DEFAULT gen_random_uuid(),
    title       VARCHAR(300) NOT NULL,
    description TEXT NULL,
    icon        VARCHAR(64) NOT NULL CONSTRAINT DF_ls_icon DEFAULT ('BookOpen'),
    color       VARCHAR(32) NOT NULL CONSTRAINT DF_ls_color DEFAULT ('#3b82f6'),
    order_index INT NOT NULL CONSTRAINT DF_ls_order DEFAULT (0),
    is_active   BOOLEAN NOT NULL CONSTRAINT DF_ls_active DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL CONSTRAINT DF_ls_created_at DEFAULT (CURRENT_TIMESTAMP)
  );
CREATE TABLE IF NOT EXISTS public.learning_modules (
    id          UUID NOT NULL CONSTRAINT PK_learning_modules PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_id  UUID NOT NULL,
    title       VARCHAR(300) NOT NULL,
    description TEXT NULL,
    order_index INT NOT NULL CONSTRAINT DF_lm_order DEFAULT (0),
    created_at  TIMESTAMPTZ NOT NULL CONSTRAINT DF_lm_created_at DEFAULT (CURRENT_TIMESTAMP),
    CONSTRAINT FK_lm_subjects FOREIGN KEY (subject_id) REFERENCES public.learning_subjects(id) ON DELETE CASCADE
  );
CREATE TABLE IF NOT EXISTS public.learning_topics (
    id                 UUID NOT NULL CONSTRAINT PK_learning_topics PRIMARY KEY DEFAULT gen_random_uuid(),
    module_id          UUID NOT NULL,
    title              VARCHAR(300) NOT NULL,
    description        TEXT NULL,
    difficulty         VARCHAR(32) NOT NULL CONSTRAINT DF_lt_difficulty DEFAULT ('beginner'),
    order_index        INT NOT NULL CONSTRAINT DF_lt_order DEFAULT (0),
    estimated_minutes  INT NOT NULL CONSTRAINT DF_lt_minutes DEFAULT (30),
    created_at         TIMESTAMPTZ NOT NULL CONSTRAINT DF_lt_created_at DEFAULT (CURRENT_TIMESTAMP),
    CONSTRAINT FK_lt_modules FOREIGN KEY (module_id) REFERENCES public.learning_modules(id) ON DELETE CASCADE
  );
CREATE TABLE IF NOT EXISTS public.learning_resources (
    id               UUID NOT NULL CONSTRAINT PK_learning_resources PRIMARY KEY DEFAULT gen_random_uuid(),
    topic_id         UUID NOT NULL,
    type             VARCHAR(32) NOT NULL CONSTRAINT DF_lr_type DEFAULT ('article'),
    title            VARCHAR(500) NOT NULL,
    url              VARCHAR(1000) NOT NULL,
    source           VARCHAR(300) NULL,
    duration_minutes INT NULL,
    order_index      INT NOT NULL CONSTRAINT DF_lr_order DEFAULT (0),
    created_at       TIMESTAMPTZ NOT NULL CONSTRAINT DF_lr_created_at DEFAULT (CURRENT_TIMESTAMP),
    CONSTRAINT FK_lr_topics FOREIGN KEY (topic_id) REFERENCES public.learning_topics(id) ON DELETE CASCADE
  );
CREATE TABLE IF NOT EXISTS public.test_questions (
    id                   UUID NOT NULL CONSTRAINT PK_test_questions PRIMARY KEY DEFAULT gen_random_uuid(),
    test_id              UUID NOT NULL,
    question_index       INT NOT NULL,
    question_text        TEXT NOT NULL,
    options              TEXT NOT NULL,
    correct_option_index INT NOT NULL,
    explanation          TEXT NOT NULL CONSTRAINT DF_tq_explanation DEFAULT (''),
    difficulty           VARCHAR(32) NOT NULL CONSTRAINT DF_tq_difficulty DEFAULT ('medium'),
    topic_id             VARCHAR(200) NOT NULL,
    topic_title          VARCHAR(500) NOT NULL CONSTRAINT DF_tq_topic_title DEFAULT (''),
    created_at           TIMESTAMPTZ NOT NULL CONSTRAINT DF_tq_created_at DEFAULT (CURRENT_TIMESTAMP),
    CONSTRAINT FK_tq_tests FOREIGN KEY (test_id) REFERENCES public.tests(id) ON DELETE CASCADE,
    CONSTRAINT UQ_tq_test_index UNIQUE (test_id, question_index)
  );
CREATE TABLE IF NOT EXISTS public.test_attempts (
    id                    UUID NOT NULL CONSTRAINT PK_test_attempts PRIMARY KEY DEFAULT gen_random_uuid(),
    test_id               UUID NOT NULL,
    employee_id           UUID NOT NULL,
    question_id           UUID NOT NULL,
    selected_option_index INT NOT NULL,
    is_correct            BOOLEAN NOT NULL,
    time_taken_seconds    INT NOT NULL CONSTRAINT DF_ta_time DEFAULT (0),
    session_key           VARCHAR(200) NOT NULL CONSTRAINT DF_ta_session DEFAULT (''),
    created_at            TIMESTAMPTZ NOT NULL CONSTRAINT DF_ta_created_at DEFAULT (CURRENT_TIMESTAMP),
    CONSTRAINT FK_ta_tests FOREIGN KEY (test_id) REFERENCES public.tests(id) ON DELETE CASCADE,
    CONSTRAINT FK_ta_employees FOREIGN KEY (employee_id) REFERENCES public.employees(id),
    CONSTRAINT FK_ta_questions FOREIGN KEY (question_id) REFERENCES public.test_questions(id)
  );
CREATE TABLE IF NOT EXISTS public.evaluations (
    id                      UUID NOT NULL CONSTRAINT PK_evaluations PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_id             VARCHAR(64) NOT NULL,
    employee_name           VARCHAR(300) NOT NULL,
    department              VARCHAR(128) NOT NULL,
    subject_id              VARCHAR(200) NOT NULL,
    subject_title           VARCHAR(300) NOT NULL,
    pre_test_score          INT NOT NULL CONSTRAINT DF_ev_pre DEFAULT (0),
    post_test_score         INT NOT NULL CONSTRAINT DF_ev_post DEFAULT (0),
    learning_gain_pct       DECIMAL(10,2) NOT NULL CONSTRAINT DF_ev_gain DEFAULT (0),
    reaction_relevance      INT NULL,
    reaction_utility        INT NULL,
    reaction_instructor     INT NULL,
    reaction_nps            INT NULL,
    reaction_comments       TEXT NULL,
    reaction_submitted_at   TIMESTAMPTZ NULL,
    bloom_scores            TEXT NULL,
    bloom_submissions       TEXT NULL,
    bloom_graded            TEXT NULL,
    bloom_graded_by         VARCHAR(320) NULL,
    bloom_graded_at         TIMESTAMPTZ NULL,
    completion_date         TIMESTAMPTZ NULL,
    created_at              TIMESTAMPTZ NOT NULL CONSTRAINT DF_ev_created_at DEFAULT (CURRENT_TIMESTAMP),
    updated_at              TIMESTAMPTZ NOT NULL CONSTRAINT DF_ev_updated_at DEFAULT (CURRENT_TIMESTAMP),
    CONSTRAINT UQ_evaluations_emp_subject UNIQUE (employee_id, subject_id)
  );
CREATE TABLE IF NOT EXISTS public.behavior_evaluations (
    id                        UUID NOT NULL CONSTRAINT PK_behavior_evaluations PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_id               VARCHAR(64) NOT NULL,
    subject_id                VARCHAR(200) NOT NULL,
    evaluator_role            VARCHAR(64) NOT NULL,
    evaluator_email           VARCHAR(320) NOT NULL,
    interval_days             INT NOT NULL,
    q1_demonstrates_skills    INT NOT NULL,
    q2_independently_applies  INT NOT NULL,
    q3_shares_learning        INT NOT NULL,
    q4_solves_problems        INT NOT NULL,
    q5_measurable_improvement INT NOT NULL,
    comments                  TEXT NULL,
    submitted_at              TIMESTAMPTZ NOT NULL CONSTRAINT DF_be_submitted DEFAULT (CURRENT_TIMESTAMP),
    CONSTRAINT UQ_behavior_eval UNIQUE (employee_id, subject_id, evaluator_role, interval_days)
  );
CREATE TABLE IF NOT EXISTS public.business_impacts (
    id                      UUID NOT NULL CONSTRAINT PK_business_impacts PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_id             VARCHAR(64) NOT NULL,
    subject_id              VARCHAR(200) NOT NULL,
    productivity_before     INT NOT NULL,
    productivity_after      INT NOT NULL,
    productivity_metric     VARCHAR(200) NOT NULL,
    quality_before          INT NOT NULL,
    quality_after           INT NOT NULL,
    quality_metric          VARCHAR(200) NOT NULL,
    customer_csat_before    INT NOT NULL,
    customer_csat_after     INT NOT NULL,
    cost_reduction          DECIMAL(12,2) NOT NULL CONSTRAINT DF_bi_cost DEFAULT (0),
    time_saved_hours        DECIMAL(12,2) NOT NULL CONSTRAINT DF_bi_time DEFAULT (0),
    roi_score               DECIMAL(12,2) NOT NULL CONSTRAINT DF_bi_roi DEFAULT (0),
    business_impact_score   INT NOT NULL,
    approved_by_pm          BOOLEAN NOT NULL CONSTRAINT DF_bi_pm DEFAULT FALSE,
    approved_by_rm          BOOLEAN NOT NULL CONSTRAINT DF_bi_rm DEFAULT FALSE,
    created_at              TIMESTAMPTZ NOT NULL CONSTRAINT DF_bi_created_at DEFAULT (CURRENT_TIMESTAMP),
    updated_at              TIMESTAMPTZ NOT NULL CONSTRAINT DF_bi_updated_at DEFAULT (CURRENT_TIMESTAMP),
    CONSTRAINT UQ_business_impacts UNIQUE (employee_id, subject_id)
  );
