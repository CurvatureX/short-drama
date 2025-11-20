#!/usr/bin/env python3
"""Simple connectivity check against Supabase.

Requires env vars:
  SUPABASE_URL
  SUPABASE_SERVICE_ROLE_KEY

Usage:
  python verify.py
"""
from __future__ import annotations

import os
import sys
from typing import Any

try:
    from supabase import Client, create_client
except Exception as exc:  # noqa: BLE001
    print("supabase-py not installed. pip install supabase", file=sys.stderr)
    raise


def get_env(name: str) -> str:
    v = os.getenv(name)
    if not v:
        print(f"Missing env var: {name}", file=sys.stderr)
        sys.exit(1)
    return v


def main() -> None:
    url = get_env("SUPABASE_URL")
    key = get_env("SUPABASE_SERVICE_ROLE_KEY")
    sb: Client = create_client(url, key)

    # Try query sessions table
    print("Querying sessions (limit 1)...")
    res: Any = sb.table("sessions").select("id, created_at").limit(1).execute()
    print("OK. Sample:", res.data)

    # Try creating a throwaway session and deleting it
    from uuid import uuid4

    sid = str(uuid4())
    print("Inserting test session:", sid)
    sb.table("sessions").insert({"id": sid}).execute()
    print("Selecting test session...")
    res = sb.table("sessions").select("id").eq("id", sid).single().execute()
    assert res.data["id"] == sid
    print("Deleting test session...")
    sb.table("sessions").delete().eq("id", sid).execute()
    print("Supabase connectivity verified.")


if __name__ == "__main__":
    main()

