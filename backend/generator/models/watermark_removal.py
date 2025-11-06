"""
Watermark Removal API Endpoints
Provides intelligent watermark removal for images and videos
"""

from fastapi import APIRouter, File, UploadFile, HTTPException, Form
from pydantic import BaseModel, Field
from PIL import Image
from typing import Optional
import io
import logging
from pathlib import Path
import tempfile

from .base import SessionResponse, image_to_bytes
from services.task_service import task_service
from services.watermark_service import watermark_service
from services.s3_service import s3_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/watermark-removal", tags=["Watermark Removal"])


class WatermarkRemovalRequest(BaseModel):
    """Request model for watermark removal"""

    auto_detect_mask: Optional[bool] = Field(
        True, description="Automatically detect watermark regions"
    )
    num_inference_steps: Optional[int] = Field(
        10, description="Number of denoising steps (10 recommended)"
    )
    guidance_scale: Optional[float] = Field(
        3.0, description="Guidance scale (3.0 recommended)"
    )
    seed: Optional[int] = Field(None, description="Random seed for reproducibility")


def remove_watermark_from_image_task(
    input_image: Image.Image,
    auto_detect_mask: bool = True,
    num_inference_steps: int = 10,
    guidance_scale: float = 3.0,
    seed: Optional[int] = None,
) -> bytes:
    """
    Task function for image watermark removal

    Args:
        input_image: PIL Image to process
        auto_detect_mask: Automatically detect watermark
        num_inference_steps: Number of steps
        guidance_scale: Guidance scale
        seed: Random seed

    Returns:
        Processed image as bytes
    """
    try:
        # Remove watermark
        result_image = watermark_service.remove_watermark_from_image(
            image=input_image,
            auto_detect_mask=auto_detect_mask,
            num_inference_steps=num_inference_steps,
            guidance_scale=guidance_scale,
            seed=seed,
        )

        # Convert to bytes
        return image_to_bytes(result_image)

    except Exception as e:
        logger.error(f"Watermark removal error: {str(e)}")
        raise


def remove_watermark_from_video_task(
    video_path: str,
    auto_detect_mask: bool = True,
    num_inference_steps: int = 10,
    guidance_scale: float = 3.0,
    seed: Optional[int] = None,
    preserve_audio: bool = True,
) -> str:
    """
    Task function for video watermark removal

    Args:
        video_path: Path to input video
        auto_detect_mask: Automatically detect watermark
        num_inference_steps: Number of steps
        guidance_scale: Guidance scale
        seed: Random seed
        preserve_audio: Preserve original audio

    Returns:
        Path to output video
    """
    try:
        # Create output path
        output_path = Path(tempfile.gettempdir()) / f"clean_{Path(video_path).name}"

        # Remove watermark
        result_path = watermark_service.remove_watermark_from_video(
            video_path=video_path,
            output_path=output_path,
            auto_detect_mask=auto_detect_mask,
            num_inference_steps=num_inference_steps,
            guidance_scale=guidance_scale,
            seed=seed,
            preserve_audio=preserve_audio,
        )

        # Read video file as bytes
        with open(result_path, "rb") as f:
            video_bytes = f.read()

        # Cleanup temp file
        Path(result_path).unlink()

        return video_bytes

    except Exception as e:
        logger.error(f"Video watermark removal error: {str(e)}")
        raise


@router.post("/image", response_model=SessionResponse)
async def remove_watermark_from_image(
    image_url: str = Form(..., description="S3 URL or HTTP(S) URL of the input image"),
    auto_detect_mask: bool = Form(True, description="Automatically detect watermark regions"),
    num_inference_steps: int = Form(10, description="Number of denoising steps (10 recommended)"),
    guidance_scale: float = Form(3.0, description="Guidance scale (3.0 recommended)"),
    seed: Optional[int] = Form(None, description="Random seed for reproducibility"),
):
    """
    Remove watermark from an image using WanVideo MiniMaxRemover

    This endpoint uses state-of-the-art AI to intelligently remove watermarks
    from images while preserving image quality.

    Features:
    - Automatic watermark detection
    - Intelligent inpainting
    - Quality preservation
    - Based on WanVideo MiniMaxRemover model

    Args:
        image_url: URL to input image (S3 or HTTP/HTTPS)
        auto_detect_mask: Automatically detect watermark regions (recommended)
        num_inference_steps: Number of denoising steps (10 is optimal)
        guidance_scale: Guidance scale for generation (3.0 recommended)
        seed: Random seed for reproducible results

    Example URLs:
        - S3: s3://short-drama-assets/images/watermarked.png
        - HTTPS: https://short-drama-assets.s3.us-east-1.amazonaws.com/images/watermarked.png
        - HTTP: https://example.com/image.jpg

    Returns:
        SessionResponse with session_id to track progress.
        Result will be uploaded to s3://short-drama-assets/images/
    """
    try:
        logger.info(
            f"Watermark removal (image) - URL: {image_url}, "
            f"Steps: {num_inference_steps}, Guidance: {guidance_scale}"
        )

        # Download image from URL
        input_image = s3_service.download_image_from_url(image_url)

        if input_image is None:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to download image from URL: {image_url}"
            )

        logger.info(f"Successfully downloaded image: {input_image.size}")

        # Submit task and get session_id
        session_id = await task_service.submit_task(
            generation_func=remove_watermark_from_image_task,
            generation_kwargs={
                "input_image": input_image,
                "auto_detect_mask": auto_detect_mask,
                "num_inference_steps": num_inference_steps,
                "guidance_scale": guidance_scale,
                "seed": seed,
            },
            file_extension="png",
            content_type="image/png",
            s3_folder="images",
        )

        return SessionResponse(
            session_id=session_id,
            status="pending",
            message=(
                f"Watermark removal task submitted. "
                f"Use /api/{{session_id}}/status to check progress. "
                f"Result will be uploaded to s3://short-drama-assets/images/"
            ),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting watermark removal task: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to submit task: {str(e)}"
        )


