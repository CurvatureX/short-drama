"""
Orchestrator Service - The main entry point for GPU task orchestration.

This service acts as a facade for clients, handling all API requests,
converting them to SQS tasks, and managing GPU instance lifecycle.
"""

import os
import json
import uuid
import time
from typing import Optional, Literal
from dotenv import load_dotenv
from pathlib import Path

import boto3
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import uvicorn

from aws.ec2 import start_instance, list_ec2_instances, get_instance_ip
from aws.sqs import send_message
from aws.dynamodb import create_task, get_task_status
import asyncio
from contextlib import asynccontextmanager

# Load environment variables
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path)

# Configuration
AWS_REGION = os.getenv('AWS_DEFAULT_REGION', 'us-east-1')
SQS_QUEUE_URL = os.getenv('SQS_QUEUE_URL', '')
DYNAMODB_TABLE = os.getenv('DYNAMODB_TABLE', 'task_store')
GPU_INSTANCE_ID = os.getenv('GPU_INSTANCE_ID', 'i-0f0f6fd680921de5f')
S3_BUCKET_NAME = os.getenv('S3_BUCKET_NAME', 'short-drama-assets')

# CPU Task Configuration
CPU_QUEUE_URL = os.getenv('CPU_QUEUE_URL', 'https://sqs.us-east-1.amazonaws.com/982081090398/cpu_tasks_queue')
CPU_TASK_TYPES = {
    'face_mask': '/api/v1/face-mask/jobs',
    'face_swap': '/api/v1/face-swap/jobs',
    'full_face_swap': '/api/v1/full-face-swap/jobs'
}

# Global state for GPU instance IP (refreshed periodically)
gpu_instance_ip = {"current_ip": None, "last_updated": 0}
IP_REFRESH_INTERVAL = 300  # Refresh IP every 5 minutes


