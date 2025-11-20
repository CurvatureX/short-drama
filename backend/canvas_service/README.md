# Canvas Service (FastAPI)

FastAPI backend that issues per-canvas sessions and stores image binaries in AWS S3. Session and image metadata are stored in Supabase Postgres. Designed to support the `frontend/image-edit-canvas` Next.js app.

## Features
- Create a new session: `POST /session`
- Upload an image bound to a session: `POST /upload`
- List session images with S3 signed URLs: `GET /images?session_id=...`
- CORS enabled for local dev

## Requirements
- Python 3.10+
- AWS credentials with S3 permissions

## Environment Variables
- `SUPABASE_URL` (required): Your Supabase project URL
- `SUPABASE_SERVICE_ROLE_KEY` (required): Service role key (server-side only). Also accepts `SUPABASE_SECRET_KEY`.
- `CORS_ORIGINS` (optional): Comma-separated list of origins allowed by CORS. Defaults to `*` for local dev.
- `PRESIGN_EXPIRY_SECONDS` (optional): Expiration for presigned GET URLs. Default: `3600`.
- `S3_BUCKET` (required): S3 bucket name where files are stored. Also accepts `AWS_S3_BUCKET` or `S3_BUCKET_NAME`.
- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION` (required unless using instance/profile credentials).
  - Also accepts `AWS_ACCESS_KEY` and `AWS_ACCESS_SECRET`.

You can copy `.env.example` to `.env` and set values before running (load into your environment before start).

## Install & Run (local)

1) Fill in `backend/.env` (copy `backend/.env.example`). Example keys:
- `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`
- `S3_BUCKET`, `AWS_DEFAULT_REGION` (+ AWS credentials or profile)

2) Start the API
```bash
cd backend/canvas_service
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn server:app --reload --host 0.0.0.0 --port 9000
```

The service automatically loads `backend/.env`. Runs at `http://localhost:9000`.

## Docker

Build and run via docker-compose:

```bash
cd backend/infra
# Ensure backend/.env has required values, then:
docker compose up --build
```

Service becomes available on `http://localhost:9000`.

## API

### Create Session
- `POST /session`
- Response: `{ "session_id": "uuid" }`

### Upload Image
- `POST /upload`
- Form fields: `session_id` (string), `file` (binary)
- Response: `{ "key": "session/uuid.png", "url": "https://..." }` (S3 presigned GET)

### List Images
- `GET /images?session_id=...`
- Response: `{ "items": [{ "key": "...", "url": "..." }] }`

## Notes
- Sessions and image metadata are stored in Supabase Postgres (see `backend/infra/supabase`).
- Uploaded objects are stored under the key prefix `images/{session_id}/` in the S3 bucket.
- Ensure the S3 bucket exists and credentials are configured.

## Database & Migrations
- Migrations for Supabase (Postgres) tables live in `backend/infra/supabase/migrations`.
- Apply using the Supabase SQL editor or `supabase db push` via CLI. See `backend/infra/supabase/README.md`.

## Tests

Install dev requirements and run pytest from this folder:

```bash
cd backend/canvas_service
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
pytest -q
```
