"""
Qwen Multi-Angle model service with Lightning LoRA
Combines Qwen-Image + Lightning LoRA + Multi-Angle LoRA
Supports both text-to-image and image-to-image editing
"""

import torch
from diffusers import DiffusionPipeline, FlowMatchEulerDiscreteScheduler
from PIL import Image
import logging
from typing import Optional, List, Union

from services.model_manager import model_manager
from services.vram_manager import vram_manager
from services.optimization import optimization_manager
from services.model_loader import model_loader
from config import model_paths

logger = logging.getLogger(__name__)

# Try to import QwenImageEditPlusPipeline (requires latest diffusers)
try:
    from diffusers import QwenImageEditPlusPipeline
    QWEN_EDIT_AVAILABLE = True
except ImportError:
    logger.warning("QwenImageEditPlusPipeline not available. Install latest diffusers for i2i support.")
    QWEN_EDIT_AVAILABLE = False


class QwenModelService:
    """
    Qwen Multi-Angle model service with advanced resource management

    Models:
    - Base: Qwen/Qwen-Image
    - LoRA 1: lightx2v/Qwen-Image-Lightning (8-step fast generation)
    - LoRA 2: dx8152/Qwen-Edit-2509-Multiple-angles (camera angle control)
    """

    def __init__(self):
        # Text-to-Image model
        self.t2i_model_name = "Qwen/Qwen-Image"
        self.lightning_lora = "lightx2v/Qwen-Image-Lightning"
        self.lightning_lora_file = "Qwen-Image-Lightning-8steps-V1.0.safetensors"

        # Image-to-Image model
        self.i2i_model_name = "Qwen/Qwen-Image-Edit-2509"
        self.multi_angle_lora = "dx8152/Qwen-Edit-2509-Multiple-angles"
        self.edit_lightning_lora = "lightx2v/Qwen-Image-Edit-Lightning"
        self.edit_lightning_lora_file = "Qwen-Image-Edit-Lightning-4steps-V1.0.safetensors"

        self.t2i_model_key = "qwen-t2i"
        self.i2i_model_key = "qwen-i2i"

        logger.info("QwenModelService initialized (t2i + i2i support)")

    def _get_or_load_t2i_model(self) -> DiffusionPipeline:
        """Get text-to-image model from cache or load it with LoRAs"""
        # Check VRAM before loading
        vram_stats = vram_manager.get_vram_stats()
        logger.info(
            f"VRAM state: {vram_stats.state.value} "
            f"({vram_stats.utilization * 100:.1f}%)"
        )

        # Cleanup if needed
        vram_manager.cleanup_if_needed()

        try:
            # Load base model with fallback: local first, then HuggingFace
            logger.info("Loading Qwen t2i model...")
            pipe = model_loader.load_safetensors_model(
                local_path=None,  # Qwen-Image not in local models (typically)
                hf_repo=self.t2i_model_name,  # "Qwen/Qwen-Image"
                model_class=DiffusionPipeline,
                torch_dtype=optimization_manager.get_optimal_dtype(),
                low_cpu_mem_usage=True,
                use_safetensors=True,
            )

            # Configure scheduler for Lightning LoRA (8 steps)
            pipe.scheduler = FlowMatchEulerDiscreteScheduler.from_config(
                pipe.scheduler.config,
                shift=3.0,
                max_seq_length=8192,
            )

            # Load Lightning LoRA with fallback
            logger.info("Loading Qwen-Image-Lightning LoRA...")
            try:
                model_loader.load_lora_weights(
                    pipeline=pipe,
                    local_path=None,  # Not in local models typically
                    hf_repo=self.lightning_lora,
                    hf_filename=self.lightning_lora_file,
                    adapter_name="lightning",
                )
                pipe.set_adapters(["lightning"], adapter_weights=[1.0])
                logger.info("Lightning LoRA loaded successfully")
            except Exception as e:
                logger.warning(f"Could not load Lightning LoRA: {e}")

            # Apply optimizations
            optimization_manager.optimize_model(pipe)

            return pipe

        except Exception as e:
            logger.error(f"Error loading Qwen t2i model: {e}")
            raise

    def _get_or_load_i2i_model(self) -> Union[DiffusionPipeline, None]:
        """Get image-to-image model from cache or load it with Multi-Angle LoRA"""
        if not QWEN_EDIT_AVAILABLE:
            logger.error("QwenImageEditPlusPipeline not available")
            return None

        # Check VRAM before loading
        vram_stats = vram_manager.get_vram_stats()
        logger.info(
            f"VRAM state: {vram_stats.state.value} "
            f"({vram_stats.utilization * 100:.1f}%)"
        )

        # Cleanup if needed
        vram_manager.cleanup_if_needed()

        try:
            # Load edit model with fallback: try local first, then HuggingFace
            logger.info("Loading Qwen i2i model...")
            pipe = model_loader.load_safetensors_model(
                local_path=model_paths.qwen_image_edit_unet,  # Try local first
                hf_repo=self.i2i_model_name,  # Fallback to "Qwen/Qwen-Image-Edit-2509"
                model_class=QwenImageEditPlusPipeline,
                torch_dtype=optimization_manager.get_optimal_dtype(),
                low_cpu_mem_usage=True,
                use_safetensors=True,
            )

            # Load LoRAs (like ComfyUI workflow: Multi-Angle + Lightning)
            logger.info("Loading Multi-Angle and Lightning LoRAs...")
            try:
                # Load Multi-Angle LoRA for camera control (镜头转换)
                model_loader.load_lora_weights(
                    pipeline=pipe,
                    local_path=model_paths.qwen_multi_angle_lora,  # Try local first
                    hf_repo=self.multi_angle_lora,  # Fallback to HF
                    adapter_name="multi_angle",
                )
                logger.info("Multi-Angle LoRA loaded successfully")

                # Load Lightning LoRA for fast 8-step editing
                model_loader.load_lora_weights(
                    pipeline=pipe,
                    local_path=model_paths.qwen_edit_lightning_lora,  # Try local first
                    hf_repo=self.edit_lightning_lora,  # Fallback to HF
                    hf_filename=self.edit_lightning_lora_file,
                    adapter_name="lightning",
                )
                logger.info("Edit-Lightning LoRA loaded successfully")

                # Set both adapters (matching ComfyUI workflow)
                pipe.set_adapters(["multi_angle", "lightning"], adapter_weights=[1.0, 1.0])
                logger.info("Both LoRAs activated")
            except Exception as e:
                logger.warning(f"Could not load LoRAs: {e}")

            # Apply optimizations
            optimization_manager.optimize_model(pipe)

            return pipe

        except Exception as e:
            logger.error(f"Error loading Qwen i2i model: {e}")
            raise

    def generate(
        self,
        prompt: str,
        negative_prompt: str = "",
        height: int = 1024,
        width: int = 1024,
        num_inference_steps: int = 8,  # Lightning LoRA optimized for 8 steps
        guidance_scale: float = 4.0,
        seed: Optional[int] = None,
        use_magic_prompt: bool = True,
    ) -> Image.Image:
        """
        Generate image using Qwen with Lightning and Multi-Angle LoRAs

        Args:
            prompt: Text prompt for generation (camera angle instructions supported)
            negative_prompt: Negative prompt
            height: Image height
            width: Image width
            num_inference_steps: Number of steps (8 recommended for Lightning)
            guidance_scale: CFG scale (4.0 recommended for Qwen)
            seed: Random seed for reproducibility
            use_magic_prompt: Add magic prompt suffix for better quality

        Returns:
            PIL Image

        Camera angle prompt examples:
        - "Move the camera forward"
        - "Rotate left 45 degrees"
        - "Turn to top-down view"
        - "Change to wide-angle view"
        - "Close-up perspective"
        """
        try:
            # Get or load t2i model
            pipe = self._get_or_load_t2i_model()

            # Add magic prompt for better quality (English)
            if use_magic_prompt and not any(
                magic in prompt.lower()
                for magic in ["masterpiece", "best quality", "4k"]
            ):
                prompt = (
                    f"{prompt}, masterpiece, best quality, high quality, "
                    f"extremely detailed, 8k uhd, dslr, high quality"
                )

            # Set up generator for reproducibility
            generator = None
            if seed is not None:
                device = "cuda" if torch.cuda.is_available() else "cpu"
                generator = torch.Generator(device).manual_seed(seed)

            logger.info(f"Generating image with Qwen: {prompt[:100]}...")

            # Log VRAM before generation
            vram_before = vram_manager.get_vram_stats()
            logger.info(
                f"VRAM before generation: {vram_before.used / 1024**2:.0f}MB / "
                f"{vram_before.total / 1024**2:.0f}MB"
            )

            # Generate image with automatic mixed precision
            with optimization_manager.autocast():
                result = pipe(
                    prompt=prompt,
                    negative_prompt=negative_prompt,
                    height=height,
                    width=width,
                    num_inference_steps=num_inference_steps,
                    true_cfg_scale=guidance_scale,
                    generator=generator,
                )

            image = result.images[0]

            # Log VRAM after generation
            vram_after = vram_manager.get_vram_stats()
            logger.info(
                f"VRAM after generation: {vram_after.used / 1024**2:.0f}MB / "
                f"{vram_after.total / 1024**2:.0f}MB"
            )

            # Cleanup if VRAM is high
            vram_manager.cleanup_if_needed()

            logger.info("Image generation completed successfully")
            return image

        except Exception as e:
            logger.error(f"Error during Qwen generation: {str(e)}")
            # Clear cache on error to free memory
            vram_manager.clear_cache()
            raise

    def edit_image(
        self,
        image: Union[Image.Image, List[Image.Image]],
        prompt: str,
        negative_prompt: str = "",
        num_inference_steps: int = 8,  # Using Lightning LoRA for fast editing
        guidance_scale: float = 1.0,  # CFG scale
        true_cfg_scale: float = 1.0,  # True CFG scale
        seed: Optional[int] = None,
        scale_to_megapixels: float = 1.0,  # Scale image to specific megapixels
        use_cfg_norm: bool = True,  # Use CFG normalization
        scheduler_shift: float = 3.0,  # ModelSamplingAuraFlow shift parameter
    ) -> Image.Image:
        """
        Edit image using Qwen-Image-Edit with Multi-Angle LoRA

        Replicates the ComfyUI workflow with all advanced features:
        - Image scaling to specific megapixels
        - CFG normalization
        - ModelSamplingAuraFlow with custom shift
        - Lightning LoRA for fast 8-step editing
        - Multi-Angle LoRA for camera control

        Args:
            image: Input image(s) (PIL Image or list of 1-3 PIL Images)
            prompt: Edit instruction (camera angle changes supported)
            negative_prompt: Negative prompt
            num_inference_steps: Number of steps (8 recommended with Lightning)
            guidance_scale: CFG scale (1.0 recommended)
            true_cfg_scale: True CFG scale (1.0 recommended)
            seed: Random seed for reproducibility
            scale_to_megapixels: Scale image to specific megapixels (1.0 = 1MP)
            use_cfg_norm: Enable CFG normalization
            scheduler_shift: ModelSamplingAuraFlow shift parameter (3.0 recommended)

        Returns:
            PIL Image

        Camera angle prompt examples for editing:
        - "将镜头向前移动" (Move the camera forward)
        - "将镜头向左旋转45度" (Rotate the camera 45 degrees to the left)
        - "将镜头转为俯视" (Turn the camera to a top-down view)
        - "将镜头转为广角镜头" (Turn the camera to a wide-angle lens)
        - "将镜头转为特写镜头" (Turn the camera to a close-up)
        """
        try:
            # Get or load i2i model
            pipe = self._get_or_load_i2i_model()

            if pipe is None:
                raise RuntimeError(
                    "Qwen Image Edit model not available. "
                    "Install latest diffusers: pip install git+https://github.com/huggingface/diffusers.git"
                )

            # Ensure image is a list
            if isinstance(image, Image.Image):
                images = [image]
            else:
                images = image

            # Scale images to target megapixels (like ImageScaleToTotalPixels node)
            if scale_to_megapixels > 0:
                scaled_images = []
                for img in images:
                    current_pixels = img.width * img.height
                    target_pixels = int(scale_to_megapixels * 1_000_000)

                    if current_pixels != target_pixels:
                        scale_factor = (target_pixels / current_pixels) ** 0.5
                        new_width = int(img.width * scale_factor)
                        new_height = int(img.height * scale_factor)
                        # Use LANCZOS for high-quality downsampling (like ComfyUI)
                        scaled_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                        scaled_images.append(scaled_img)
                        logger.info(f"Scaled image from {img.size} to {scaled_img.size}")
                    else:
                        scaled_images.append(img)
                images = scaled_images

            # Configure scheduler with shift parameter (ModelSamplingAuraFlow)
            if scheduler_shift != pipe.scheduler.config.get("shift", 3.0):
                pipe.scheduler = FlowMatchEulerDiscreteScheduler.from_config(
                    pipe.scheduler.config,
                    shift=scheduler_shift,
                    max_seq_length=8192,
                )
                logger.info(f"Configured scheduler with shift={scheduler_shift}")

            # Set up generator for reproducibility
            generator = None
            if seed is not None:
                device = "cuda" if torch.cuda.is_available() else "cpu"
                generator = torch.Generator(device).manual_seed(seed)

            logger.info(
                f"Editing image with Qwen: {prompt[:100]}... "
                f"(steps={num_inference_steps}, cfg={guidance_scale}, "
                f"true_cfg={true_cfg_scale}, shift={scheduler_shift})"
            )

            # Log VRAM before generation
            vram_before = vram_manager.get_vram_stats()
            logger.info(
                f"VRAM before editing: {vram_before.used / 1024**2:.0f}MB / "
                f"{vram_before.total / 1024**2:.0f}MB"
            )

            # Edit image with automatic mixed precision
            # Note: CFG normalization is handled internally by the pipeline
            with optimization_manager.autocast():
                result = pipe(
                    image=images,
                    prompt=prompt,
                    negative_prompt=negative_prompt,
                    num_inference_steps=num_inference_steps,
                    guidance_scale=guidance_scale,
                    true_cfg_scale=true_cfg_scale,
                    generator=generator,
                )

            edited_image = result.images[0]

            # Log VRAM after generation
            vram_after = vram_manager.get_vram_stats()
            logger.info(
                f"VRAM after editing: {vram_after.used / 1024**2:.0f}MB / "
                f"{vram_after.total / 1024**2:.0f}MB"
            )

            # Cleanup if VRAM is high
            vram_manager.cleanup_if_needed()

            logger.info("Image editing completed successfully")
            return edited_image

        except Exception as e:
            logger.error(f"Error during Qwen image editing: {str(e)}")
            # Clear cache on error to free memory
            vram_manager.clear_cache()
            raise

    def generate_multi_angle(
        self,
        base_prompt: str,
        camera_angles: List[str],
        **kwargs,
    ) -> List[Image.Image]:
        """
        Generate multiple images with different camera angles

        Args:
            base_prompt: Base prompt describing the scene
            camera_angles: List of camera angle descriptions
            **kwargs: Additional generation parameters

        Returns:
            List of generated images

        Example:
            camera_angles = [
                "front view",
                "rotate left 45 degrees",
                "top-down view",
                "close-up perspective"
            ]
        """
        images = []

        for angle in camera_angles:
            # Combine base prompt with camera angle instruction
            full_prompt = f"{base_prompt}, {angle}"

            logger.info(f"Generating with angle: {angle}")

            try:
                image = self.generate(prompt=full_prompt, **kwargs)
                images.append(image)
            except Exception as e:
                logger.error(f"Error generating angle '{angle}': {e}")
                # Continue with other angles
                continue

        return images

    def get_model_info(self) -> dict:
        """Get information about the Qwen models"""
        cache_stats = model_manager.get_cache_stats()
        vram_stats = vram_manager.get_memory_summary()
        optimization_info = optimization_manager.get_optimization_info()

        return {
            "models": {
                "t2i": self.t2i_model_name,
                "i2i": self.i2i_model_name,
            },
            "loras": {
                "t2i_lightning": f"{self.lightning_lora}/{self.lightning_lora_file}",
                "i2i_multi_angle": self.multi_angle_lora,
                "i2i_lightning": f"{self.edit_lightning_lora}/{self.edit_lightning_lora_file}",
            },
            "workflow_features": {
                "image_scaling": "1.0 megapixels default",
                "scheduler": "FlowMatchEulerDiscreteScheduler with shift=3.0",
                "cfg_norm": "Enabled by default",
                "default_steps": "8 (with Lightning LoRA)",
            },
            "i2i_available": QWEN_EDIT_AVAILABLE,
            "cache_stats": cache_stats,
            "vram_stats": vram_stats,
            "optimization_info": optimization_info,
        }


# Singleton instance
qwen_model_service = QwenModelService()
