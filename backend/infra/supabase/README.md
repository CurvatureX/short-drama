# Supabase Schema & Migrations

This folder contains the database schema and SQL migrations for the Canvas Service.

Overview:
- `sessions` table: stores canvas sessions (id as UUID, created_at)
- `images` table: stores image metadata per session (S3 key, content type, size, created_at)

## Structure
- `migrations/0001_init.sql` — create extensions and tables with indexes
- `schema.sql` — current schema snapshot for reference/review

## Applying Migrations
You can apply the migrations in one of two ways:

1) Supabase SQL Editor
- Open the SQL editor in the Supabase dashboard
- Paste and run the contents of each migration file in order

2) Supabase CLI (recommended for automation)
```bash
# Ensure you are authenticated: supabase login
# Start a linked project or set connection env vars
cd backend/infra/supabase
supabase db push
```

Note: RLS can be enabled later to expose only what you need to clients. The backend uses the service role key and bypasses RLS by design.

## Scripts

- `scripts/bootstrap.sh` — links the folder to a Supabase project (if `SUPABASE_PROJECT_REF` is set) and pushes migrations via CLI.
  - Usage:
    ```bash
    export SUPABASE_PROJECT_REF=your-project-ref
    bash backend/infra/supabase/scripts/bootstrap.sh
    ```
- `scripts/verify.py` — simple Python script to verify Supabase connectivity and basic CRUD on `sessions`.
  - Usage:
    ```bash
    cd backend/infra/supabase/scripts
    export SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=...
    pip install supabase
    python verify.py
    ```
