"""
VRAM Manager for efficient GPU memory management
Similar to ComfyUI's memory management
"""

import torch
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum

try:
    import pynvml
    PYNVML_AVAILABLE = True
except ImportError:
    PYNVML_AVAILABLE = False

logger = logging.getLogger(__name__)


class VRAMState(Enum):
    """VRAM usage states"""
    LOW = "low"           # < 50% used
    MODERATE = "moderate"  # 50-75% used
    HIGH = "high"         # 75-90% used
    CRITICAL = "critical"  # > 90% used


@dataclass
class VRAMStats:
    """VRAM statistics"""
    total: int
    used: int
    free: int
    utilization: float
    state: VRAMState


class VRAMManager:
    """
    Manages VRAM/GPU memory efficiently

    Features:
    - Real-time memory monitoring
    - Automatic cleanup when memory is low
    - Memory profiling for models
    - Smart offloading decisions
    """

    def __init__(self):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.pynvml_initialized = False
        self._initialize_pynvml()

        # Memory thresholds (in bytes)
        self.critical_threshold = 0.9  # 90%
        self.high_threshold = 0.75     # 75%
        self.moderate_threshold = 0.5  # 50%

        # Track loaded models and their memory usage
        self.model_memory_usage: Dict[str, int] = {}

    def _initialize_pynvml(self):
        """Initialize NVIDIA Management Library"""
        if not PYNVML_AVAILABLE or self.device == "cpu":
            return

        try:
            pynvml.nvmlInit()
            self.pynvml_initialized = True
            logger.info("NVIDIA ML initialized successfully")
        except Exception as e:
            logger.warning(f"Failed to initialize NVIDIA ML: {e}")
            self.pynvml_initialized = False

    def get_vram_stats(self) -> VRAMStats:
        """
        Get current VRAM statistics

        Returns:
            VRAMStats with current memory state
        """
        if self.device == "cpu":
            return VRAMStats(
                total=0, used=0, free=0, utilization=0.0, state=VRAMState.LOW
            )

        if self.pynvml_initialized:
            try:
                handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                info = pynvml.nvmlDeviceGetMemoryInfo(handle)

                total = info.total
                used = info.used
                free = info.free
                utilization = used / total if total > 0 else 0.0

            except Exception as e:
                logger.error(f"Error getting VRAM stats: {e}")
                return self._get_torch_vram_stats()
        else:
            return self._get_torch_vram_stats()

        # Determine state
        if utilization >= self.critical_threshold:
            state = VRAMState.CRITICAL
        elif utilization >= self.high_threshold:
            state = VRAMState.HIGH
        elif utilization >= self.moderate_threshold:
            state = VRAMState.MODERATE
        else:
            state = VRAMState.LOW

        return VRAMStats(
            total=total,
            used=used,
            free=free,
            utilization=utilization,
            state=state
        )

    def _get_torch_vram_stats(self) -> VRAMStats:
        """Fallback to PyTorch memory stats"""
        if not torch.cuda.is_available():
            return VRAMStats(
                total=0, used=0, free=0, utilization=0.0, state=VRAMState.LOW
            )

        try:
            total = torch.cuda.get_device_properties(0).total_memory
            reserved = torch.cuda.memory_reserved(0)
            allocated = torch.cuda.memory_allocated(0)
            free = total - reserved

            utilization = reserved / total if total > 0 else 0.0

            if utilization >= self.critical_threshold:
                state = VRAMState.CRITICAL
            elif utilization >= self.high_threshold:
                state = VRAMState.HIGH
            elif utilization >= self.moderate_threshold:
                state = VRAMState.MODERATE
            else:
                state = VRAMState.LOW

            return VRAMStats(
                total=total,
                used=reserved,
                free=free,
                utilization=utilization,
                state=state
            )
        except Exception as e:
            logger.error(f"Error getting torch VRAM stats: {e}")
            return VRAMStats(
                total=0, used=0, free=0, utilization=0.0, state=VRAMState.LOW
            )

    def clear_cache(self):
        """Clear CUDA cache to free up memory"""
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
            logger.info("CUDA cache cleared")

    def should_offload_to_cpu(self) -> bool:
        """
        Determine if models should be offloaded to CPU

        Returns:
            True if VRAM usage is high and offloading is recommended
        """
        stats = self.get_vram_stats()
        return stats.state in [VRAMState.HIGH, VRAMState.CRITICAL]

    def register_model(self, model_name: str, memory_usage: int):
        """Register a model's memory usage"""
        self.model_memory_usage[model_name] = memory_usage
        logger.info(f"Registered model {model_name}: {memory_usage / 1024**2:.2f} MB")

    def unregister_model(self, model_name: str):
        """Unregister a model"""
        if model_name in self.model_memory_usage:
            del self.model_memory_usage[model_name]
            logger.info(f"Unregistered model {model_name}")

    def get_memory_summary(self) -> Dict[str, Any]:
        """Get comprehensive memory summary"""
        stats = self.get_vram_stats()

        return {
            "device": self.device,
            "total_vram_mb": stats.total / 1024**2 if stats.total > 0 else 0,
            "used_vram_mb": stats.used / 1024**2 if stats.used > 0 else 0,
            "free_vram_mb": stats.free / 1024**2 if stats.free > 0 else 0,
            "utilization_percent": stats.utilization * 100,
            "state": stats.state.value,
            "loaded_models": list(self.model_memory_usage.keys()),
            "total_model_memory_mb": sum(self.model_memory_usage.values()) / 1024**2,
        }

    def cleanup_if_needed(self):
        """Perform cleanup if memory usage is high"""
        stats = self.get_vram_stats()

        if stats.state in [VRAMState.HIGH, VRAMState.CRITICAL]:
            logger.warning(f"VRAM usage {stats.state.value}, performing cleanup")
            self.clear_cache()

            # Log post-cleanup stats
            new_stats = self.get_vram_stats()
            logger.info(
                f"Cleanup complete. VRAM: {new_stats.utilization * 100:.1f}% "
                f"({new_stats.used / 1024**2:.0f}MB / {new_stats.total / 1024**2:.0f}MB)"
            )

    def __del__(self):
        """Cleanup on destruction"""
        if self.pynvml_initialized:
            try:
                pynvml.nvmlShutdown()
            except:
                pass


# Singleton instance
vram_manager = VRAMManager()
