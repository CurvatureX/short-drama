"""
Flux model service with advanced resource management
Using ComfyUI-style optimizations
"""

import torch
from diffusers import FluxPipeline
from PIL import Image
import logging
from typing import Optional

from services.model_manager import model_manager
from services.vram_manager import vram_manager
from services.optimization import optimization_manager

logger = logging.getLogger(__name__)


class FluxModelService:
    """
    Advanced Flux model service with resource management

    Features:
    - Model caching and LRU eviction
    - Automatic VRAM management
    - Mixed precision inference
    - Attention optimizations
    - CPU offloading when needed
    """

    def __init__(self):
        self.model_name = "black-forest-labs/FLUX.1-dev"
        self.model_key = "flux-dev"

        logger.info("FluxModelService initialized with advanced resource management")

    def _get_or_load_model(self) -> FluxPipeline:
        """Get model from cache or load it"""
        # Check VRAM before loading
        vram_stats = vram_manager.get_vram_stats()
        logger.info(
            f"VRAM state: {vram_stats.state.value} "
            f"({vram_stats.utilization * 100:.1f}%)"
        )

        # Cleanup if needed
        vram_manager.cleanup_if_needed()

        # Load model using model manager (handles caching)
        model = model_manager.load_model(
            model_name=self.model_name,
            model_class=FluxPipeline,
            variant="default",
            torch_dtype=optimization_manager.get_optimal_dtype(),
            low_cpu_mem_usage=True,
            use_safetensors=True,
        )

        # Apply optimizations
        optimization_manager.optimize_model(model)

        return model

    def generate(
        self,
        prompt: str,
        height: int = 1024,
        width: int = 1024,
        guidance_scale: float = 3.5,
        num_inference_steps: int = 50,
        max_sequence_length: int = 512,
        seed: Optional[int] = None,
    ) -> Image.Image:
        """
        Generate image using Flux.1-dev with optimizations

        Args:
            prompt: Text prompt for generation
            height: Image height
            width: Image width
            guidance_scale: Guidance scale for generation
            num_inference_steps: Number of inference steps
            max_sequence_length: Maximum sequence length
            seed: Random seed for reproducibility

        Returns:
            PIL Image
        """
        try:
            # Get or load model
            pipe = self._get_or_load_model()

            # Set up generator for reproducibility
            generator = None
            if seed is not None:
                device = "cuda" if torch.cuda.is_available() else "cpu"
                generator = torch.Generator(device).manual_seed(seed)

            logger.info(f"Generating image with Flux.1-dev: {prompt[:100]}...")

            # Log VRAM before generation
            vram_before = vram_manager.get_vram_stats()
            logger.info(
                f"VRAM before generation: {vram_before.used / 1024**2:.0f}MB / "
                f"{vram_before.total / 1024**2:.0f}MB"
            )

            # Generate image with automatic mixed precision
            with optimization_manager.autocast():
                result = pipe(
                    prompt,
                    height=height,
                    width=width,
                    guidance_scale=guidance_scale,
                    num_inference_steps=num_inference_steps,
                    max_sequence_length=max_sequence_length,
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
            logger.error(f"Error during Flux generation: {str(e)}")
            # Clear cache on error to free memory
            vram_manager.clear_cache()
            raise

    def get_model_info(self) -> dict:
        """Get information about the model"""
        cache_stats = model_manager.get_cache_stats()
        vram_stats = vram_manager.get_memory_summary()
        optimization_info = optimization_manager.get_optimization_info()

        return {
            "model_name": self.model_name,
            "cache_stats": cache_stats,
            "vram_stats": vram_stats,
            "optimization_info": optimization_info,
        }

    def unload_model(self):
        """Manually unload the model"""
        model_manager.clear_cache()
        vram_manager.clear_cache()
        logger.info("Flux model unloaded manually")


# Singleton instance
flux_model_service = FluxModelService()
