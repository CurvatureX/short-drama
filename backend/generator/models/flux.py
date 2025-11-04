"""
Flux model implementation using Flux.1-dev from diffusers
"""

from fastapi import APIRouter, File, UploadFile, HTTPException, Form
from PIL import Image, ImageDraw
import io
import logging
from typing import Optional

from .base import TextToImageRequest, SessionResponse, image_to_bytes
from services.task_service import task_service
from services.flux_service import flux_model_service
from services.s3_service import s3_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/flux", tags=["Flux"])


def generate_image(request: TextToImageRequest) -> bytes:
    """
    Generate image using Flux.1-dev

    Args:
        request: TextToImageRequest with generation parameters

    Returns:
        Image as bytes
    """
    try:
        # Generate image using Flux model service
        image = flux_model_service.generate(
            prompt=request.prompt,
            height=request.height,
            width=request.width,
            guidance_scale=request.guidance_scale,
            num_inference_steps=request.num_inference_steps,
            seed=request.seed,
        )

        # Convert PIL Image to bytes
        return image_to_bytes(image)

    except Exception as e:
        logger.error(f"Flux generation error: {str(e)}")
        # Return error placeholder image
        error_image = Image.new("RGB", (request.width, request.height), color="red")
        draw = ImageDraw.Draw(error_image)
        draw.text((10, 10), f"Error: {str(e)[:100]}", fill="white")
        return image_to_bytes(error_image)


def transform_image(input_image: Image.Image, prompt: str = None, **kwargs) -> bytes:
    """
    Transform image using Flux img2img

    TODO: Implement actual Flux img2img inference when available
    Currently returns a placeholder transformation
    """
    # Placeholder implementation - Flux.1-dev doesn't have img2img yet
    # You can implement this when FluxImg2ImgPipeline becomes available
    output_image = input_image.copy()
    draw = ImageDraw.Draw(output_image)
    text = "Flux i2i (placeholder)"
    if prompt:
        text += f"\n{prompt[:50]}"
    draw.text((10, 10), text, fill="blue")
    return image_to_bytes(output_image)


@router.post("/t2i", response_model=SessionResponse)
async def text_to_image(request: TextToImageRequest):
    """
    Text-to-Image using Flux.1-dev

    Returns immediately with a session_id to track progress
    """
    try:
        logger.info(f"Flux t2i - Prompt: {request.prompt}")

        # Submit task and get session_id
        session_id = await task_service.submit_task(
            generation_func=generate_image,
            generation_kwargs={"request": request},
            file_extension="png",
            content_type="image/png",
        )

        return SessionResponse(
            session_id=session_id,
            status="pending",
            message="Task submitted. Use /api/{session_id}/status to check progress.",
        )

    except Exception as e:
        logger.error(f"Error submitting Flux t2i task: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to submit task: {str(e)}"
        )


@router.post("/i2i", response_model=SessionResponse)
async def image_to_image(
    image_url: str = Form(..., description="S3 URL or HTTP(S) URL of the input image"),
    prompt: Optional[str] = Form(None),
    strength: float = Form(0.8),
    guidance_scale: float = Form(7.5),
    num_inference_steps: int = Form(50),
    seed: Optional[int] = Form(None),
):
    """
    Image-to-Image using Flux (Placeholder)

    Accepts S3 URL or HTTP(S) URL as image input.

    Note: Flux.1-dev doesn't officially support img2img yet.
    This is a placeholder implementation.

    Example image_url:
    - S3: "https://bucket-name.s3.region.amazonaws.com/path/to/image.png"
    - HTTP: "https://example.com/image.jpg"

    Returns immediately with a session_id to track progress
    """
    try:
        logger.info(f"Flux i2i - URL: {image_url}, Prompt: {prompt}")

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
            generation_func=transform_image,
            generation_kwargs={
                "input_image": input_image,
                "prompt": prompt,
                "strength": strength,
                "guidance_scale": guidance_scale,
                "num_inference_steps": num_inference_steps,
                "seed": seed,
            },
            file_extension="png",
            content_type="image/png",
        )

        return SessionResponse(
            session_id=session_id,
            status="pending",
            message="Task submitted. Use /api/{session_id}/status to check progress.",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting Flux i2i task: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to submit task: {str(e)}"
        )
