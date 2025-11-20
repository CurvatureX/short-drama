#!/usr/bin/env bash
set -euo pipefail

echo "==> Supabase bootstrap"

if ! command -v supabase >/dev/null 2>&1; then
  echo "ERROR: supabase CLI not found. Install: https://supabase.com/docs/guides/cli" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
SUPA_DIR="$ROOT_DIR/backend/infra/supabase"

cd "$SUPA_DIR"

echo "Working dir: $(pwd)"

if [[ -n "${SUPABASE_PROJECT_REF:-}" ]]; then
  echo "Linking to project ref: $SUPABASE_PROJECT_REF"
  supabase link --project-ref "$SUPABASE_PROJECT_REF" || true
else
  echo "SUPABASE_PROJECT_REF not set. You can set it to run 'supabase link'."
fi

echo "Pushing migrations (0001_init.sql)..."
supabase db push

echo "Done. You can verify with: supabase db remote commit --dry-run"

