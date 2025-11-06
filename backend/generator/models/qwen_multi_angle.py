"""
Qwen Multi-Angle model implementation
Using Qwen-Image + Lightning LoRA + Multi-Angle LoRA
"""

from fastapi import APIRouter, File, UploadFile, HTTPException, Form
from pydantic import BaseModel, Field
from PIL import Image, ImageDraw
from typing import Optional, List
import io
import logging

from .base import SessionResponse, image_to_bytes
from services.task_service import task_service
from services.qwen_service import qwen_model_service
from services.s3_service import s3_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/qwen-multi-angle", tags=["Qwen Multi-Angle"])


class QwenTextToImageRequest(BaseModel):
    """Request model for Qwen text-to-image generation"""

    prompt: str = Field(..., description="Text prompt with optional camera angle instructions")
    negative_prompt: Optional[str] = Field("", description="Negative prompt")
    width: Optional[int] = Field(1024, description="Image width")
    height: Optional[int] = Field(1024, description="Image height")
    num_inference_steps: Optional[int] = Field(8, description="Number of inference steps (8 recommended for Lightning)")
    guidance_scale: Optional[float] = Field(4.0, description="CFG scale (4.0 recommended for Qwen)")
    seed: Optional[int] = Field(None, description="Random seed")
    use_magic_prompt: Optional[bool] = Field(True, description="Add magic prompt for better quality")


class QwenMultiAngleRequest(BaseModel):
    """Request model for multi-angle generation"""

    base_prompt: str = Field(..., description="Base scene description")
    camera_angles: List[str] = Field(
        ...,
        description="List of camera angles to generate",
        example=["front view", "rotate left 45 degrees", "top-down view", "close-up"]
    )
    negative_prompt: Optional[str] = Field("", description="Negative prompt")
    width: Optional[int] = Field(1024, description="Image width")
    height: Optional[int] = Field(1024, description="Image height")
    num_inference_steps: Optional[int] = Field(8, description="Number of inference steps")
    guidance_scale: Optional[float] = Field(4.0, description="CFG scale")
    seed: Optional[int] = Field(None, description="Random seed (same for all angles)")
    use_magic_prompt: Optional[bool] = Field(True, description="Add magic prompt")


def generate_image(request: QwenTextToImageRequest) -> bytes:
    """
    Generate image using Qwen with Lightning and Multi-Angle LoRAs

    Args:
        request: QwenTextToImageRequest with generation parameters

    Returns:
        Image as bytes
    """
    try:
        # Generate image using Qwen model service
        image = qwen_model_service.generate(
            prompt=request.prompt,
            negative_prompt=request.negative_prompt or "",
            height=request.height,
            width=request.width,
            num_inference_steps=request.num_inference_steps,
            guidance_scale=request.guidance_scale,
            seed=request.seed,
            use_magic_prompt=request.use_magic_prompt,
        )

        # Convert PIL Image to bytes
        return image_to_bytes(image)

    except Exception as e:
        logger.error(f"Qwen generation error: {str(e)}")
        # Return error placeholder image
        error_image = Image.new("RGB", (request.width, request.height), color="red")
        draw = ImageDraw.Draw(error_image)
        draw.text((10, 10), f"Error: {str(e)[:100]}", fill="white")
        return image_to_bytes(error_image)


def generate_multi_angle_images(request: QwenMultiAngleRequest) -> List[bytes]:
    """
    Generate multiple images with different camera angles

    Args:
        request: QwenMultiAngleRequest with base prompt and angles

    Returns:
        List of images as bytes
    """
    try:
        # Generate images with different angles
        images = qwen_model_service.generate_multi_angle(
            base_prompt=request.base_prompt,
            camera_angles=request.camera_angles,
            negative_prompt=request.negative_prompt or "",
            height=request.height,
            width=request.width,
            num_inference_steps=request.num_inference_steps,
            guidance_scale=request.guidance_scale,
            seed=request.seed,
            use_magic_prompt=request.use_magic_prompt,
        )

        # Convert all images to bytes
        return [image_to_bytes(img) for img in images]

    except Exception as e:
        logger.error(f"Qwen multi-angle generation error: {str(e)}")
        raise


