import io
import os
import sys
import pathlib
from typing import Any, Dict, List

import pytest
from fastapi.testclient import TestClient


# Ensure server module is importable
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class FakeS3:
    def __init__(self) -> None:
        self.objects: Dict[str, bytes] = {}

    def upload_fileobj(self, bio: io.BytesIO, bucket: str, key: str, ExtraArgs: Dict[str, Any] | None = None) -> None:  # noqa: N803
        self.objects[key] = bio.getvalue()

    def generate_presigned_url(self, ClientMethod: str, Params: Dict[str, Any], ExpiresIn: int) -> str:  # noqa: N803
        return f"https://example.com/{Params['Bucket']}/{Params['Key']}?exp={ExpiresIn}"


class _Res:
    def __init__(self, data: Any) -> None:
        self.data = data


class FakeQuery:
    def __init__(self, table: str, db: "FakeSupabase") -> None:
        self.table = table
        self.db = db
        self._filters: Dict[str, Any] = {}
        self._single = False
        self._order: str | None = None

    def select(self, *_args: str) -> "FakeQuery":
        return self

    def eq(self, field: str, value: Any) -> "FakeQuery":
        self._filters[field] = value
        return self

    def single(self) -> "FakeQuery":
        self._single = True
        return self

    def order(self, field: str) -> "FakeQuery":
        self._order = field
        return self

    def limit(self, _n: int) -> "FakeQuery":
        return self

    def execute(self) -> _Res:  # noqa: C901
        if self.table == "sessions":
            if self._filters:
                sid = self._filters.get("id")
                rec = self.db.sessions.get(sid)
                if self._single:
                    return _Res(rec)
                return _Res([rec] if rec else [])
            else:
                return _Res(list(self.db.sessions.values()))
        elif self.table == "images":
            items = [r for r in self.db.images if all(r.get(k) == v for k, v in self._filters.items())]
            if self._order:
                items.sort(key=lambda x: x.get(self._order))
            return _Res(items)
        else:
            return _Res([])


class FakeTable:
    def __init__(self, name: str, db: "FakeSupabase") -> None:
        self.name = name
        self.db = db
        self._query = FakeQuery(name, db)

    # query ops
    def select(self, *args: str) -> FakeQuery:  # noqa: ARG002
        return FakeQuery(self.name, self.db)

    def eq(self, field: str, value: Any) -> FakeQuery:
        return FakeQuery(self.name, self.db).eq(field, value)

    def order(self, field: str) -> FakeQuery:
        return FakeQuery(self.name, self.db).order(field)

    def limit(self, n: int) -> FakeQuery:
        return FakeQuery(self.name, self.db).limit(n)

    def insert(self, row: Dict[str, Any]) -> _Res:
        if self.name == "sessions":
            self.db.sessions[row["id"]] = {"id": row["id"], "created_at": "now"}
            return _Res(row)
        elif self.name == "images":
            self.db.images.append({**row, "created_at": len(self.db.images)})
            return _Res(row)
        return _Res(None)

    def delete(self) -> "FakeTableDelete":
        return FakeTableDelete(self.name, self.db)

    def execute(self) -> _Res:
        return _Res(None)


class FakeTableDelete:
    def __init__(self, name: str, db: "FakeSupabase") -> None:
        self.name = name
        self.db = db
        self._filters: Dict[str, Any] = {}

    def eq(self, field: str, value: Any) -> "FakeTableDelete":
        self._filters[field] = value
        return self

    def execute(self) -> _Res:
        if self.name == "sessions":
            sid = self._filters.get("id")
            if sid in self.db.sessions:
                del self.db.sessions[sid]
        elif self.name == "images":
            self.db.images = [r for r in self.db.images if all(r.get(k) != v for k, v in self._filters.items())]
        return _Res(None)


class FakeSupabase:
    def __init__(self) -> None:
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.images: List[Dict[str, Any]] = []

    def table(self, name: str) -> FakeTable:
        return FakeTable(name, self)


@pytest.fixture(autouse=True)
def env_setup(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SUPABASE_URL", "http://local.test")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")
    monkeypatch.setenv("S3_BUCKET", "test-bucket")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")


@pytest.fixture()
def app_with_fakes():
    import importlib

    server = importlib.import_module("server")
    server.sb = FakeSupabase()
    server.s3 = FakeS3()
    client = TestClient(server.app)
    return server, client


def test_create_session(app_with_fakes):
    server, client = app_with_fakes
    r = client.post("/session")
    assert r.status_code == 200
    sid = r.json()["session_id"]
    assert isinstance(sid, str) and len(sid) > 0
    # Ensure session persisted in fake DB
    assert sid in server.sb.sessions


def test_upload_and_list_images(app_with_fakes):
    server, client = app_with_fakes

    # Create session first
    sid = client.post("/session").json()["session_id"]

    # Upload a small fake PNG
    png_bytes = b"\x89PNG\r\n\x1a\n" + b"0" * 16
    files = {"file": ("test.png", io.BytesIO(png_bytes), "image/png")}
    data = {"session_id": sid}
    ur = client.post("/upload", files=files, data=data)
    assert ur.status_code == 200
    up = ur.json()
    assert "key" in up and "url" in up
    assert up["key"].startswith(f"images/{sid}/")
    # Ensure bytes stored in fake S3
    assert up["key"] in server.s3.objects
    assert server.s3.objects[up["key"]] == png_bytes

    # List images
    lr = client.get(f"/images?session_id={sid}")
    assert lr.status_code == 200
    items = lr.json()["items"]
    assert len(items) == 1
    assert items[0]["key"] == up["key"]