async def refresh_gpu_ip():
    """Background task to periodically refresh GPU instance IP."""
    while True:
        try:
            ip = get_instance_ip(GPU_INSTANCE_ID, AWS_REGION)
            if ip != gpu_instance_ip["current_ip"]:
                print(f"GPU instance IP updated: {gpu_instance_ip['current_ip']} -> {ip}")
                gpu_instance_ip["current_ip"] = ip
            gpu_instance_ip["last_updated"] = time.time()
        except Exception as e:
            print(f"Error refreshing GPU IP: {e}")

        await asyncio.sleep(IP_REFRESH_INTERVAL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup and shutdown tasks."""
    # Startup: Get initial GPU IP and start background refresh task
    print("Starting Orchestrator Service...")
    print(f"AWS Region: {AWS_REGION}")
    print(f"SQS Queue: {SQS_QUEUE_URL}")
    print(f"DynamoDB Table: {DYNAMODB_TABLE}")
    print(f"GPU Instance: {GPU_INSTANCE_ID}")

    try:
        initial_ip = get_instance_ip(GPU_INSTANCE_ID, AWS_REGION)
        gpu_instance_ip["current_ip"] = initial_ip
        gpu_instance_ip["last_updated"] = time.time()
        print(f"Initial GPU instance IP: {initial_ip}")
    except Exception as e:
        print(f"Warning: Could not get initial GPU IP: {e}")

    # Start background IP refresh task
    refresh_task = asyncio.create_task(refresh_gpu_ip())

    yield

    # Shutdown: Cancel background task
    refresh_task.cancel()
    try:
        await refresh_task
    except asyncio.CancelledError:
        pass
    print("Orchestrator Service shut down")


# Initialize FastAPI
app = FastAPI(
    lifespan=lifespan,
    title="GPU Task Orchestrator",
    description="Cost-optimized async task processing system for GPU workloads",
    version="1.0.0"
)

# Add CORS middleware to allow frontend access
# Read allowed origins from environment variable (comma-separated)
cors_origins_env = os.getenv("CORS_ORIGINS")
if cors_origins_env:
    allowed_origins = [o.strip() for o in cors_origins_env.split(",") if o.strip()]
else:
    # Default to localhost for development
    allowed_origins = ["http://localhost:3000", "http://127.0.0.1:3000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],  # Allow all HTTP methods
    allow_headers=["*"],  # Allow all headers
)

# ==================== Request/Response Models ====================

class CameraAngleRequest(BaseModel):
    image_url: str
    prompt: Optional[str] = None
    vertical: Literal[-2, -1, 0, 1, 2] = 0
    horizontal: Literal[-2, -1, 0, 1, 2] = 0
    zoom: Literal[-1, 0, 1] = 0
    seed: Optional[int] = None
    steps: Optional[int] = 8

class ImageEditRequest(BaseModel):
    image_url: str
    prompt: str
    image2_url: Optional[str] = None
    image3_url: Optional[str] = None
    seed: Optional[int] = None
    steps: Optional[int] = 4
    cfg: Optional[float] = 1.0
    sampler_name: Optional[str] = "sa_solver"
    scheduler: Optional[str] = "beta"
    denoise: Optional[float] = 1.0

class FaceMaskRequest(BaseModel):
    image_url: str
    face_position_prompt: Optional[str] = None
    face_index: Optional[int] = 0

class FullFaceSwapRequest(BaseModel):
    source_image_url: str
    target_face_url: str
    model: Optional[str] = "seedream"
    face_position_prompt: Optional[str] = None
    expression_prompt: Optional[str] = None
    face_index: Optional[int] = 0
    size: Optional[str] = None
    skip_mask: Optional[bool] = False  # If True, source_image_url is already masked

class JobResponse(BaseModel):
    job_id: str
    status: str
    result_url: Optional[str] = None
    error: Optional[str] = None

# ==================== Helper Functions ====================

def ensure_gpu_running():
    """
    Check if GPU instance is running, start it if stopped.

    Business Rule: The orchestrator must start the GPU instance
    when tasks are submitted, ensuring it's available to process work.
    """
    try:
        instances = list_ec2_instances(
            region=AWS_REGION,
            filters=[{'Name': 'instance-id', 'Values': [GPU_INSTANCE_ID]}]
        )

        if not instances:
            print(f"Warning: GPU instance {GPU_INSTANCE_ID} not found")
            return

        instance = instances[0]
        state = instance['State']

        print(f"GPU instance {GPU_INSTANCE_ID} state: {state}")

        if state == 'stopped':
            print(f"Starting GPU instance {GPU_INSTANCE_ID}...")
            start_instance(GPU_INSTANCE_ID, AWS_REGION)
        elif state in ('running', 'pending'):
            print(f"GPU instance already {state}, no action needed")
        else:
            print(f"GPU instance in unexpected state: {state}")

    except Exception as e:
        print(f"Error checking/starting GPU instance: {e}")
        # Don't fail the request - task is already queued

def submit_task(api_path: str, request_body: dict) -> str:
    """
    Submit a task to the processing queue.

    This is the core orchestration logic:
    1. Generate unique task_id
    2. Write PENDING status to DynamoDB
    3. Send task message to SQS
    4. Ensure GPU instance is running
    5. Return task_id immediately

    Args:
        api_path: The ComfyUI API endpoint path (e.g., "/api/v1/camera-angle/jobs")
        request_body: The original request payload as dict

    Returns:
        task_id: Unique identifier for tracking this task
    """
    # Step 1: Generate task ID
    task_id = str(uuid.uuid4())

    # Step 2: Write to DynamoDB with PENDING status
    try:
        create_task(
            table_name=DYNAMODB_TABLE,
            task_id=task_id,
            job_type=api_path,
            region=AWS_REGION
        )
    except Exception as e:
        print(f"Error writing to DynamoDB: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create task in database: {str(e)}"
        )

    # Step 3: Send message to SQS
    message_body = {
        "task_id": task_id,
        "api_path": api_path,
        "request_body": request_body
    }

    try:
        send_message(
            queue_url=SQS_QUEUE_URL,
            message_body=json.dumps(message_body),
            region=AWS_REGION
        )
    except Exception as e:
        print(f"Error sending to SQS: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to queue task: {str(e)}"
        )

    # Step 4: Ensure GPU is running (non-blocking, best effort)
    ensure_gpu_running()

    return task_id

# ==================== API Endpoints ====================

@app.get("/")
async def root():
    """API root with service information"""
    return {
        "service": "GPU Task Orchestrator",
        "version": "1.0.0",
        "description": "Cost-optimized async GPU task processing",
        "endpoints": {
            "camera_angle": "/api/v1/camera-angle/jobs",
            "qwen_image_edit": "/api/v1/qwen-image-edit/jobs",
            "job_status": "/api/v1/jobs/{job_id}",
            "health": "/health"
        }
    }

@app.get("/health")
async def health_check():
    """
    Health check endpoint.

    This checks the orchestrator itself, not the GPU instance.
    The GPU instance is ephemeral and may be stopped.
    """
    # Check if we can connect to DynamoDB
    try:
        # Simple connectivity check
        dynamodb = boto3.client('dynamodb', region_name=AWS_REGION)
        dynamodb.describe_table(TableName=DYNAMODB_TABLE)
        db_status = "healthy"
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"

    # Check if we can connect to SQS
    try:
        sqs = boto3.client('sqs', region_name=AWS_REGION)
        sqs.get_queue_attributes(QueueUrl=SQS_QUEUE_URL, AttributeNames=['All'])
        queue_status = "healthy"
    except Exception as e:
        queue_status = f"unhealthy: {str(e)}"

    overall_healthy = db_status == "healthy" and queue_status == "healthy"

    return {
        "status": "healthy" if overall_healthy else "unhealthy",
        "message": "Orchestrator is running" if overall_healthy else "Orchestrator has issues",
        "components": {
            "dynamodb": db_status,
            "sqs": queue_status
        }
    }


@app.get("/api/v1/health")
async def health_check_v1():
    """
    Health check endpoint for API v1.

    Alias for /health to support ALB routing with /api/v1 prefix.
    """
    return await health_check()


@app.get("/debug/gpu-instance")
async def get_gpu_instance_info():
    """
    Debug endpoint to check GPU instance information.

    Returns current GPU instance IP and last refresh time.
    """
    return {
        "instance_id": GPU_INSTANCE_ID,
        "current_ip": gpu_instance_ip["current_ip"],
        "last_updated": gpu_instance_ip["last_updated"],
        "last_updated_ago": f"{int(time.time() - gpu_instance_ip['last_updated'])}s ago" if gpu_instance_ip["last_updated"] > 0 else "never"
    }

# ==================== Camera Angle API ====================

@app.post("/api/v1/camera-angle/jobs", response_model=JobResponse, status_code=202)
async def create_camera_angle_job(request: CameraAngleRequest):
    """
    Submit a camera angle transformation job.

    This endpoint returns within 1 second with a 202 Accepted response.
    Clients should poll GET /api/v1/jobs/{job_id} for status updates.
    """
    task_id = submit_task(
        api_path="/api/v1/camera-angle/jobs",
        request_body=request.dict()
    )

    return JobResponse(
        job_id=task_id,
        status="pending",
        result_url=None,
        error=None
    )

# ==================== Qwen Image Edit API ====================

@app.post("/api/v1/qwen-image-edit/jobs", response_model=JobResponse, status_code=202)
async def create_qwen_image_edit_job(request: ImageEditRequest):
    """
    Submit a Qwen image editing job.

    This endpoint returns within 1 second with a 202 Accepted response.
    Clients should poll GET /api/v1/jobs/{job_id} for status updates.
    """
    task_id = submit_task(
        api_path="/api/v1/qwen-image-edit/jobs",
        request_body=request.dict()
    )

    return JobResponse(
        job_id=task_id,
        status="pending",
        result_url=None,
        error=None
    )

# ==================== CPU Tasks (Face Mask & Face Swap) ====================

@app.post("/api/v1/face-mask/tasks", response_model=JobResponse, status_code=202)
async def create_face_mask_task(request: FaceMaskRequest):
    """
    Submit a face mask task (CPU task).

    This endpoint returns within 1 second with a 202 Accepted response.
    Clients should poll GET /api/v1/jobs/{job_id} for status updates.
    """
    if not CPU_QUEUE_URL:
        raise HTTPException(
            status_code=500,
            detail="CPU_QUEUE_URL not configured"
        )

    # Generate task ID
    task_id = str(uuid.uuid4())

    try:
        # Create task record in DynamoDB
        create_task(
            table_name=DYNAMODB_TABLE,
            task_id=task_id,
            job_type='/api/v1/face-mask/jobs',
            region=AWS_REGION,
            initial_status='pending'
        )

        # Send message to CPU SQS queue
        message_body = json.dumps({
            'task_id': task_id,
            'task_type': 'face_mask',
            'api_path': '/api/v1/face-mask/jobs',
            'request_body': request.dict()
        })

        send_message(
            queue_url=CPU_QUEUE_URL,
            message_body=message_body,
            region=AWS_REGION
        )

        print(f"✓ Submitted face mask task {task_id}")

        return JobResponse(
            job_id=task_id,
            status="pending",
            result_url=None,
            error=None
        )

    except Exception as e:
        print(f"✗ Error submitting face mask task: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to submit task: {str(e)}"
        )

@app.post("/api/v1/full-face-swap/tasks", response_model=JobResponse, status_code=202)
async def create_full_face_swap_task(request: FullFaceSwapRequest):
    """
    Submit a full face swap task (CPU task).

    This endpoint returns within 1 second with a 202 Accepted response.
    Clients should poll GET /api/v1/jobs/{job_id} for status updates.
    """
    if not CPU_QUEUE_URL:
        raise HTTPException(
            status_code=500,
            detail="CPU_QUEUE_URL not configured"
        )

    # Generate task ID
    task_id = str(uuid.uuid4())

    try:
        # Create task record in DynamoDB
        create_task(
            table_name=DYNAMODB_TABLE,
            task_id=task_id,
            job_type='/api/v1/full-face-swap/jobs',
            region=AWS_REGION,
            initial_status='pending'
        )

        # Send message to CPU SQS queue
        message_body = json.dumps({
            'task_id': task_id,
            'task_type': 'full_face_swap',
            'api_path': '/api/v1/full-face-swap/jobs',
            'request_body': request.dict()
        })

        send_message(
            queue_url=CPU_QUEUE_URL,
            message_body=message_body,
            region=AWS_REGION
        )

        print(f"✓ Submitted full face swap task {task_id}")

        return JobResponse(
            job_id=task_id,
            status="pending",
            result_url=None,
            error=None
        )

    except Exception as e:
        print(f"✗ Error submitting full face swap task: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to submit task: {str(e)}"
        )

# ==================== Unified Job Status ====================

@app.get("/api/v1/jobs/{job_id}", response_model=JobResponse)
async def get_job_status(job_id: str):
    """
    Get the status of any job (camera-angle or qwen-image-edit).

    This endpoint simply queries DynamoDB and returns the current state.
    The orchestrator does NOT process tasks - it only reports their status.

    Includes retry logic: if job not found on first attempt, waits 1 second and retries.
    This handles eventual consistency issues with DynamoDB.
    """
    try:
        # First attempt
        task = get_task_status(
            table_name=DYNAMODB_TABLE,
            task_id=job_id,
            region=AWS_REGION
        )

        # If not found, wait 1 second and retry once
        if not task:
            import time
            time.sleep(1)
            print(f"Job {job_id} not found on first attempt, retrying...")
            task = get_task_status(
                table_name=DYNAMODB_TABLE,
                task_id=job_id,
                region=AWS_REGION
            )

        if not task:
            raise HTTPException(status_code=404, detail="Job not found")

        return JobResponse(
            job_id=job_id,
            status=task.get('status', 'unknown'),
            result_url=task.get('result_url') or task.get('result_s3_uri'),  # Try both field names
            error=task.get('error') or task.get('error_message')  # Try both field names
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error retrieving job status: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve job status: {str(e)}"
        )

# ==================== Image Management ====================

@app.delete("/api/v1/images/{s3_key:path}")
async def delete_image(s3_key: str):
    """
    Delete an image from S3.

    Args:
        s3_key: The S3 object key (path within the bucket)

    Returns:
        Success confirmation
    """
    try:
        # Delete from S3
        s3_client = boto3.client('s3', region_name=AWS_REGION)
        s3_client.delete_object(Bucket=S3_BUCKET_NAME, Key=s3_key)

        print(f"Deleted image from S3: s3://{S3_BUCKET_NAME}/{s3_key}")

        return JSONResponse(
            status_code=200,
            content={"message": "Image deleted successfully", "s3_key": s3_key}
        )

    except Exception as e:
        print(f"Error deleting image {s3_key}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete image: {str(e)}"
        )

if __name__ == "__main__":
    # Validate configuration
    if not SQS_QUEUE_URL:
        print("ERROR: SQS_QUEUE_URL environment variable not set")
        exit(1)

    print(f"Starting Orchestrator Service...")
    print(f"AWS Region: {AWS_REGION}")
    print(f"SQS Queue: {SQS_QUEUE_URL}")
    print(f"DynamoDB Table: {DYNAMODB_TABLE}")
    print(f"GPU Instance: {GPU_INSTANCE_ID}")

    uvicorn.run(app, host="0.0.0.0", port=8080)
