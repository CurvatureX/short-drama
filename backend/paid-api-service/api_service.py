"""
Paid API Service - REST API for face masking and face swapping

This service exposes the face_swap.py functionality as REST APIs.
Designed to run on CPU instances with API access to QWEN3-VL and SeeDream.
"""

import os
import sys
import json
import uuid
import time
from typing import Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uvicorn

# Add current directory to path to import face_swap
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)
sys.path.insert(0, os.path.join(current_dir, 'image-to-image'))

from face_swap import create_face_mask, apply_face_swap, swap_with_seedream
from seedream import ImageSize

# Configuration
PORT = int(os.getenv("PORT", "8000"))
HOST = os.getenv("HOST", "0.0.0.0")

# Initialize FastAPI
app = FastAPI(
    title="Paid API Service",
    description="REST API for face masking and face swapping",
    version="1.0.0"
)

# In-memory job storage
jobs = {}


class FaceMaskRequest(BaseModel):
    """Request model for face masking"""
    image_url: str
    face_index: Optional[int] = 0


class FaceSwapRequest(BaseModel):
    """Request model for face swap using pre-masked image"""
    masked_image_url: str
    target_face_url: str
    prompt: Optional[str] = None
    size: Optional[str] = None  # e.g., "2048x2048", "auto", or None


class FullFaceSwapRequest(BaseModel):
    """Request model for full face swap pipeline"""
    source_image_url: str
    target_face_url: str
    face_index: Optional[int] = 0
    prompt: Optional[str] = None
    size: Optional[str] = None


class JobStatus(BaseModel):
    """Job status response model"""
    job_id: str
    status: str  # pending, processing, completed, failed
    result_url: Optional[str] = None
    error: Optional[str] = None


def parse_image_size(size_str: Optional[str]) -> Optional[ImageSize]:
    """Parse size string to ImageSize enum"""
    if not size_str or size_str == "auto":
        return None

    # Try to find matching enum
    for size_enum in ImageSize:
        if size_enum.value == size_str:
            return size_enum

    # If not found, return None (will auto-detect)
    return None


async def process_face_mask(job_id: str, request: FaceMaskRequest):
    """Background task to create face mask"""
    try:
        jobs[job_id]['status'] = 'processing'

        result_url = create_face_mask(
            source_image_url=request.image_url,
            face_index=request.face_index
        )

        jobs[job_id]['status'] = 'completed'
        jobs[job_id]['result_url'] = result_url

    except Exception as e:
        jobs[job_id]['status'] = 'failed'
        jobs[job_id]['error'] = str(e)
        print(f"Error processing face mask job {job_id}: {e}")


async def process_face_swap(job_id: str, request: FaceSwapRequest):
    """Background task to apply face swap"""
    try:
        jobs[job_id]['status'] = 'processing'

        size = parse_image_size(request.size)

        result_url = apply_face_swap(
            masked_image_url=request.masked_image_url,
            target_face_url=request.target_face_url,
            prompt=request.prompt,
            size=size
        )

        jobs[job_id]['status'] = 'completed'
        jobs[job_id]['result_url'] = result_url

    except Exception as e:
        jobs[job_id]['status'] = 'failed'
        jobs[job_id]['error'] = str(e)
        print(f"Error processing face swap job {job_id}: {e}")


async def process_full_face_swap(job_id: str, request: FullFaceSwapRequest):
    """Background task for full face swap pipeline"""
    try:
        jobs[job_id]['status'] = 'processing'

        size = parse_image_size(request.size)

        result_url = swap_with_seedream(
            source_image_url=request.source_image_url,
            target_face_url=request.target_face_url,
            face_index=request.face_index,
            prompt=request.prompt,
            size=size
        )

        jobs[job_id]['status'] = 'completed'
        jobs[job_id]['result_url'] = result_url

    except Exception as e:
        jobs[job_id]['status'] = 'failed'
        jobs[job_id]['error'] = str(e)
        print(f"Error processing full face swap job {job_id}: {e}")


