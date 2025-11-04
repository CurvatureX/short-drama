"""
Optimization utilities for efficient model inference
Mixed precision, attention optimizations, etc.
"""

import torch
import logging
from typing import Any, Optional
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class OptimizationManager:
    """
    Manages optimization techniques for models

    Features:
    - Mixed precision (AMP)
    - Attention optimizations
    - Memory-efficient attention
    - Gradient checkpointing
    """

    def __init__(self):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.amp_enabled = self.device == "cuda"

        # Check for xformers availability
        self.xformers_available = False
        try:
            import xformers
            self.xformers_available = True
            logger.info("xformers available for memory-efficient attention")
        except ImportError:
            logger.info("xformers not available, using default attention")

        # Check for Flash Attention
        self.flash_attention_available = False
        try:
            # Check if Flash Attention 2 is available in PyTorch
            if hasattr(torch.nn.functional, 'scaled_dot_product_attention'):
                self.flash_attention_available = True
                logger.info("Flash Attention available via PyTorch SDPA")
        except:
            pass

    @contextmanager
    def autocast(self, enabled: bool = True):
        """
        Context manager for automatic mixed precision

        Usage:
            with optimization_manager.autocast():
                output = model(input)
        """
        if enabled and self.amp_enabled:
            with torch.cuda.amp.autocast(dtype=torch.bfloat16):
                yield
        else:
            yield

    def enable_attention_optimization(self, model: Any) -> bool:
        """
        Enable attention optimization for a model

        Args:
            model: Model to optimize

        Returns:
            True if optimization was applied
        """
        try:
            # Try xformers first
            if self.xformers_available and hasattr(model, 'enable_xformers_memory_efficient_attention'):
                model.enable_xformers_memory_efficient_attention()
                logger.info("Enabled xformers memory-efficient attention")
                return True

            # Try Flash Attention via PyTorch SDPA
            if self.flash_attention_available and hasattr(model, 'enable_attention_slicing'):
                # Some diffusers models support attention slicing
                model.enable_attention_slicing(slice_size="auto")
                logger.info("Enabled attention slicing")
                return True

        except Exception as e:
            logger.warning(f"Could not enable attention optimization: {e}")

        return False

    def enable_vae_optimization(self, model: Any) -> bool:
        """
        Enable VAE optimizations

        Args:
            model: Model with VAE component

        Returns:
            True if optimization was applied
        """
        try:
            if hasattr(model, 'vae') and hasattr(model.vae, 'enable_slicing'):
                model.vae.enable_slicing()
                logger.info("Enabled VAE slicing")
                return True

            if hasattr(model, 'vae') and hasattr(model.vae, 'enable_tiling'):
                model.vae.enable_tiling()
                logger.info("Enabled VAE tiling")
                return True

        except Exception as e:
            logger.warning(f"Could not enable VAE optimization: {e}")

        return False

    def optimize_model(self, model: Any) -> Any:
        """
        Apply all available optimizations to a model

        Args:
            model: Model to optimize

        Returns:
            Optimized model
        """
        logger.info("Applying optimizations to model")

        # Enable attention optimizations
        self.enable_attention_optimization(model)

        # Enable VAE optimizations
        self.enable_vae_optimization(model)

        # Enable gradient checkpointing if available (for training/fine-tuning)
        if hasattr(model, 'enable_gradient_checkpointing'):
            try:
                model.enable_gradient_checkpointing()
                logger.info("Enabled gradient checkpointing")
            except:
                pass

        # Set to eval mode for inference
        if hasattr(model, 'eval'):
            model.eval()

        # Disable gradient computation for inference
        if hasattr(model, 'requires_grad_'):
            for param in model.parameters():
                param.requires_grad = False

        return model

    def get_optimal_dtype(self) -> torch.dtype:
        """
        Get optimal data type for current device

        Returns:
            Optimal torch dtype
        """
        if self.device == "cuda":
            # bfloat16 is preferred for CUDA if available
            if torch.cuda.is_bf16_supported():
                return torch.bfloat16
            return torch.float16
        return torch.float32

    def enable_tf32(self):
        """Enable TF32 for better performance on Ampere GPUs"""
        if self.device == "cuda":
            torch.backends.cuda.matmul.allow_tf32 = True
            torch.backends.cudnn.allow_tf32 = True
            logger.info("TF32 enabled for CUDA operations")

    def get_optimization_info(self) -> dict:
        """Get information about available optimizations"""
        return {
            "device": self.device,
            "amp_enabled": self.amp_enabled,
            "xformers_available": self.xformers_available,
            "flash_attention_available": self.flash_attention_available,
            "optimal_dtype": str(self.get_optimal_dtype()),
            "bf16_supported": torch.cuda.is_bf16_supported() if self.device == "cuda" else False,
        }


# Singleton instance
optimization_manager = OptimizationManager()

# Enable TF32 by default
optimization_manager.enable_tf32()
