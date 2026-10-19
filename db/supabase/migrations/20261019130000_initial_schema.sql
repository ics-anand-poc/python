-- PostgreSQL schema used by the optional Supabase API database target.

create table public.resumes (
  id uuid primary key default gen_random_uuid(),
  filename varchar(500) not null,
  text_content text,
  parsed jsonb,
  analysis jsonb,
  enhanced jsonb,
  report jsonb,
  error text,
  created_at timestamptz not null default now(),
  file_hash varchar(128),
  file_base64 text,
  reset_count integer not null default 0
);

create table public.job_descriptions (
  id uuid primary key default gen_random_uuid(),
  jd_text text not null,
  rm_email varchar(320) not null,
  file_name varchar(500),
  created_at timestamptz not null default now()
);

create table public.portal_settings (
  key varchar(200) primary key,
  value jsonb not null,
  updated_at timestamptz not null default now()
);

create table public.employees (
  id uuid primary key default gen_random_uuid(),
  employee_id varchar(64) not null unique,
  email varchar(320) not null,
  full_name varchar(300) not null,
  department varchar(64) not null default 'general',
  role varchar(200) not null default '',
  avatar_url varchar(1000),
  xp_points integer not null default 0,
  streak_days integer not null default 0,
  last_active_date date,
  badges jsonb not null default '[]'::jsonb,
  skill_level varchar(32) not null default 'beginner',
  ai_readiness_score integer not null default 0,
  is_first_login boolean not null default true,
  product varchar(200),
  password_hash varchar(500),
  password_salt varchar(200),
  product_qb_eligible boolean not null default false,
  assessment_only boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.tests (
  id uuid primary key default gen_random_uuid(),
  employee_id uuid not null references public.employees(id) on delete cascade,
  employee_code varchar(64) not null default '',
  topic_id varchar(200) not null,
  subject_id varchar(200) not null,
  topic_title varchar(500),
  subject_title varchar(500),
  difficulty varchar(32) not null default 'medium',
  total_questions integer not null default 25,
  time_limit_seconds integer not null default 1800,
  status varchar(32) not null default 'pending',
  current_question_index integer not null default 0,
  started_at timestamptz,
  completed_at timestamptz,
  in_progress jsonb,
  session_recording_url varchar(1000),
  proctoring jsonb,
  score_correct integer,
  score_total integer,
  score_percent numeric(5, 2),
  ai_analysis jsonb,
  created_at timestamptz not null default now(),
  unique (employee_id, topic_id)
);

create table public.audit_logs (
  id uuid primary key default gen_random_uuid(),
  actor_email varchar(320) not null,
  action varchar(200) not null,
  target text not null,
  details jsonb,
  ip_address varchar(64),
  created_at timestamptz not null default now()
);

create table public.simulated_emails (
  id uuid primary key default gen_random_uuid(),
  candidate_email varchar(320) not null,
  full_name varchar(300),
  subject varchar(500),
  body text,
  status varchar(64),
  rm_email varchar(320) not null,
  created_at timestamptz not null default now()
);

create table public.candidate_interview_data (
  id uuid primary key default gen_random_uuid(),
  candidate_name varchar(300),
  email varchar(320),
  interview_status varchar(64) not null default 'Pending',
  score numeric(10, 2),
  warning_count integer not null default 0,
  evaluation jsonb,
  interview_started_at timestamptz,
  completed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.interview_questions (
  id uuid primary key default gen_random_uuid(),
  resume_id uuid not null references public.resumes(id) on delete cascade,
  question_index integer not null,
  question_text text not null,
  created_at timestamptz not null default now()
);

create table public.interview_attempts (
  id uuid primary key default gen_random_uuid(),
  resume_id uuid not null references public.resumes(id) on delete cascade,
  question_index integer not null,
  question_text text not null,
  candidate_answer text not null,
  mock_score integer not null,
  mock_feedback text not null,
  created_at timestamptz not null default now()
);

create table public.candidate_sessions (
  id uuid primary key default gen_random_uuid(),
  code varchar(128) unique,
  email varchar(320) unique,
  created_at timestamptz not null default now(),
  used boolean not null default false,
  resume_id uuid references public.resumes(id) on delete cascade,
  used_at timestamptz
);

create table public.reset_logs (
  id uuid primary key default gen_random_uuid(),
  candidate_email varchar(320) not null,
  reset_by varchar(320) not null,
  source varchar(128) not null,
  created_at timestamptz not null default now()
);

create table public.learning_subjects (
  id uuid primary key default gen_random_uuid(),
  title varchar(300) not null,
  description text,
  icon varchar(64) not null default 'BookOpen',
  color varchar(32) not null default '#3b82f6',
  order_index integer not null default 0,
  is_active boolean not null default true,
  created_at timestamptz not null default now()
);

create table public.learning_modules (
  id uuid primary key default gen_random_uuid(),
  subject_id uuid not null references public.learning_subjects(id) on delete cascade,
  title varchar(300) not null,
  description text,
  order_index integer not null default 0,
  created_at timestamptz not null default now()
);

create table public.learning_topics (
  id uuid primary key default gen_random_uuid(),
  module_id uuid not null references public.learning_modules(id) on delete cascade,
  title varchar(300) not null,
  description text,
  difficulty varchar(32) not null default 'beginner',
  order_index integer not null default 0,
  estimated_minutes integer not null default 30,
  created_at timestamptz not null default now()
);

create table public.learning_resources (
  id uuid primary key default gen_random_uuid(),
  topic_id uuid not null references public.learning_topics(id) on delete cascade,
  type varchar(32) not null default 'article',
  title varchar(500) not null,
  url varchar(1000) not null,
  source varchar(300),
  duration_minutes integer,
  order_index integer not null default 0,
  created_at timestamptz not null default now()
);

create table public.test_questions (
  id uuid primary key default gen_random_uuid(),
  test_id uuid not null references public.tests(id) on delete cascade,
  question_index integer not null,
  question_text text not null,
  options jsonb not null,
  correct_option_index integer not null,
  explanation text not null default '',
  difficulty varchar(32) not null default 'medium',
  topic_id varchar(200) not null,
  topic_title varchar(500) not null default '',
  created_at timestamptz not null default now(),
  unique (test_id, question_index)
);

create table public.test_attempts (
  id uuid primary key default gen_random_uuid(),
  test_id uuid not null references public.tests(id) on delete cascade,
  employee_id uuid not null references public.employees(id),
  question_id uuid not null references public.test_questions(id),
  selected_option_index integer not null,
  is_correct boolean not null,
  time_taken_seconds integer not null default 0,
  session_key varchar(200) not null default '',
  created_at timestamptz not null default now()
);

create table public.evaluations (
  id uuid primary key default gen_random_uuid(),
  employee_id varchar(64) not null,
  employee_name varchar(300) not null,
  department varchar(128) not null,
  subject_id varchar(200) not null,
  subject_title varchar(300) not null,
  pre_test_score integer not null default 0,
  post_test_score integer not null default 0,
  learning_gain_pct numeric(10, 2) not null default 0,
  reaction_relevance integer,
  reaction_utility integer,
  reaction_instructor integer,
  reaction_nps integer,
  reaction_comments text,
  reaction_submitted_at timestamptz,
  bloom_scores jsonb,
  bloom_submissions jsonb,
  bloom_graded jsonb,
  bloom_graded_by varchar(320),
  bloom_graded_at timestamptz,
  completion_date timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (employee_id, subject_id)
);

create table public.behavior_evaluations (
  id uuid primary key default gen_random_uuid(),
  employee_id varchar(64) not null,
  subject_id varchar(200) not null,
  evaluator_role varchar(64) not null,
  evaluator_email varchar(320) not null,
  interval_days integer not null,
  q1_demonstrates_skills integer not null,
  q2_independently_applies integer not null,
  q3_shares_learning integer not null,
  q4_solves_problems integer not null,
  q5_measurable_improvement integer not null,
  comments text,
  submitted_at timestamptz not null default now(),
  unique (employee_id, subject_id, evaluator_role, interval_days)
);

create table public.business_impacts (
  id uuid primary key default gen_random_uuid(),
  employee_id varchar(64) not null,
  subject_id varchar(200) not null,
  productivity_before integer not null,
  productivity_after integer not null,
  productivity_metric varchar(200) not null,
  quality_before integer not null,
  quality_after integer not null,
  quality_metric varchar(200) not null,
  customer_csat_before integer not null,
  customer_csat_after integer not null,
  cost_reduction numeric(12, 2) not null default 0,
  time_saved_hours numeric(12, 2) not null default 0,
  roi_score numeric(12, 2) not null default 0,
  business_impact_score integer not null,
  approved_by_pm boolean not null default false,
  approved_by_rm boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (employee_id, subject_id)
);

alter table public.resumes enable row level security;
alter table public.job_descriptions enable row level security;
alter table public.portal_settings enable row level security;
alter table public.employees enable row level security;
alter table public.tests enable row level security;
alter table public.audit_logs enable row level security;
alter table public.simulated_emails enable row level security;
alter table public.candidate_interview_data enable row level security;
alter table public.interview_questions enable row level security;
alter table public.interview_attempts enable row level security;
alter table public.candidate_sessions enable row level security;
alter table public.reset_logs enable row level security;
alter table public.learning_subjects enable row level security;
alter table public.learning_modules enable row level security;
alter table public.learning_topics enable row level security;
alter table public.learning_resources enable row level security;
alter table public.test_questions enable row level security;
alter table public.test_attempts enable row level security;
alter table public.evaluations enable row level security;
alter table public.behavior_evaluations enable row level security;
alter table public.business_impacts enable row level security;
