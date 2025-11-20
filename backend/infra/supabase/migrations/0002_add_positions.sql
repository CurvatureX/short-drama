-- Add position columns to images table for canvas persistence
alter table public.images
  add column if not exists pos_x double precision default 0,
  add column if not exists pos_y double precision default 0;

-- Add index for efficient querying
create index if not exists idx_images_positions on public.images(session_id, pos_x, pos_y);
