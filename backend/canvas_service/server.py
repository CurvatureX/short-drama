from __future__ import annotations

import io
import logging
import os
import uuid
from typing import List, Optional
from pathlib import Path

import boto3
from botocore.client import Config
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from supabase import Client, create_client
from dotenv import load_dotenv


LOGGER = logging.getLogger("canvas_service")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# Load environment from backend/.env (preferred) and local .env as fallback
try:
    repo_backend_dir = Path(__file__).resolve().parents[1]  # .../backend
    dotenv_candidates = [
        repo_backend_dir / ".env",            # backend/.env
        Path(__file__).resolve().parent / ".env",  # backend/canvas_service/.env
    ]
    for p in dotenv_candidates:
        if p.exists():
            load_dotenv(dotenv_path=p, override=False)
except Exception:
    # Loading .env is best-effort; real env vars still work
    pass

# Normalize environment variable names so common alternates work out-of-the-box
def _coalesce_env(target: str, candidates: list[str]) -> None:
    if os.getenv(target):
        return
    for name in candidates:
        val = os.getenv(name)
        if val:
            os.environ[target] = val
            return

# AWS creds and S3 bucket
_coalesce_env("AWS_ACCESS_KEY_ID", ["AWS_ACCESS_KEY_ID", "AWS_ACCESS_KEY"])  # pragma: no cover
_coalesce_env("AWS_SECRET_ACCESS_KEY", ["AWS_SECRET_ACCESS_KEY", "AWS_ACCESS_SECRET"])  # pragma: no cover
_coalesce_env("S3_BUCKET", ["S3_BUCKET", "AWS_S3_BUCKET", "S3_BUCKET_NAME"])  # pragma: no cover

# Supabase key naming differences
_coalesce_env("SUPABASE_SERVICE_ROLE_KEY", ["SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SECRET_KEY"])  # pragma: no cover


class CreateSessionResponse(BaseModel):
    """Response payload for creating a session."""

    session_id: str


class ImageItem(BaseModel):
    key: str
    url: str
    x: float = 0.0
    y: float = 0.0


class ListImagesResponse(BaseModel):
    items: List[ImageItem]


def get_env(name: str, default: Optional[str] = None) -> str:
    value = os.getenv(name, default)
    if value is None:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def create_s3_client():
    return boto3.client("s3", config=Config(signature_version="s3v4"))


def create_supabase() -> Client:
    url = get_env("SUPABASE_URL")
    key = get_env("SUPABASE_SERVICE_ROLE_KEY")
    return create_client(url, key)


S3_BUCKET = get_env("S3_BUCKET", default=os.getenv("AWS_S3_BUCKET"))
PRESIGN_EXPIRY = int(os.getenv("PRESIGN_EXPIRY_SECONDS", "3600"))
CLOUDFRONT_DOMAIN = os.getenv("CLOUDFRONT_DOMAIN", "https://d3bg7alr1qwred.cloudfront.net")

s3 = create_s3_client()
sb = create_supabase()

app = FastAPI(title="Canvas Service", version="0.2.0")

# CORS
cors_origins_env = os.getenv("CORS_ORIGINS")
if cors_origins_env:
    allowed = [o.strip() for o in cors_origins_env.split(",") if o.strip()]
else:
    allowed = ["*"]  # local/dev convenience

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health_check():
    """Health check endpoint for container orchestration."""
    return {"status": "healthy", "service": "canvas-service"}


def ensure_session_exists(session_id: str) -> None:
    try:
        res = sb.table("sessions").select("id").eq("id", session_id).single().execute()
        if not res.data:
            raise HTTPException(status_code=400, detail="Invalid or expired session_id")
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("Session lookup failed: %s", exc)
        raise HTTPException(status_code=500, detail="Session lookup failed")


