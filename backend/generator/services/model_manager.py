"""
Model Manager with caching and efficient loading
Similar to ComfyUI's model management system
"""

import torch
from diffusers import FluxPipeline, DiffusionPipeline
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass
from enum import Enum
import threading
import time
import logging
from collections import OrderedDict

from services.vram_manager import vram_manager, VRAMState

logger = logging.getLogger(__name__)


class ModelState(Enum):
    """Model loading state"""
    UNLOADED = "unloaded"
    LOADING = "loading"
    LOADED_GPU = "loaded_gpu"
    LOADED_CPU = "loaded_cpu"
    OFFLOADING = "offloading"


@dataclass
class ModelInfo:
    """Information about a loaded model"""
    name: str
    model: Any
    state: ModelState
    memory_usage: int
    last_used: float
    load_count: int


class ModelManager:
    """
    Advanced model manager with caching, memory mapping, and dynamic loading

    Features:
    - LRU cache for models
    - Memory-mapped loading
    - Automatic CPU offloading
    - Model preloading
    - Usage tracking
    """

    def __init__(
        self,
        max_models_in_memory: int = 2,
        max_cache_size_gb: float = 20.0,
        enable_memory_efficient_loading: bool = True,
    ):
        self.max_models_in_memory = max_models_in_memory
        self.max_cache_size_gb = max_cache_size_gb
        self.enable_memory_efficient_loading = enable_memory_efficient_loading

        # Model cache (LRU)
        self.model_cache: OrderedDict[str, ModelInfo] = OrderedDict()

        # Threading locks
        self.lock = threading.RLock()

        # Device
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

        logger.info(
            f"ModelManager initialized: device={self.device}, "
            f"max_models={max_models_in_memory}, max_cache={max_cache_size_gb}GB"
        )

    def _get_model_key(self, model_name: str, variant: str = "default") -> str:
        """Generate unique key for model"""
        return f"{model_name}:{variant}"

    def load_model(
        self,
        model_name: str,
        model_class: type,
        variant: str = "default",
        torch_dtype: torch.dtype = torch.bfloat16,
        **load_kwargs,
    ) -> Any:
        """
        Load a model with caching and memory management

        Args:
            model_name: Model identifier (e.g., "black-forest-labs/FLUX.1-dev")
            model_class: Model class to instantiate
            variant: Model variant identifier
            torch_dtype: Torch data type for loading
            **load_kwargs: Additional kwargs for from_pretrained

        Returns:
            Loaded model
        """
        model_key = self._get_model_key(model_name, variant)

        with self.lock:
            # Check if model is in cache
            if model_key in self.model_cache:
                model_info = self.model_cache[model_key]

                # Move to end (most recently used)
                self.model_cache.move_to_end(model_key)
                model_info.last_used = time.time()
                model_info.load_count += 1

                logger.info(f"Model {model_key} loaded from cache")

                # Ensure model is on correct device
                if model_info.state == ModelState.LOADED_CPU:
                    self._move_to_gpu(model_info)

                return model_info.model

            # Check if we need to free up space
            self._evict_if_needed()

            # Load new model
            return self._load_new_model(
                model_name, model_class, variant, torch_dtype, **load_kwargs
            )

    def _load_new_model(
        self,
        model_name: str,
        model_class: type,
        variant: str,
        torch_dtype: torch.dtype,
        **load_kwargs,
    ) -> Any:
        """Load a new model from scratch"""
        model_key = self._get_model_key(model_name, variant)

        logger.info(f"Loading new model: {model_key}")

        # Check VRAM state
        vram_stats = vram_manager.get_vram_stats()

        try:
            # Load model with optimizations
            load_config = {
                "torch_dtype": torch_dtype,
                **load_kwargs,
            }

            # Use memory-efficient loading if enabled
            if self.enable_memory_efficient_loading and self.device == "cuda":
                load_config["low_cpu_mem_usage"] = True
                load_config["use_safetensors"] = True

            model = model_class.from_pretrained(model_name, **load_config)

            # Determine loading strategy based on VRAM
            if vram_stats.state in [VRAMState.HIGH, VRAMState.CRITICAL]:
                logger.warning("High VRAM usage, enabling CPU offloading")
                if hasattr(model, "enable_model_cpu_offload"):
                    model.enable_model_cpu_offload()
                state = ModelState.LOADED_CPU
            else:
                if self.device == "cuda":
                    if hasattr(model, "enable_model_cpu_offload"):
                        model.enable_model_cpu_offload()
                    state = ModelState.LOADED_GPU
                else:
                    state = ModelState.LOADED_CPU

            # Estimate memory usage
            memory_usage = self._estimate_model_memory(model)

            # Create model info
            model_info = ModelInfo(
                name=model_name,
                model=model,
                state=state,
                memory_usage=memory_usage,
                last_used=time.time(),
                load_count=1,
            )

            # Add to cache
            self.model_cache[model_key] = model_info

            # Register with VRAM manager
            vram_manager.register_model(model_key, memory_usage)

            logger.info(
                f"Model {model_key} loaded successfully. "
                f"Memory: {memory_usage / 1024**2:.2f}MB, State: {state.value}"
            )

            return model

        except Exception as e:
            logger.error(f"Failed to load model {model_key}: {e}")
            raise

    def _estimate_model_memory(self, model: Any) -> int:
        """Estimate memory usage of a model"""
        try:
            total_params = sum(p.numel() for p in model.parameters())
            # Estimate: 2 bytes per param for bfloat16, 4 for float32
            param_memory = total_params * 2  # Assuming bfloat16
            # Add 20% overhead for activations and buffers
            total_memory = int(param_memory * 1.2)
            return total_memory
        except Exception as e:
            logger.warning(f"Could not estimate model memory: {e}")
            return 0

    def _evict_if_needed(self):
        """Evict least recently used models if cache is full"""
        while len(self.model_cache) >= self.max_models_in_memory:
            # Remove oldest (least recently used)
            oldest_key, oldest_info = self.model_cache.popitem(last=False)

            logger.info(f"Evicting model from cache: {oldest_key}")

            # Unload model
            self._unload_model(oldest_info)

    def _unload_model(self, model_info: ModelInfo):
        """Unload a model and free memory"""
        try:
            # Delete model
            del model_info.model

            # Clear CUDA cache
            vram_manager.clear_cache()

            # Unregister from VRAM manager
            model_key = self._get_model_key(model_info.name)
            vram_manager.unregister_model(model_key)

            logger.info(f"Model {model_info.name} unloaded")

        except Exception as e:
            logger.error(f"Error unloading model {model_info.name}: {e}")

    def _move_to_gpu(self, model_info: ModelInfo):
        """Move model from CPU to GPU"""
        if self.device != "cuda" or model_info.state == ModelState.LOADED_GPU:
            return

        logger.info(f"Moving model {model_info.name} to GPU")
        vram_manager.cleanup_if_needed()
        model_info.state = ModelState.LOADED_GPU

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        with self.lock:
            return {
                "cached_models": len(self.model_cache),
                "max_models": self.max_models_in_memory,
                "models": [
                    {
                        "name": info.name,
                        "state": info.state.value,
                        "memory_mb": info.memory_usage / 1024**2,
                        "load_count": info.load_count,
                        "last_used": info.last_used,
                    }
                    for info in self.model_cache.values()
                ],
            }

    def clear_cache(self):
        """Clear all cached models"""
        with self.lock:
            for model_info in list(self.model_cache.values()):
                self._unload_model(model_info)

            self.model_cache.clear()
            logger.info("Model cache cleared")

    def preload_model(
        self,
        model_name: str,
        model_class: type,
        variant: str = "default",
        torch_dtype: torch.dtype = torch.bfloat16,
        **load_kwargs,
    ):
        """
        Preload a model in the background

        Useful for warming up models before they're needed
        """
        def _preload():
            try:
                self.load_model(
                    model_name, model_class, variant, torch_dtype, **load_kwargs
                )
                logger.info(f"Model {model_name} preloaded successfully")
            except Exception as e:
                logger.error(f"Failed to preload model {model_name}: {e}")

        thread = threading.Thread(target=_preload, daemon=True)
        thread.start()


# Singleton instance
model_manager = ModelManager(
    max_models_in_memory=2,
    max_cache_size_gb=20.0,
    enable_memory_efficient_loading=True,
)
