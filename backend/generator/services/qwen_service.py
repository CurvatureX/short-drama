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
            # Load base model using model manager
            pipe = model_manager.load_model(
                model_name=self.t2i_model_name,
                model_class=DiffusionPipeline,
                variant=self.t2i_model_key,
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

            # Load Lightning LoRA for fast generation
            logger.info("Loading Qwen-Image-Lightning LoRA...")
            try:
                pipe.load_lora_weights(
                    self.lightning_lora,
                    weight_name=self.lightning_lora_file,
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
            # Load edit model using model manager
            pipe = model_manager.load_model(
                model_name=self.i2i_model_name,
                model_class=QwenImageEditPlusPipeline,
                variant=self.i2i_model_key,
                torch_dtype=optimization_manager.get_optimal_dtype(),
                low_cpu_mem_usage=True,
                use_safetensors=True,
            )

            # Load Multi-Angle LoRA for camera control
            logger.info("Loading Multi-Angle LoRA...")
            try:
                pipe.load_lora_weights(
                    self.multi_angle_lora,
                    adapter_name="multi_angle",
                )
                pipe.set_adapters(["multi_angle"], adapter_weights=[1.0])
                logger.info("Multi-Angle LoRA loaded successfully")
            except Exception as e:
                logger.warning(f"Could not load Multi-Angle LoRA: {e}")

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
        num_inference_steps: int = 40,
        guidance_scale: float = 4.0,
        true_cfg_scale: float = 1.0,
        seed: Optional[int] = None,
    ) -> Image.Image:
        """
        Edit image using Qwen-Image-Edit with Multi-Angle LoRA

        Args:
            image: Input image(s) (PIL Image or list of 1-3 PIL Images)
            prompt: Edit instruction (camera angle changes supported)
            negative_prompt: Negative prompt
            num_inference_steps: Number of steps (40 recommended for editing)
            guidance_scale: CFG scale (4.0 recommended)
            true_cfg_scale: True CFG scale (1.0 recommended)
            seed: Random seed for reproducibility

        Returns:
            PIL Image

        Camera angle prompt examples for editing:
        - "Move the camera forward"
        - "Rotate view left 45 degrees"
        - "Change to top-down perspective"
        - "Zoom in closer"
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

            # Set up generator for reproducibility
            generator = None
            if seed is not None:
                device = "cuda" if torch.cuda.is_available() else "cpu"
                generator = torch.Generator(device).manual_seed(seed)

            logger.info(f"Editing image with Qwen: {prompt[:100]}...")

            # Log VRAM before generation
            vram_before = vram_manager.get_vram_stats()
            logger.info(
                f"VRAM before editing: {vram_before.used / 1024**2:.0f}MB / "
                f"{vram_before.total / 1024**2:.0f}MB"
            )

            # Edit image with automatic mixed precision
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
                "lightning": self.lightning_lora,
                "multi_angle": self.multi_angle_lora,
            },
            "i2i_available": QWEN_EDIT_AVAILABLE,
            "cache_stats": cache_stats,
            "vram_stats": vram_stats,
            "optimization_info": optimization_info,
        }


# Singleton instance
qwen_model_service = QwenModelService()