@app.post("/session", response_model=CreateSessionResponse)
def create_session() -> CreateSessionResponse:
    """Create a new canvas session in Supabase and return its ID."""
    session_id = str(uuid.uuid4())
    try:
        sb.table("sessions").insert({"id": session_id}).execute()
        LOGGER.info("Created session %s", session_id)
        return CreateSessionResponse(session_id=session_id)
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("Create session failed: %s", exc)
        raise HTTPException(status_code=500, detail="Create session failed")


@app.post("/upload")
async def upload_image(
    session_id: str = Form(...),
    file: UploadFile = File(...),
):
    """Upload an image to S3 under the session prefix and return a presigned URL.

    Also records image metadata in Supabase Postgres.
    """
    # Validate session through Supabase
    ensure_session_exists(session_id)

    # Basic validation
    content_type = file.content_type or "application/octet-stream"
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image uploads are supported")

    # Determine file extension
    ext = ""
    filename = file.filename or "upload"
    if "." in filename:
        ext = filename.split(".")[-1].lower()
        if len(ext) > 6:
            ext = ""

    # S3 object key under images/{session_id}/
    key = (
        f"images/{session_id}/{uuid.uuid4()}.{ext}" if ext else f"images/{session_id}/{uuid.uuid4()}"
    )

    try:
        data = await file.read()
        bio = io.BytesIO(data)
        s3.upload_fileobj(
            bio,
            S3_BUCKET,
            key,
            ExtraArgs={"ContentType": content_type},
        )

        # Persist metadata to Supabase
        sb.table("images").insert(
            {
                "session_id": session_id,
                "s3_key": key,
                "content_type": content_type,
                "size": len(data),
            }
        ).execute()

        # Return CloudFront URL instead of S3 presigned URL for better performance
        url = f"{CLOUDFRONT_DOMAIN}/{key}"
        LOGGER.info("Uploaded %s to s3://%s/%s (CloudFront: %s)", filename, S3_BUCKET, key, url)
        return {"key": key, "url": url, "x": 0.0, "y": 0.0}
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("Upload failed: %s", exc)
        raise HTTPException(status_code=500, detail="Upload failed") from exc


@app.get("/images", response_model=ListImagesResponse)
def list_images(session_id: str) -> ListImagesResponse:
    """List images for a session from Supabase metadata and return CloudFront URLs."""
    ensure_session_exists(session_id)

    try:
        res = sb.table("images").select("s3_key, pos_x, pos_y").eq("session_id", session_id).order("created_at").execute()
        items: List[ImageItem] = []
        for row in (res.data or []):
            key = row["s3_key"]
            # Use CloudFront URL for better performance
            url = f"{CLOUDFRONT_DOMAIN}/{key}"
            items.append(ImageItem(
                key=key,
                url=url,
                x=row.get("pos_x", 0.0),
                y=row.get("pos_y", 0.0)
            ))
        return ListImagesResponse(items=items)
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("List images failed: %s", exc)
        raise HTTPException(status_code=500, detail="List images failed") from exc


class AddImageRequest(BaseModel):
    session_id: str
    s3_key: str
    x: float = 0.0
    y: float = 0.0


@app.post("/add-image")
def add_image(request: AddImageRequest) -> ImageItem:
    """
    Add an existing S3 image to a session.

    This is used when generated images (from Qwen/Camera Angle) need to be
    added to the session so they persist across page refreshes.
    """
    ensure_session_exists(request.session_id)

    try:
        # Check if the S3 object exists
        try:
            head_response = s3.head_object(Bucket=S3_BUCKET, Key=request.s3_key)
            content_type = head_response.get("ContentType", "image/png")
            size = head_response.get("ContentLength", 0)
        except Exception as e:
            LOGGER.error("S3 object not found: %s", request.s3_key)
            raise HTTPException(status_code=404, detail=f"S3 object not found: {request.s3_key}")

        # Check if this image is already in the session
        existing = sb.table("images").select("id").eq("session_id", request.session_id).eq("s3_key", request.s3_key).execute()
        if existing.data:
            LOGGER.info("Image already exists in session, skipping: %s", request.s3_key)
        else:
            # Add to Supabase images table with position
            sb.table("images").insert({
                "session_id": request.session_id,
                "s3_key": request.s3_key,
                "content_type": content_type,
                "size": size,
                "pos_x": request.x,
                "pos_y": request.y,
            }).execute()
            LOGGER.info("Added existing image to session %s: %s at (%f, %f)", request.session_id, request.s3_key, request.x, request.y)

        # Use CloudFront URL for better performance
        url = f"{CLOUDFRONT_DOMAIN}/{request.s3_key}"

        return ImageItem(key=request.s3_key, url=url, x=request.x, y=request.y)

    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("Add image failed: %s", exc)
        raise HTTPException(status_code=500, detail="Add image failed") from exc