@router.post("/t2i", response_model=SessionResponse)
async def text_to_image(request: QwenTextToImageRequest):
    """
    Text-to-Image using Qwen with Lightning and Multi-Angle LoRAs

    Supports camera angle control in prompts:
    - "Move the camera forward"
    - "Rotate left/right 45 degrees"
    - "Turn to top-down view"
    - "Change to wide-angle view"
    - "Close-up perspective"

    Returns immediately with a session_id to track progress
    """
    try:
        logger.info(f"Qwen t2i - Prompt: {request.prompt}")

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
        logger.error(f"Error submitting Qwen t2i task: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to submit task: {str(e)}"
        )


@router.post("/multi-angle", response_model=SessionResponse)
async def generate_multi_angle(request: QwenMultiAngleRequest):
    """
    Generate multiple images with different camera angles

    This endpoint generates multiple images from a single base prompt
    with different camera perspectives specified in camera_angles list.

    Example request:
    {
      "base_prompt": "A futuristic car in a showroom",
      "camera_angles": [
        "front view",
        "rotate left 45 degrees",
        "top-down view",
        "close-up on the headlights"
      ]
    }

    Returns immediately with a session_id to track progress.
    The result will contain multiple images (one per angle).
    """
    try:
        logger.info(
            f"Qwen multi-angle - Base: {request.base_prompt}, "
            f"Angles: {len(request.camera_angles)}"
        )

        # Submit task and get session_id
        session_id = await task_service.submit_task(
            generation_func=generate_multi_angle_images,
            generation_kwargs={"request": request},
            file_extension="zip",  # Multiple images will be zipped
            content_type="application/zip",
        )

        return SessionResponse(
            session_id=session_id,
            status="pending",
            message=f"Multi-angle task submitted ({len(request.camera_angles)} angles). "
                   f"Use /api/{{session_id}}/status to check progress.",
        )

    except Exception as e:
        logger.error(f"Error submitting Qwen multi-angle task: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to submit task: {str(e)}"
        )


def edit_image(
    input_image: Image.Image,
    prompt: str,
    negative_prompt: str = "",
    guidance_scale: float = 1.0,
    true_cfg_scale: float = 1.0,
    num_inference_steps: int = 8,
    seed: Optional[int] = None,
    scale_to_megapixels: float = 1.0,
    use_cfg_norm: bool = True,
    scheduler_shift: float = 3.0,
) -> bytes:
    """
    Edit image using Qwen-Image-Edit with Multi-Angle LoRA

    This function replicates the ComfyUI workflow capabilities:
    - Scales image to target megapixels (ImageScaleToTotalPixels)
    - Uses ModelSamplingAuraFlow with shift parameter
    - Applies CFG normalization
    - Uses Lightning LoRA for fast 8-step editing
    - Uses Multi-Angle LoRA for camera control

    Args:
        input_image: PIL Image to edit
        prompt: Edit instruction (camera angle changes supported)
        negative_prompt: Negative prompt
        guidance_scale: CFG scale (1.0 recommended)
        true_cfg_scale: True CFG scale (1.0 recommended)
        num_inference_steps: Number of steps (8 recommended with Lightning)
        seed: Random seed
        scale_to_megapixels: Scale image to specific megapixels (1.0 = 1MP)
        use_cfg_norm: Enable CFG normalization
        scheduler_shift: ModelSamplingAuraFlow shift (3.0 recommended)

    Returns:
        Edited image as bytes
    """
    try:
        # Edit image using Qwen model service
        edited_image = qwen_model_service.edit_image(
            image=input_image,
            prompt=prompt,
            negative_prompt=negative_prompt,
            num_inference_steps=num_inference_steps,
            guidance_scale=guidance_scale,
            true_cfg_scale=true_cfg_scale,
            seed=seed,
            scale_to_megapixels=scale_to_megapixels,
            use_cfg_norm=use_cfg_norm,
            scheduler_shift=scheduler_shift,
        )

        # Convert PIL Image to bytes
        return image_to_bytes(edited_image)

    except Exception as e:
        logger.error(f"Qwen image editing error: {str(e)}")
        # Return error placeholder image
        error_image = Image.new("RGB", (input_image.width, input_image.height), color="red")
        draw = ImageDraw.Draw(error_image)
        draw.text((10, 10), f"Error: {str(e)[:100]}", fill="white")
        return image_to_bytes(error_image)


