"""
Base classes and schemas for image/video generation models
"""

from pydantic import BaseModel
from typing import Optional
from PIL import Image
import io


class TextToImageRequest(BaseModel):
    """Request model for text-to-image generation"""

    prompt: str
    negative_prompt: Optional[str] = None
    width: Optional[int] = 512
    height: Optional[int] = 512
    num_inference_steps: Optional[int] = 50
    guidance_scale: Optional[float] = 7.5
    seed: Optional[int] = None


class ImageToImageParams(BaseModel):
    """Parameters for image-to-image generation"""

    prompt: Optional[str] = None
    strength: Optional[float] = 0.8
    guidance_scale: Optional[float] = 7.5
    num_inference_steps: Optional[int] = 50
    seed: Optional[int] = None


class SessionResponse(BaseModel):
    """Response model for generation endpoints"""

    session_id: str
    status: str
    message: str


def image_to_bytes(image: Image.Image, format: str = "PNG") -> bytes:
    """Convert PIL Image to bytes"""
    img_byte_arr = io.BytesIO()
    image.save(img_byte_arr, format=format)
    img_byte_arr.seek(0)
    return img_byte_arr.getvalue()