class UpdatePositionRequest(BaseModel):
    session_id: str
    s3_key: str
    x: float
    y: float


@app.post("/update-position")
def update_position(request: UpdatePositionRequest) -> dict:
    """
    Update the position of an image in the canvas.

    This is called after every drag operation to persist the new position.
    """
    ensure_session_exists(request.session_id)

    # Retry logic for transient network errors
    max_retries = 3
    last_error = None

    for attempt in range(max_retries):
        try:
            # Recreate Supabase client on retry to get a fresh connection
            if attempt > 0:
                global sb
                sb = create_supabase()
                LOGGER.info("Retrying update_position (attempt %d/%d)", attempt + 1, max_retries)

            # Update the position in Supabase
            result = sb.table("images").update({
                "pos_x": request.x,
                "pos_y": request.y,
            }).eq("session_id", request.session_id).eq("s3_key", request.s3_key).execute()

            if not result.data:
                raise HTTPException(status_code=404, detail="Image not found in session")

            LOGGER.info("Updated position for %s in session %s to (%f, %f)",
                       request.s3_key, request.session_id, request.x, request.y)

            return {"success": True, "s3_key": request.s3_key, "x": request.x, "y": request.y}

        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            # Check if it's a retryable error (network/connection issues)
            error_str = str(exc).lower()
            if "disconnect" in error_str or "connection" in error_str or "timeout" in error_str:
                if attempt < max_retries - 1:
                    LOGGER.warning("Transient error on attempt %d: %s", attempt + 1, exc)
                    continue  # Retry
            # Non-retryable error or max retries reached
            LOGGER.exception("Update position failed after %d attempts: %s", attempt + 1, exc)
            raise HTTPException(status_code=500, detail="Update position failed") from exc

    # Should not reach here, but just in case
    raise HTTPException(status_code=500, detail="Update position failed") from last_error


class DeleteImageRequest(BaseModel):
    session_id: str
    s3_key: str


@app.delete("/delete-image")
def delete_image(request: DeleteImageRequest) -> dict:
    """
    Delete an image from both S3 and Supabase.

    This removes the image file from S3 storage and its metadata from the database.
    """
    ensure_session_exists(request.session_id)

    try:
        # Delete from S3
        try:
            s3.delete_object(Bucket=S3_BUCKET, Key=request.s3_key)
            LOGGER.info("Deleted from S3: s3://%s/%s", S3_BUCKET, request.s3_key)
        except Exception as s3_error:
            LOGGER.warning("Failed to delete from S3 (may not exist): %s", s3_error)
            # Continue anyway - we still want to clean up the database

        # Delete from Supabase
        result = sb.table("images").delete().eq("session_id", request.session_id).eq("s3_key", request.s3_key).execute()

        if not result.data:
            LOGGER.warning("Image not found in database: %s", request.s3_key)
        else:
            LOGGER.info("Deleted from database: %s", request.s3_key)

        return {"success": True, "s3_key": request.s3_key, "message": "Image deleted successfully"}

    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("Delete image failed: %s", exc)
        raise HTTPException(status_code=500, detail="Delete image failed") from exc


@app.get("/")
def health() -> dict:
    return {"status": "ok"}