@router.post("/i2i", response_model=SessionResponse)
async def image_to_image(
    image_url: str = Form(..., description="S3 URL or HTTP(S) URL of the input image"),
    prompt: str = Form(..., description="Edit instruction (camera angle changes supported)"),
    negative_prompt: Optional[str] = Form(""),
    guidance_scale: float = Form(1.0, description="CFG scale (1.0 recommended)"),
    true_cfg_scale: float = Form(1.0, description="True CFG scale (1.0 recommended)"),
    num_inference_steps: int = Form(8, description="Number of steps (8 with Lightning LoRA)"),
    seed: Optional[int] = Form(None, description="Random seed for reproducibility"),
    scale_to_megapixels: float = Form(1.0, description="Scale image to megapixels (1.0 = 1MP)"),
    use_cfg_norm: bool = Form(True, description="Enable CFG normalization"),
    scheduler_shift: float = Form(3.0, description="ModelSamplingAuraFlow shift parameter"),
):
    """
    Image-to-Image editing using Qwen-Image-Edit with Multi-Angle LoRA

    This endpoint replicates the full ComfyUI workflow with all advanced features:
    - UNETLoader: qwen-image-edit-2509 (fp8_e4m3fn quantized)
    - CLIPLoader: qwen-2.5-vl-7b (fp8 scaled)
    - VAELoader: qwen_image_vae
    - LoRA 1: Multi-Angle LoRA (镜头转换) for camera control
    - LoRA 2: Lightning LoRA (4-step fast editing)
    - ImageScaleToTotalPixels: Scales to target megapixels
    - ModelSamplingAuraFlow: Uses shift=3.0 for better quality
    - CFGNorm: Normalizes CFG for stable generation
    - KSampler: 8 steps, euler scheduler, simple mode

    Accepts S3 URL or HTTP(S) URL as image input.

    Supported camera angle instructions (Chinese):
    - "将镜头向前移动" (Move the camera forward)
    - "将镜头向左移动" (Move the camera left)
    - "将镜头向右移动" (Move the camera right)
    - "将镜头向下移动" (Move the camera down)
    - "将镜头向左旋转45度" (Rotate the camera 45 degrees to the left)
    - "将镜头向右旋转45度" (Rotate the camera 45 degrees to the right)
    - "将镜头转为俯视" (Turn the camera to a top-down view)
    - "将镜头转为广角镜头" (Turn the camera to a wide-angle lens)
    - "将镜头转为特写镜头" (Turn the camera to a close-up)

    Example image_url:
    - S3: "s3://short-drama-assets/images/input.png"
    - S3 HTTPS: "https://short-drama-assets.s3.us-east-1.amazonaws.com/images/input.png"
    - HTTP: "https://example.com/image.jpg"

    Returns immediately with a session_id to track progress.
    Result will be uploaded to s3://short-drama-assets/images/
    """
    try:
        logger.info(
            f"Qwen i2i (ComfyUI workflow) - URL: {image_url}, Prompt: {prompt}, "
            f"Steps: {num_inference_steps}, CFG: {guidance_scale}, Shift: {scheduler_shift}"
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
            generation_func=edit_image,
            generation_kwargs={
                "input_image": input_image,
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "guidance_scale": guidance_scale,
                "true_cfg_scale": true_cfg_scale,
                "num_inference_steps": num_inference_steps,
                "seed": seed,
                "scale_to_megapixels": scale_to_megapixels,
                "use_cfg_norm": use_cfg_norm,
                "scheduler_shift": scheduler_shift,
            },
            file_extension="png",
            content_type="image/png",
            s3_folder="images",  # Upload to s3://short-drama-assets/images/
        )

        return SessionResponse(
            session_id=session_id,
            status="pending",
            message=(
                f"Image editing task submitted (ComfyUI workflow). "
                f"Use /api/{{session_id}}/status to check progress. "
                f"Result will be uploaded to s3://short-drama-assets/images/"
            ),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting Qwen i2i task: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to submit task: {str(e)}"
        )


@router.get("/info")
async def get_model_info():
    """
    Get information about the Qwen Multi-Angle model

    Returns details about loaded models, LoRAs, and current system state
    """
    try:
        return qwen_model_service.get_model_info()
    except Exception as e:
        logger.error(f"Error getting Qwen model info: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get model info: {str(e)}"
        )
