"""
Background task processing service
"""

import asyncio
import uuid
import logging
from typing import Callable, Any, Dict
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from PIL import Image

from services.redis_service import redis_service
from services.s3_service import s3_service

logger = logging.getLogger(__name__)

# Thread pool for CPU/GPU-bound generation tasks
# Back to ThreadPoolExecutor - ProcessPoolExecutor has pickle issues
# Memory management will be handled by explicit cleanup in generation functions
executor = ThreadPoolExecutor(max_workers=1)  # Only 1 at a time to avoid OOM

# Separate thread pool for I/O-bound operations (model downloads)
# This prevents model downloads from blocking generation tasks
io_executor = ThreadPoolExecutor(max_workers=10)


class TaskService:
    """Service for managing background task execution"""

    @staticmethod
    def generate_session_id() -> str:
        """Generate a unique session ID"""
        return str(uuid.uuid4())

    @staticmethod
    async def process_generation_task(
        session_id: str,
        generation_func: Callable,
        generation_kwargs: Dict[str, Any],
        file_extension: str = "png",
        content_type: str = "image/png",
        s3_folder: str = "images",
    ) -> None:
        """
        Process image/video generation task in background

        Args:
            session_id: Unique session identifier
            generation_func: Function to call for generation
            generation_kwargs: Kwargs to pass to generation function
            file_extension: File extension for upload
            content_type: MIME type for upload
            s3_folder: S3 folder prefix (images or videos)
        """
        try:
            # Update status to processing
            redis_service.set_task_status(
                session_id=session_id,
                status="processing",
                progress=10,
                message="Starting generation...",
            )

            # Run generation in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            # Use lambda to pass kwargs correctly to the function
            image_bytes = await loop.run_in_executor(
                executor, lambda: generation_func(**generation_kwargs)
            )

            # Update progress
            redis_service.set_task_status(
                session_id=session_id,
                status="processing",
                progress=60,
                message=f"Generation complete, uploading to S3 ({s3_folder})...",
            )

            # Upload to S3
            s3_url = s3_service.upload_file(
                file_data=image_bytes,
                session_id=session_id,
                file_extension=file_extension,
                content_type=content_type,
                s3_folder=s3_folder,
            )

            if s3_url:
                # Update status to completed
                redis_service.set_task_status(
                    session_id=session_id,
                    status="completed",
                    progress=100,
                    message="Generation completed successfully",
                    result_url=s3_url,
                )
            else:
                # S3 upload failed
                redis_service.set_task_status(
                    session_id=session_id,
                    status="failed",
                    progress=60,
                    message="Failed to upload to S3",
                    error="S3 upload error",
                )

        except Exception as e:
            logger.error(f"Task {session_id} failed: {str(e)}")
            redis_service.set_task_status(
                session_id=session_id,
                status="failed",
                progress=0,
                message="Generation failed",
                error=str(e),
            )

    @staticmethod
    async def submit_task(
        generation_func: Callable,
        generation_kwargs: Dict[str, Any],
        file_extension: str = "png",
        content_type: str = "image/png",
        s3_folder: str = "images",
    ) -> str:
        """
        Submit a new generation task

        Args:
            generation_func: Function to call for generation
            generation_kwargs: Kwargs to pass to generation function
            file_extension: File extension for upload
            content_type: MIME type for upload
            s3_folder: S3 folder prefix (images or videos)

        Returns:
            session_id for tracking the task
        """
        session_id = TaskService.generate_session_id()

        # Initialize task status
        redis_service.set_task_status(
            session_id=session_id,
            status="pending",
            progress=0,
            message="Task queued",
        )

        # Start background task
        asyncio.create_task(
            TaskService.process_generation_task(
                session_id=session_id,
                generation_func=generation_func,
                generation_kwargs=generation_kwargs,
                file_extension=file_extension,
                content_type=content_type,
                s3_folder=s3_folder,
            )
        )

        return session_id


task_service = TaskService()