@app.get("/")
async def root():
    """Service info"""
    return {
        "service": "Paid API Service",
        "version": "1.0.0",
        "endpoints": {
            "face_mask": "/api/v1/face-mask/jobs",
            "face_swap": "/api/v1/face-swap/jobs",
            "full_pipeline": "/api/v1/full-face-swap/jobs",
            "job_status": "/api/v1/jobs/{job_id}"
        }
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    # Verify environment variables are set
    required_vars = [
        "DASHSCOPE_API_KEY",
        "ARK_API_KEY",
        "S3_BUCKET_NAME",
        "CLOUDFRONT_DOMAIN",
        "AWS_ACCESS_KEY",
        "AWS_ACCESS_SECRET"
    ]

    missing_vars = [var for var in required_vars if not os.getenv(var)]

    return {
        "status": "healthy" if not missing_vars else "degraded",
        "missing_env_vars": missing_vars if missing_vars else None
    }


@app.post("/api/v1/face-mask/jobs", response_model=JobStatus)
async def create_face_mask_job(request: FaceMaskRequest, background_tasks: BackgroundTasks):
    """
    Create a face mask job

    This endpoint:
    1. Downloads the source image
    2. Uses QWEN3-VL to detect faces
    3. Creates a black elliptical mask on the specified face
    4. Uploads the masked image to S3

    Returns job_id for status polling.
    """
    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        'status': 'pending',
        'created_at': time.time(),
        'job_type': 'face_mask'
    }

    background_tasks.add_task(process_face_mask, job_id, request)

    return JobStatus(job_id=job_id, status='pending')


@app.post("/api/v1/face-swap/jobs", response_model=JobStatus)
async def create_face_swap_job(request: FaceSwapRequest, background_tasks: BackgroundTasks):
    """
    Apply face swap to a pre-masked image

    This endpoint:
    1. Takes a masked image (with black elliptical mask on face)
    2. Uses SeeDream to reconstruct the face using target identity

    Returns job_id for status polling.
    """
    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        'status': 'pending',
        'created_at': time.time(),
        'job_type': 'face_swap'
    }

    background_tasks.add_task(process_face_swap, job_id, request)

    return JobStatus(job_id=job_id, status='pending')


@app.post("/api/v1/full-face-swap/jobs", response_model=JobStatus)
async def create_full_face_swap_job(request: FullFaceSwapRequest, background_tasks: BackgroundTasks):
    """
    Full face swap pipeline (combines face masking + face swap)

    This endpoint:
    1. Downloads the source image
    2. Uses QWEN3-VL to detect faces and create mask
    3. Uploads masked image to S3
    4. Uses SeeDream to swap face with target identity

    Returns job_id for status polling.
    """
    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        'status': 'pending',
        'created_at': time.time(),
        'job_type': 'full_face_swap'
    }

    background_tasks.add_task(process_full_face_swap, job_id, request)

    return JobStatus(job_id=job_id, status='pending')


@app.get("/api/v1/jobs/{job_id}", response_model=JobStatus)
async def get_job_status(job_id: str):
    """Get status of any job"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = jobs[job_id]
    return JobStatus(
        job_id=job_id,
        status=job['status'],
        result_url=job.get('result_url'),
        error=job.get('error')
    )


@app.get("/api/v1/face-mask/jobs/{job_id}", response_model=JobStatus)
async def get_face_mask_job_status(job_id: str):
    """Get status of a face mask job"""
    return await get_job_status(job_id)


@app.get("/api/v1/face-swap/jobs/{job_id}", response_model=JobStatus)
async def get_face_swap_job_status(job_id: str):
    """Get status of a face swap job"""
    return await get_job_status(job_id)


@app.get("/api/v1/full-face-swap/jobs/{job_id}", response_model=JobStatus)
async def get_full_face_swap_job_status(job_id: str):
    """Get status of a full face swap job"""
    return await get_job_status(job_id)


if __name__ == "__main__":
    print("=" * 80)
    print("Paid API Service Starting")
    print("=" * 80)
    print(f"Host: {HOST}")
    print(f"Port: {PORT}")
    print("=" * 80)

    uvicorn.run(app, host=HOST, port=PORT)
