"""
CPU Tasks Orchestrator API

This module provides API endpoints for submitting CPU-bound tasks
(face masking, face swapping) to the CPU task queue.
"""

import os
import json
import uuid
import time
from typing import Optional, Dict, Any
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import boto3
from botocore.exceptions import ClientError

# Import shared AWS utilities
from aws.sqs import send_message
from aws.dynamodb import create_task, get_task_status
from cpu_tasks_config import (
    CPU_QUEUE_URL,
    CPU_DYNAMODB_TABLE,
    AWS_REGION,
    CPU_TASK_TYPES
)

app = FastAPI(
    title="CPU Tasks Orchestrator API",
    description="Orchestrator for CPU-bound paid API tasks",
    version="1.0.0"
)


class FaceMaskRequest(BaseModel):
    """Request model for face masking"""
    image_url: str
    face_index: Optional[int] = 0


class FaceSwapRequest(BaseModel):
    """Request model for face swap"""
    masked_image_url: str
    target_face_url: str
    prompt: Optional[str] = None
    size: Optional[str] = None


class FullFaceSwapRequest(BaseModel):
    """Request model for full face swap"""
    source_image_url: str
    target_face_url: str
    face_index: Optional[int] = 0
    prompt: Optional[str] = None
    size: Optional[str] = None


class TaskResponse(BaseModel):
    """Task submission response"""
    task_id: str
    status: str
    message: str


class TaskStatusResponse(BaseModel):
    """Task status response"""
    task_id: str
    status: str
    job_type: str
    result_url: Optional[str] = None
    error_message: Optional[str] = None
    created_at: Optional[int] = None
    updated_at: Optional[int] = None


def submit_cpu_task(
    task_type: str,
    request_body: Dict[str, Any]
) -> str:
    """
    Submit a CPU task to the queue

    Args:
        task_type: Type of task (face_mask, face_swap, full_face_swap)
        request_body: Request parameters

    Returns:
        task_id: UUID of the created task

    Raises:
        HTTPException: If queue URL not configured or task creation fails
    """
    if not CPU_QUEUE_URL:
        raise HTTPException(
            status_code=500,
            detail="CPU_QUEUE_URL not configured"
        )

    if task_type not in CPU_TASK_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid task type: {task_type}"
        )

    # Generate task ID
    task_id = str(uuid.uuid4())

    try:
        # Create task record in DynamoDB
        api_path = CPU_TASK_TYPES[task_type]
        create_task(
            table_name=CPU_DYNAMODB_TABLE,
            task_id=task_id,
            job_type=api_path,
            region=AWS_REGION,
            initial_status='pending'
        )

        # Send message to SQS
        message_body = json.dumps({
            'task_id': task_id,
            'task_type': task_type,
            'api_path': api_path,
            'request_body': request_body
        })

        send_message(
            queue_url=CPU_QUEUE_URL,
            message_body=message_body,
            region=AWS_REGION
        )

        print(f"✓ Submitted CPU task {task_id} (type: {task_type})")
        return task_id

    except Exception as e:
        print(f"✗ Error submitting CPU task: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to submit task: {str(e)}"
        )


@app.get("/")
async def root():
    """API information"""
    return {
        "service": "CPU Tasks Orchestrator",
        "version": "1.0.0",
        "endpoints": {
            "face_mask": "/api/v1/face-mask/tasks",
            "face_swap": "/api/v1/face-swap/tasks",
            "full_face_swap": "/api/v1/full-face-swap/tasks",
            "task_status": "/api/v1/tasks/{task_id}"
        }
    }


@app.get("/health")
async def health_check():
    """Health check"""
    issues = []

    if not CPU_QUEUE_URL:
        issues.append("CPU_QUEUE_URL not configured")

    return {
        "status": "healthy" if not issues else "degraded",
        "issues": issues if issues else None,
        "queue_url": CPU_QUEUE_URL if CPU_QUEUE_URL else None
    }


@app.post("/api/v1/face-mask/tasks", response_model=TaskResponse)
async def submit_face_mask_task(request: FaceMaskRequest):
    """
    Submit a face mask task

    Creates a black elliptical mask on detected face.
    """
    task_id = submit_cpu_task(
        task_type='face_mask',
        request_body=request.dict()
    )

    return TaskResponse(
        task_id=task_id,
        status='pending',
        message='Face mask task submitted successfully'
    )


@app.post("/api/v1/face-swap/tasks", response_model=TaskResponse)
async def submit_face_swap_task(request: FaceSwapRequest):
    """
    Submit a face swap task

    Applies face swap to a pre-masked image.
    """
    task_id = submit_cpu_task(
        task_type='face_swap',
        request_body=request.dict()
    )

    return TaskResponse(
        task_id=task_id,
        status='pending',
        message='Face swap task submitted successfully'
    )


@app.post("/api/v1/full-face-swap/tasks", response_model=TaskResponse)
async def submit_full_face_swap_task(request: FullFaceSwapRequest):
    """
    Submit a full face swap task

    Combines face masking and face swapping in one pipeline.
    """
    task_id = submit_cpu_task(
        task_type='full_face_swap',
        request_body=request.dict()
    )

    return TaskResponse(
        task_id=task_id,
        status='pending',
        message='Full face swap task submitted successfully'
    )


@app.get("/api/v1/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_task_status_endpoint(task_id: str):
    """
    Get task status

    Retrieves status and results from DynamoDB.
    """
    try:
        task = get_task_status(
            table_name=CPU_DYNAMODB_TABLE,
            task_id=task_id,
            region=AWS_REGION
        )

        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        return TaskStatusResponse(
            task_id=task_id,
            status=task.get('status', 'unknown'),
            job_type=task.get('job_type', 'unknown'),
            result_url=task.get('result_url'),
            error_message=task.get('error_message'),
            created_at=task.get('created_at'),
            updated_at=task.get('updated_at')
        )

    except ClientError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving task status: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)
