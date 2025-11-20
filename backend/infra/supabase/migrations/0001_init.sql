-- Enable extensions for UUID generation if not already present
create extension if not exists pgcrypto;
create extension if not exists "uuid-ossp";

-- Sessions table: one row per canvas session
create table if not exists public.sessions (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now()
);

-- Images metadata table: objects live in S3, key stored here
create table if not exists public.images (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references public.sessions(id) on delete cascade,
  s3_key text not null,
  content_type text,
  size bigint,
  created_at timestamptz not null default now()
);

create index if not exists idx_images_session_id on public.images(session_id);
create index if not exists idx_images_created_at on public.images(created_at);

-- RLS left off; backend uses service role key