@router.post("/video", response_model=SessionResponse)
async def remove_watermark_from_video(
    video_url: str = Form(..., description="S3 URL or HTTP(S) URL of the input video"),
    auto_detect_mask: bool = Form(True, description="Automatically detect watermark regions"),
    num_inference_steps: int = Form(10, description="Number of denoising steps (10 recommended)"),
    guidance_scale: float = Form(3.0, description="Guidance scale (3.0 recommended)"),
    seed: Optional[int] = Form(None, description="Random seed for reproducibility"),
    preserve_audio: bool = Form(True, description="Preserve original audio track"),
):
    """
    Remove watermark from a video using WanVideo MiniMaxRemover

    This endpoint uses state-of-the-art AI to intelligently remove watermarks
    from videos while maintaining temporal consistency and preserving video quality.

    Features:
    - Automatic watermark detection
    - Temporal consistency across frames
    - Audio preservation
    - Quality preservation
    - Based on WanVideo MiniMaxRemover model

    Args:
        video_url: URL to input video (S3 or HTTP/HTTPS)
        auto_detect_mask: Automatically detect watermark regions (recommended)
        num_inference_steps: Number of denoising steps (10 is optimal)
        guidance_scale: Guidance scale for generation (3.0 recommended)
        seed: Random seed for reproducible results
        preserve_audio: Keep original audio track (recommended)

    Example URLs:
        - S3: s3://short-drama-assets/videos/watermarked.mp4
        - HTTPS: https://short-drama-assets.s3.us-east-1.amazonaws.com/videos/watermarked.mp4
        - HTTP: https://example.com/video.mp4

    Returns:
        SessionResponse with session_id to track progress.
        Result will be uploaded to s3://short-drama-assets/videos/

    Note:
        Video processing may take longer depending on video length and resolution.
        Progress updates are available through the status endpoint.
    """
    try:
        logger.info(
            f"Watermark removal (video) - URL: {video_url}, "
            f"Steps: {num_inference_steps}, Guidance: {guidance_scale}"
        )

        # Download video from URL to temporary file
        import requests
        response = requests.get(video_url, timeout=300, stream=True)
        response.raise_for_status()

        # Save to temporary file
        temp_video = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                temp_video.write(chunk)
        temp_video.close()

        logger.info(f"Successfully downloaded video to: {temp_video.name}")

        # Submit task and get session_id
        session_id = await task_service.submit_task(
            generation_func=remove_watermark_from_video_task,
            generation_kwargs={
                "video_path": temp_video.name,
                "auto_detect_mask": auto_detect_mask,
                "num_inference_steps": num_inference_steps,
                "guidance_scale": guidance_scale,
                "seed": seed,
                "preserve_audio": preserve_audio,
            },
            file_extension="mp4",
            content_type="video/mp4",
            s3_folder="videos",
        )

        return SessionResponse(
            session_id=session_id,
            status="pending",
            message=(
                f"Video watermark removal task submitted. "
                f"This may take several minutes depending on video length. "
                f"Use /api/{{session_id}}/status to check progress. "
                f"Result will be uploaded to s3://short-drama-assets/videos/"
            ),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting video watermark removal task: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to submit task: {str(e)}"
        )


@router.get("/info")
async def get_watermark_removal_info():
    """
    Get information about the watermark removal service

    Returns details about the model, capabilities, and current system state.
    """
    try:
        return watermark_service.get_service_info()
    except Exception as e:
        logger.error(f"Error getting watermark removal info: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get service info: {str(e)}"
        )
