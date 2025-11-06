"""
Image and Video Generation Server

This server provides endpoints for generating images and videos using various AI models.
Each model has dedicated endpoints with the naming schema: /api/{model_name}/{conversion_type}
where conversion_type can be: t2i (text-to-image), i2i (image-to-image), t2v (text-to-video), i2v (image-to-video)
"""

from fastapi import FastAPI, HTTPException, Path
from pydantic import BaseModel
from typing import Optional
import logging

# Import model routers
from models import flux
from models import qwen_multi_angle
from models import watermark_removal

# Import services
from services.redis_service import redis_service
from services.vram_manager import vram_manager
from services.model_manager import model_manager
from services.queue_manager import queue_manager
from services.optimization import optimization_manager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Image/Video Generation API",
    description="API for generating images and videos from text or image inputs with async task processing",
    version="1.0.0",
)


class TaskStatusResponse(BaseModel):
    """Response model for task status"""

    session_id: str
    status: str  # pending, processing, completed, failed
    progress: int  # 0-100
    message: str
    result_url: Optional[str] = None
    error: Optional[str] = None


@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "online",
        "service": "Image/Video Generation API",
        "version": "1.0.0",
        "models": [
            "flux",
            "qwen-multi-angle",
            "watermark-removal",
        ],
        "redis_connected": redis_service.ping(),
    }


@app.get("/api/{session_id}/status", response_model=TaskStatusResponse)
async def get_task_status(
    session_id: str = Path(..., description="Session ID to check status")
):
    """
    Get the status of a generation task

    Returns the current status, progress, and result URL (if completed)
    """
    task_status = redis_service.get_task_status(session_id)

    if not task_status:
        raise HTTPException(
            status_code=404,
            detail=f"Task with session_id {session_id} not found or has expired",
        )

    return TaskStatusResponse(**task_status)


@app.get("/api/system/stats")
async def get_system_stats():
    """
    Get comprehensive system statistics

    Returns information about VRAM, models, queue, and optimizations
    """
    return {
        "vram": vram_manager.get_memory_summary(),
        "models": model_manager.get_cache_stats(),
        "queue": queue_manager.get_queue_stats(),
        "optimizations": optimization_manager.get_optimization_info(),
    }


@app.post("/api/system/cleanup")
async def trigger_cleanup():
    """
    Manually trigger system cleanup

    Clears VRAM cache and performs garbage collection
    """
    vram_manager.cleanup_if_needed()
    return {"status": "cleanup_triggered", "vram": vram_manager.get_memory_summary()}


# Include all model routers
app.include_router(flux.router)
app.include_router(qwen_multi_angle.router)
app.include_router(watermark_removal.router)


def run():
    """Entry point for running the server"""
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    run()
