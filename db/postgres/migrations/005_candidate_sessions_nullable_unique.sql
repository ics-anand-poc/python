ALTER TABLE public.candidate_sessions DROP CONSTRAINT IF EXISTS uq_cs_code;
ALTER TABLE public.candidate_sessions DROP CONSTRAINT IF EXISTS uq_cs_email;
CREATE UNIQUE INDEX IF NOT EXISTS ux_cs_code ON public.candidate_sessions (code) WHERE code IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_cs_email ON public.candidate_sessions (email) WHERE email IS NOT NULL;
