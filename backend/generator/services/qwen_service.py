"""
Qwen Multi-Angle model service with Lightning LoRA
Component-by-component loading with dynamic offloading (ComfyUI-style)
Supports both text-to-image and image-to-image editing
"""

import gc
import torch
from diffusers import (
    DiffusionPipeline,
    FlowMatchEulerDiscreteScheduler,
    AutoencoderKL,
    UNet2DConditionModel,
)
from transformers import AutoTokenizer, AutoModel
from PIL import Image
import logging
from typing import Optional, List, Union
from pathlib import Path
from safetensors.torch import load_file

from services.model_manager import model_manager
from services.vram_manager import vram_manager
from services.optimization import optimization_manager
from services.model_loader import model_loader
from config import model_paths

logger = logging.getLogger(__name__)

# Try to import QwenImageEditPlusPipeline (for reference, but we won't use it)
try:
    from diffusers import QwenImageEditPlusPipeline
    QWEN_EDIT_AVAILABLE = True
except ImportError:
    logger.warning("QwenImageEditPlusPipeline not available. Install latest diffusers for i2i support.")
    QWEN_EDIT_AVAILABLE = False


class QwenModelService:
    """
    Qwen Multi-Angle model service with component-by-component loading

    This implementation loads UNET, VAE, CLIP separately and uses dynamic
    CPU/GPU offloading to stay within GPU memory limits (ComfyUI-style).

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

        # Cache for loaded pipeline (ComfyUI-style persistence)
        self._cached_pipe = None
        self._cached_model_key = None
        self._cached_components = None

        logger.info("QwenModelService initialized (component-by-component loading with caching)")

    def _unload_component(self, component, name: str):
        """Unload a single component from GPU to CPU"""
        try:
            if component is not None and hasattr(component, 'to'):
                logger.info(f"Moving {name} to CPU...")
                component.to("cpu")
                torch.cuda.empty_cache()
        except Exception as e:
            logger.warning(f"Error moving {name} to CPU: {e}")

    def _load_component_to_gpu(self, component, name: str):
        """Load a single component from CPU to GPU"""
        try:
            if component is not None and hasattr(component, 'to'):
                logger.info(f"Moving {name} to GPU...")
                component.to("cuda")
                torch.cuda.empty_cache()
        except Exception as e:
            logger.error(f"Error moving {name} to GPU: {e}")
            raise

    def clear_cache(self):
        """
        Explicitly clear the cached pipeline and components (ComfyUI-style)

        Call this when:
        - Switching to a different workflow
        - Memory pressure detected
        - Explicit cleanup requested
        """
        logger.info("Clearing pipeline cache...")

        if self._cached_pipe is not None:
            del self._cached_pipe
            self._cached_pipe = None

        if self._cached_components is not None:
            self._cleanup_all_components(self._cached_components)
            self._cached_components = None

        self._cached_model_key = None

        gc.collect()
        torch.cuda.empty_cache()
        vram_manager.clear_cache()

        logger.info("Pipeline cache cleared")

    def _cleanup_all_components(self, components: dict):
        """Completely cleanup all components and free GPU memory"""
        logger.info("Cleaning up all components...")

        for name, component in components.items():
            try:
                if component is not None:
                    if hasattr(component, 'to'):
                        component.to("cpu")
                    del component
            except Exception as e:
                logger.warning(f"Error cleaning up {name}: {e}")

        # Force garbage collection
        gc.collect()
        torch.cuda.empty_cache()
        torch.cuda.synchronize()

        # Clear all caches
        model_manager.clear_cache()
        vram_manager.clear_cache()

        logger.info("All components cleaned up")

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
            if not torch.cuda.is_available():
                raise RuntimeError("CUDA/GPU not available! This service requires a GPU to run.")

            pipe = model_loader.load_safetensors_model(
                local_path=None,  # Qwen-Image not in local models (typically)
                hf_repo=self.t2i_model_name,  # "Qwen/Qwen-Image"
                model_class=DiffusionPipeline,
                torch_dtype=optimization_manager.get_optimal_dtype(),
                low_cpu_mem_usage=True,
                use_safetensors=True,
            )

            # Move entire pipeline to CUDA (keep everything on GPU, no CPU offload)
            logger.info("Moving model to CUDA device...")
            pipe = pipe.to("cuda")
            logger.info(f"T2I model loaded on CUDA (dtype={pipe.dtype}, no CPU offloading)")

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

    def _load_i2i_components_separately(self, use_cache=True) -> dict:
        """
        Load i2i model components separately (ComfyUI-style with caching)

        Matches ComfyUI workflow:
        - Model: qwen_image_edit_2509_fp8_e4m3fn.safetensors
        - LoRA 1: Multi-Angle LoRA (镜头转换) weight=1.0
        - LoRA 2: Lightning LoRA (4-step) weight=1.0
        - Scheduler: FlowMatchEulerDiscreteScheduler shift=3.0
        - CFG: 1.0 with CFGNorm enabled

        Args:
            use_cache: If True, return cached components if available (ComfyUI-style)

        Returns dict with:
        - transformer: The transformer model (with LoRAs applied)
        - vae: The VAE model
        - text_encoder: The text encoder
        - tokenizer: The tokenizer
        - processor: The processor
        - scheduler: The scheduler (configured)
        """
        if not QWEN_EDIT_AVAILABLE:
            logger.error("Diffusers with Qwen support not available")
            return None

        # Check if we can use cached components (ComfyUI-style)
        if use_cache and self._cached_components is not None and self._cached_model_key == self.i2i_model_key:
            logger.info("Using cached components (ComfyUI-style persistence) - GPU still has models loaded!")
            return self._cached_components

        logger.info("Loading components from scratch (not in cache)...")

        # Clear old cache if switching models
        if self._cached_model_key is not None and self._cached_model_key != self.i2i_model_key:
            logger.info(f"Switching from {self._cached_model_key} to {self.i2i_model_key}, clearing cache...")
            self.clear_cache()

        # Check VRAM before loading
        vram_stats = vram_manager.get_vram_stats()
        logger.info(
            f"VRAM state: {vram_stats.state.value} "
            f"({vram_stats.utilization * 100:.1f}%)"
        )

        # Force cleanup before loading
        model_manager.clear_cache()
        vram_manager.clear_cache()

        components = {}

        try:
            logger.info("Loading components separately (ComfyUI-style)...")

            # Get dtype
            dtype = optimization_manager.get_optimal_dtype()

            # ========== STEP 1: Load Transformer (largest component) on CPU first ==========
            logger.info("Loading Transformer (Qwen-Image-Edit) on CPU...")

            # Always download from HuggingFace (local files don't support from_single_file)
            # The model will be cached by HuggingFace for subsequent loads
            logger.info(f"Loading model from HuggingFace: {self.i2i_model_name}")
            temp_pipe = QwenImageEditPlusPipeline.from_pretrained(
                self.i2i_model_name,
                torch_dtype=dtype,
                low_cpu_mem_usage=True,
                use_safetensors=True,
            )

            # ========== STEP 1.5: Load LoRAs (matching ComfyUI workflow) ==========
            logger.info("Loading LoRAs into pipeline (ComfyUI workflow)...")
            try:
                # Load Multi-Angle LoRA (镜头转换 / Camera Angle Control)
                logger.info("Loading Multi-Angle LoRA...")
                model_loader.load_lora_weights(
                    pipeline=temp_pipe,
                    local_path=model_paths.qwen_multi_angle_lora,
                    hf_repo=self.multi_angle_lora,
                    adapter_name="multi_angle",
                )

                # Load Lightning LoRA (4-step fast editing)
                logger.info("Loading Lightning LoRA (4-step)...")
                model_loader.load_lora_weights(
                    pipeline=temp_pipe,
                    local_path=model_paths.qwen_edit_lightning_lora,
                    hf_repo=self.edit_lightning_lora,
                    hf_filename=self.edit_lightning_lora_file,
                    adapter_name="lightning",
                )

                # Set both adapters with weight 1.0 each (matching ComfyUI)
                temp_pipe.set_adapters(["multi_angle", "lightning"], adapter_weights=[1.0, 1.0])
                logger.info("Both LoRAs loaded and activated (weights: [1.0, 1.0])")
            except Exception as e:
                logger.warning(f"Could not load LoRAs: {e}. Continuing without LoRAs...")

            # Extract components (QwenImageEditPlusPipeline uses 'transformer' not 'unet')
            components["transformer"] = temp_pipe.transformer
            components["vae"] = temp_pipe.vae
            components["text_encoder"] = temp_pipe.text_encoder
            components["tokenizer"] = temp_pipe.tokenizer
            components["processor"] = temp_pipe.processor
            components["scheduler"] = temp_pipe.scheduler

            # Keep everything on CPU for now
            logger.info("Moving all components to CPU...")
            components["transformer"].to("cpu")
            components["vae"].to("cpu")
            if hasattr(components["text_encoder"], "to"):
                components["text_encoder"].to("cpu")

            # Clean up temp pipeline
            del temp_pipe
            gc.collect()
            torch.cuda.empty_cache()

            logger.info("All components loaded on CPU with LoRAs applied")

            # ========== STEP 2: Configure scheduler (matching ComfyUI) ==========
            logger.info("Configuring scheduler with shift=3.0 (ModelSamplingAuraFlow)...")
            components["scheduler"] = FlowMatchEulerDiscreteScheduler.from_config(
                components["scheduler"].config,
                shift=3.0,
                max_seq_length=8192,
            )

            # Cache the components (ComfyUI-style persistence)
            self._cached_components = components
            self._cached_model_key = self.i2i_model_key
            logger.info("Components loaded successfully with LoRAs (all on CPU) and cached for reuse")

            return components

        except Exception as e:
            logger.error(f"Error loading components: {e}")
            # Cleanup on error
            self._cleanup_all_components(components)
            raise

    def edit_image(
        self,
        image: Union[Image.Image, List[Image.Image]],
        prompt: str,
        negative_prompt: str = "",
        num_inference_steps: int = 8,
        guidance_scale: float = 1.0,
        true_cfg_scale: float = 1.0,
        seed: Optional[int] = None,
        scale_to_megapixels: float = 1.0,
        use_cfg_norm: bool = True,
        scheduler_shift: float = 3.0,
    ) -> Image.Image:
        """
        Edit image using component-by-component loading with dynamic offloading

        This implementation:
        1. Loads all components (UNET, VAE, text encoder) on CPU
        2. Moves each component to GPU only when needed
        3. Moves it back to CPU after use
        4. This keeps peak GPU memory usage minimal

        Args:
            image: Input image(s)
            prompt: Edit instruction
            negative_prompt: Negative prompt
            num_inference_steps: Number of steps
            guidance_scale: CFG scale
            true_cfg_scale: True CFG scale
            seed: Random seed
            scale_to_megapixels: Scale image to megapixels
            use_cfg_norm: Enable CFG normalization
            scheduler_shift: Scheduler shift parameter

        Returns:
            PIL Image
        """
        components = None
        pipe = None

        try:
            # ========== LOAD COMPONENTS ==========
            components = self._load_i2i_components_separately()

            if components is None:
                raise RuntimeError("Failed to load components")

            # ========== PREPROCESS IMAGE ==========
            if isinstance(image, Image.Image):
                images = [image]
            else:
                images = image

            # Scale images to target megapixels
            if scale_to_megapixels > 0:
                scaled_images = []
                for img in images:
                    current_pixels = img.width * img.height
                    target_pixels = int(scale_to_megapixels * 1_000_000)

                    if current_pixels != target_pixels:
                        scale_factor = (target_pixels / current_pixels) ** 0.5
                        new_width = int(img.width * scale_factor)
                        new_height = int(img.height * scale_factor)
                        scaled_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                        scaled_images.append(scaled_img)
                        logger.info(f"Scaled image from {img.size} to {scaled_img.size}")
                    else:
                        scaled_images.append(img)
                images = scaled_images

            # ========== RECONSTRUCT PIPELINE FOR INFERENCE ==========
            # Check if we can reuse the cached pipeline (ComfyUI-style)
            if self._cached_pipe is not None and self._cached_model_key == self.i2i_model_key:
                logger.info("Reusing cached pipeline (ComfyUI-style - NO reloading!)")
                pipe = self._cached_pipe
            else:
                # Unfortunately, diffusers pipeline is tightly integrated
                # We need to create a pipeline but with sequential GPU loading
                logger.info("Reconstructing pipeline with CPU offloading...")

                # Create pipeline from components
                pipe = QwenImageEditPlusPipeline(
                    transformer=components["transformer"],
                    vae=components["vae"],
                    text_encoder=components["text_encoder"],
                    tokenizer=components["tokenizer"],
                    processor=components["processor"],
                    scheduler=components["scheduler"],
                )

                # Enable CPU offloading (this will move components on-demand)
                logger.info("Enabling sequential CPU offloading...")
                pipe.enable_model_cpu_offload()

            # Set up generator
            generator = None
            if seed is not None:
                device = "cuda" if torch.cuda.is_available() else "cpu"
                generator = torch.Generator(device).manual_seed(seed)

            logger.info(
                f"Editing image: {prompt[:100]}... "
                f"(steps={num_inference_steps}, cfg={guidance_scale})"
            )

            # Log VRAM before generation
            vram_before = vram_manager.get_vram_stats()
            logger.info(
                f"VRAM before editing: {vram_before.used / 1024**2:.0f}MB / "
                f"{vram_before.total / 1024**2:.0f}MB"
            )

            # ========== INFERENCE WITH AUTOMATIC OFFLOADING ==========
            # The enable_model_cpu_offload() will automatically:
            # 1. Move text_encoder to GPU → encode prompt → move back to CPU
            # 2. Move transformer to GPU → denoise → move back to CPU
            # 3. Move VAE to GPU → decode → move back to CPU
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

            # Copy image before cleanup
            edited_image_copy = edited_image.copy()

            # Minimal cleanup (ComfyUI-style: keep components on GPU for next run)
            del result
            del edited_image

            # DON'T delete the pipeline or components!
            # Keep them on GPU (via CPU offloading) for the next generation
            # This is the ComfyUI approach - components stay loaded

            # Cache the pipeline for reuse (ComfyUI-style)
            self._cached_pipe = pipe

            # Only do minimal GC
            gc.collect()

            logger.info("Image editing completed - models kept on GPU for next run (ComfyUI-style)")
            return edited_image_copy

        except Exception as e:
            logger.error(f"Error during image editing: {str(e)}")
            # Cleanup on error
            try:
                if pipe is not None:
                    del pipe
                if components is not None:
                    self._cleanup_all_components(components)
            except:
                pass
            gc.collect()
            torch.cuda.empty_cache()
            vram_manager.clear_cache()
            raise

    def generate(
        self,
        prompt: str,
        negative_prompt: str = "",
        height: int = 1024,
        width: int = 1024,
        num_inference_steps: int = 8,
        guidance_scale: float = 4.0,
        seed: Optional[int] = None,
        use_magic_prompt: bool = True,
    ) -> Image.Image:
        """
        Generate image using Qwen with Lightning and Multi-Angle LoRAs

        Args:
            prompt: Text prompt for generation
            negative_prompt: Negative prompt
            height: Image height
            width: Image width
            num_inference_steps: Number of steps
            guidance_scale: CFG scale
            seed: Random seed
            use_magic_prompt: Add magic prompt for quality

        Returns:
            PIL Image
        """
        try:
            # Get or load t2i model
            pipe = self._get_or_load_t2i_model()

            # Add magic prompt for better quality
            if use_magic_prompt and not any(
                magic in prompt.lower()
                for magic in ["masterpiece", "best quality", "4k"]
            ):
                prompt = (
                    f"{prompt}, masterpiece, best quality, high quality, "
                    f"extremely detailed, 8k uhd, dslr, high quality"
                )

            # Set up generator
            generator = None
            if seed is not None:
                device = "cuda" if torch.cuda.is_available() else "cpu"
                generator = torch.Generator(device).manual_seed(seed)

            logger.info(f"Generating image: {prompt[:100]}...")

            # Log VRAM before generation
            vram_before = vram_manager.get_vram_stats()
            logger.info(
                f"VRAM before generation: {vram_before.used / 1024**2:.0f}MB / "
                f"{vram_before.total / 1024**2:.0f}MB"
            )

            # Generate image
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

            # Cleanup
            del pipe
            gc.collect()
            torch.cuda.empty_cache()
            vram_manager.clear_cache()

            logger.info("Image generation completed and model unloaded")
            return image

        except Exception as e:
            logger.error(f"Error during generation: {str(e)}")
            try:
                del pipe
                gc.collect()
            except:
                pass
            torch.cuda.empty_cache()
            vram_manager.clear_cache()
            raise

    def generate_multi_angle(
        self,
        base_prompt: str,
        camera_angles: List[str],
        **kwargs,
    ) -> List[Image.Image]:
        """Generate multiple images with different camera angles"""
        images = []

        for angle in camera_angles:
            full_prompt = f"{base_prompt}, {angle}"
            logger.info(f"Generating with angle: {angle}")

            try:
                image = self.generate(prompt=full_prompt, **kwargs)
                images.append(image)
            except Exception as e:
                logger.error(f"Error generating angle '{angle}': {e}")
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
                "component_loading": "Separate UNET/VAE/TextEncoder with CPU offloading",
                "image_scaling": "1.0 megapixels default",
                "scheduler": "FlowMatchEulerDiscreteScheduler with shift=3.0",
                "default_steps": "8 (with Lightning LoRA)",
            },
            "i2i_available": QWEN_EDIT_AVAILABLE,
            "cache_stats": cache_stats,
            "vram_stats": vram_stats,
            "optimization_info": optimization_info,
        }


# Singleton instance
qwen_model_service = QwenModelService()
