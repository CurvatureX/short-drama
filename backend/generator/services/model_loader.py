"""
Model Loader with Fallback Strategy

This module provides intelligent model loading:
1. First tries to load from local ComfyUI models directory
2. Falls back to downloading from HuggingFace if not found
3. Caches downloaded models for future use
"""

import logging
from pathlib import Path
from typing import Optional, Union, Type, Any
import torch
from huggingface_hub import hf_hub_download, snapshot_download

from config import settings, model_paths

logger = logging.getLogger(__name__)


class ModelLoader:
    """
    Intelligent model loader with local-first, HuggingFace fallback strategy
    """

    def __init__(self):
        self.local_base = Path(settings.comfyui_models_base)
        logger.info(f"ModelLoader initialized with base: {self.local_base}")

    def load_safetensors_model(
        self,
        local_path: Optional[Path] = None,
        hf_repo: Optional[str] = None,
        hf_filename: Optional[str] = None,
        model_class: Optional[Type] = None,
        subfolder: Optional[str] = None,
        torch_dtype: torch.dtype = torch.float16,
        **kwargs,
    ) -> Any:
        """
        Load a safetensors model with fallback strategy

        Args:
            local_path: Path to local model file (e.g., model_paths.qwen_image_edit_unet)
            hf_repo: HuggingFace repository ID (e.g., "Qwen/Qwen-Image-Edit-2509")
            hf_filename: Filename in HF repo (e.g., "qwen_image_edit_2509_fp8_e4m3fn.safetensors")
            model_class: Model class to use for loading (e.g., DiffusionPipeline)
            subfolder: Subfolder in HF repo
            torch_dtype: Data type for model weights
            **kwargs: Additional arguments for model loading

        Returns:
            Loaded model

        Raises:
            FileNotFoundError: If model not found locally and HF repo not provided
            RuntimeError: If model loading fails
        """
        # Strategy 1: Try local path first
        if local_path and local_path.exists():
            logger.info(f"Loading model from local path: {local_path}")
            try:
                return self._load_from_local(
                    local_path=local_path,
                    model_class=model_class,
                    torch_dtype=torch_dtype,
                    **kwargs,
                )
            except Exception as e:
                logger.warning(f"Failed to load from local path: {e}")
                if hf_repo is None:
                    raise

        # Strategy 2: Download from HuggingFace
        if hf_repo:
            logger.info(f"Downloading model from HuggingFace: {hf_repo}")
            try:
                return self._load_from_huggingface(
                    repo_id=hf_repo,
                    filename=hf_filename,
                    model_class=model_class,
                    subfolder=subfolder,
                    torch_dtype=torch_dtype,
                    **kwargs,
                )
            except Exception as e:
                logger.error(f"Failed to download from HuggingFace: {e}")
                raise

        # No valid source
        raise FileNotFoundError(
            f"Model not found at local path: {local_path}\n"
            f"HuggingFace repo not provided for fallback download."
        )

    def _load_from_local(
        self,
        local_path: Path,
        model_class: Optional[Type] = None,
        torch_dtype: torch.dtype = torch.float16,
        **kwargs,
    ) -> Any:
        """Load model from local file"""
        if not local_path.exists():
            raise FileNotFoundError(f"Local model not found: {local_path}")

        # Get file size for logging
        size_mb = local_path.stat().st_size / (1024 * 1024)
        logger.info(f"Loading {size_mb:.1f} MB from {local_path.name}")

        # Use model_class if provided, otherwise return path
        if model_class:
            # For diffusers models
            if hasattr(model_class, "from_single_file"):
                return model_class.from_single_file(
                    str(local_path),
                    torch_dtype=torch_dtype,
                    **kwargs,
                )
            elif hasattr(model_class, "from_pretrained"):
                # Try loading as pretrained model
                return model_class.from_pretrained(
                    str(local_path.parent),
                    torch_dtype=torch_dtype,
                    **kwargs,
                )
            else:
                raise ValueError(f"Model class {model_class} doesn't support loading")
        else:
            # Return path for manual loading
            return str(local_path)

    def _load_from_huggingface(
        self,
        repo_id: str,
        filename: Optional[str] = None,
        model_class: Optional[Type] = None,
        subfolder: Optional[str] = None,
        torch_dtype: torch.dtype = torch.float16,
        **kwargs,
    ) -> Any:
        """Download and load model from HuggingFace"""
        logger.info(f"Downloading from HuggingFace: {repo_id}")

        # Get HF token if available
        hf_token = settings.hf_token

        if filename:
            # Download single file
            logger.info(f"Downloading file: {filename}")
            local_file = hf_hub_download(
                repo_id=repo_id,
                filename=filename,
                subfolder=subfolder,
                token=hf_token,
            )
            logger.info(f"Downloaded to cache: {local_file}")

            # Load using model_class if provided
            if model_class:
                if hasattr(model_class, "from_single_file"):
                    return model_class.from_single_file(
                        local_file,
                        torch_dtype=torch_dtype,
                        **kwargs,
                    )
                else:
                    raise ValueError(
                        f"Model class {model_class} doesn't support from_single_file"
                    )
            else:
                return local_file
        else:
            # Download entire repository
            logger.info(f"Downloading repository: {repo_id}")
            local_dir = snapshot_download(
                repo_id=repo_id,
                token=hf_token,
            )
            logger.info(f"Downloaded to cache: {local_dir}")

            # Load using model_class if provided
            if model_class:
                if hasattr(model_class, "from_pretrained"):
                    return model_class.from_pretrained(
                        local_dir,
                        torch_dtype=torch_dtype,
                        **kwargs,
                    )
                else:
                    raise ValueError(
                        f"Model class {model_class} doesn't support from_pretrained"
                    )
            else:
                return local_dir

    def load_lora_weights(
        self,
        pipeline: Any,
        local_path: Optional[Path] = None,
        hf_repo: Optional[str] = None,
        hf_filename: Optional[str] = None,
        adapter_name: str = "default",
        adapter_weight: float = 1.0,
    ) -> Any:
        """
        Load LoRA weights into a pipeline with fallback strategy

        Args:
            pipeline: Diffusion pipeline to load LoRA into
            local_path: Local path to LoRA file
            hf_repo: HuggingFace repository ID
            hf_filename: Filename in HF repo
            adapter_name: Name for the LoRA adapter
            adapter_weight: Weight for the adapter

        Returns:
            Pipeline with LoRA loaded
        """
        # Strategy 1: Try local path
        if local_path and local_path.exists():
            logger.info(f"Loading LoRA from local: {local_path}")
            try:
                pipeline.load_lora_weights(
                    str(local_path.parent),
                    weight_name=local_path.name,
                    adapter_name=adapter_name,
                )
                logger.info(f"LoRA '{adapter_name}' loaded from local")
                return pipeline
            except Exception as e:
                logger.warning(f"Failed to load LoRA from local: {e}")
                if hf_repo is None:
                    raise

        # Strategy 2: Download from HuggingFace
        if hf_repo:
            logger.info(f"Downloading LoRA from HuggingFace: {hf_repo}")
            try:
                if hf_filename:
                    pipeline.load_lora_weights(
                        hf_repo,
                        weight_name=hf_filename,
                        adapter_name=adapter_name,
                    )
                else:
                    pipeline.load_lora_weights(
                        hf_repo,
                        adapter_name=adapter_name,
                    )
                logger.info(f"LoRA '{adapter_name}' loaded from HuggingFace")
                return pipeline
            except Exception as e:
                logger.error(f"Failed to download LoRA from HuggingFace: {e}")
                raise

        raise FileNotFoundError(
            f"LoRA not found at local path: {local_path}\n"
            f"HuggingFace repo not provided for fallback."
        )

    def get_model_source(
        self,
        local_path: Optional[Path] = None,
        hf_repo: Optional[str] = None,
    ) -> tuple[str, str]:
        """
        Determine which source will be used for loading

        Returns:
            Tuple of (source, path) where source is "local" or "huggingface"
        """
        if local_path and local_path.exists():
            return ("local", str(local_path))
        elif hf_repo:
            return ("huggingface", hf_repo)
        else:
            return ("unavailable", "No valid source")


# Singleton instance
model_loader = ModelLoader()
