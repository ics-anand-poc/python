ALTER TABLE public.employees ALTER COLUMN badges DROP DEFAULT;
ALTER TABLE public.employees
    ALTER COLUMN badges TYPE JSONB USING badges::jsonb,
    ALTER COLUMN badges SET DEFAULT '[]'::jsonb;

ALTER TABLE public.tests
    ALTER COLUMN in_progress TYPE JSONB USING in_progress::jsonb,
    ALTER COLUMN proctoring TYPE JSONB USING proctoring::jsonb,
    ALTER COLUMN ai_analysis TYPE JSONB USING ai_analysis::jsonb;

ALTER TABLE public.test_questions
    ALTER COLUMN options TYPE JSONB USING options::jsonb;

ALTER TABLE public.portal_settings
    ALTER COLUMN value TYPE JSONB USING value::jsonb;

ALTER TABLE public.evaluations
    ALTER COLUMN bloom_scores TYPE JSONB USING bloom_scores::jsonb,
    ALTER COLUMN bloom_submissions TYPE JSONB USING bloom_submissions::jsonb,
    ALTER COLUMN bloom_graded TYPE JSONB USING bloom_graded::jsonb;

ALTER TABLE public.candidate_interview_data
    ALTER COLUMN evaluation TYPE JSONB USING evaluation::jsonb;

ALTER TABLE public.question_sets
    ALTER COLUMN items TYPE JSONB USING items::jsonb;
