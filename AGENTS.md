# Repository Guidelines

## Project Structure & Module Organization
- `backend/orchestrator/` — FastAPI service that queues GPU jobs (entry: `orchestrator_api.py`, AWS helpers in `aws/`, docs and helper scripts alongside).
- `backend/comfyui-api-service/` — Adapter that mirrors ComfyUI APIs and an SQS worker; includes service scripts and docs.
- `backend/generator/` — FastAPI generation server and CLI (`server.py`, `cli.py`, `pyproject.toml`).
- `backend/infra/` — Infrastructure docs and CDK guidance.
- `frontend/` — Placeholder for the web UI (no code yet).
- `playground/` — Experiments and media samples; not production code.

## Build, Test, and Development Commands
- Orchestrator (local):
  - `cd backend/orchestrator && python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt`
  - Run API: `python orchestrator_api.py` (serves on `http://localhost:8080`)
  - Env: set in `backend/.env` (e.g., `SQS_QUEUE_URL`, `DYNAMODB_TABLE`, `GPU_INSTANCE_ID`).
- Generator (local):
  - Quick run: `python backend/generator/server.py` (FastAPI on port 8000)
  - Optional install: `pip install -e backend/generator` then `server` (from `project.scripts`).
- Adapter: see `backend/comfyui-api-service/README.md` for service/unit test scripts.
- Smoke tests (orchestrator helpers): `python backend/orchestrator/test_ec2.py` (list), `test_start.py`, `test_stop.py`.

## Coding Style & Naming Conventions
- Python: PEP 8, 4‑space indent, type hints for new/changed code.
- Names: modules/functions `snake_case`, classes `PascalCase`, constants `UPPER_SNAKE_CASE`.
- Prefer `logging` over `print`; include concise docstrings (`"""..."""`).

## Testing Guidelines
- Place lightweight scripts near modules (current pattern) or add pytest tests as `tests/test_*.py` per service.
- Cover new logic with unit tests; include example payloads and AWS stubs where relevant.
- No strict coverage threshold yet; aim for meaningful coverage on new code.

## Commit & Pull Request Guidelines
- Commits: imperative mood, concise summary, include scope (e.g., `orchestrator:`). Example: `orchestrator: add DynamoDB status query`.
- PRs: clear description, linked issues, steps to run locally, config/env notes; attach logs or screenshots for API/UI changes.
- For changes touching AWS: list required env vars, resources created/updated, and rollback notes.

## Security & Configuration Tips
- Do not commit credentials. Use `backend/.env` (git-ignored). Example keys: `AWS_ACCESS_KEY`, `AWS_ACCESS_SECRET`, `AWS_DEFAULT_REGION`.
- Validate `SQS_QUEUE_URL`, `DYNAMODB_TABLE`, and `GPU_INSTANCE_ID` before running orchestrator.
