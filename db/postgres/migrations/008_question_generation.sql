CREATE TABLE IF NOT EXISTS public.question_sets (
    resume_id     UUID NOT NULL CONSTRAINT PK_question_sets PRIMARY KEY,
    status        VARCHAR(16)     NOT NULL CONSTRAINT DF_question_sets_status DEFAULT ('queued'),
    language      VARCHAR(32)     NULL,
    served        VARCHAR(16)     NULL,
    items         TEXT    NULL,
    attempts      INT              NOT NULL CONSTRAINT DF_question_sets_attempts DEFAULT (0),
    last_error    VARCHAR(500)    NULL,
    queued_at     TIMESTAMPTZ   NOT NULL CONSTRAINT DF_question_sets_queued_at DEFAULT (CURRENT_TIMESTAMP),
    updated_at    TIMESTAMPTZ   NOT NULL CONSTRAINT DF_question_sets_updated_at DEFAULT (CURRENT_TIMESTAMP),
    CONSTRAINT FK_question_sets_resumes FOREIGN KEY (resume_id) REFERENCES public.resumes(id) ON DELETE CASCADE
  );
  CREATE INDEX IF NOT EXISTS IX_question_sets_status ON public.question_sets (status, updated_at);
CREATE TABLE IF NOT EXISTS public.interview_question_bank (
    id            UUID NOT NULL CONSTRAINT PK_interview_question_bank PRIMARY KEY DEFAULT gen_random_uuid(),
    bank_key      VARCHAR(64)     NOT NULL,
    kind          VARCHAR(16)     NOT NULL,
    language      VARCHAR(32)     NULL,
    difficulty    VARCHAR(16)     NULL,
    question_text TEXT    NOT NULL,
    text_hash     VARCHAR(40)     NOT NULL,
    created_at    TIMESTAMPTZ   NOT NULL CONSTRAINT DF_iqb_created_at DEFAULT (CURRENT_TIMESTAMP)
  );
  CREATE UNIQUE INDEX IF NOT EXISTS UX_iqb_key_hash ON public.interview_question_bank (bank_key, kind, text_hash);
  CREATE INDEX IF NOT EXISTS IX_iqb_lookup ON public.interview_question_bank (bank_key, kind, language);

