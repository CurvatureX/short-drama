"""
Configuration for Redis, AWS S3, and Model Paths
"""

from pydantic_settings import BaseSettings
from typing import Optional
from pathlib import Path


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # Redis configuration
    redis_host: str = "short-drama-redis-mqc7z9.serverless.use1.cache.amazonaws.com"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: Optional[str] = None

    # AWS S3 configuration
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_region: str = "us-east-1"
    s3_bucket_name: str = "short-drama-assets"
    s3_endpoint_url: Optional[str] = None  # For S3-compatible services

    # Task configuration
    task_ttl: int = 3600  # Task status TTL in seconds (1 hour)

    # Hugging Face configuration
    hf_token: Optional[str] = None
    hf_provider: str = "nebius"  # Inference provider

    # Local Model Paths (ComfyUI models directory)
    comfyui_models_base: str = "/home/ubuntu/ComfyUI/models"

    # Model path properties
    @property
    def models_checkpoints(self) -> Path:
        return Path(self.comfyui_models_base) / "checkpoints"

    @property
    def models_vae(self) -> Path:
        return Path(self.comfyui_models_base) / "vae"

    @property
    def models_loras(self) -> Path:
        return Path(self.comfyui_models_base) / "loras"

    @property
    def models_unet(self) -> Path:
        return Path(self.comfyui_models_base) / "unet"

    @property
    def models_text_encoders(self) -> Path:
        return Path(self.comfyui_models_base) / "text_encoders"

    @property
    def models_diffusion(self) -> Path:
        return Path(self.comfyui_models_base) / "diffusion_models"

    @property
    def models_clip(self) -> Path:
        return Path(self.comfyui_models_base) / "clip"

    @property
    def models_controlnet(self) -> Path:
        return Path(self.comfyui_models_base) / "controlnet"

    @property
    def models_upscale(self) -> Path:
        return Path(self.comfyui_models_base) / "upscale_models"

    @property
    def models_inpaint(self) -> Path:
        return Path(self.comfyui_models_base) / "inpaint"

    @property
    def models_lama(self) -> Path:
        return Path(self.comfyui_models_base) / "lama"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Specific model configurations
class ModelPaths:
    """Specific model file paths from ComfyUI directory"""

    def __init__(self, settings: Settings):
        self.settings = settings

    # Qwen Multi-Angle Models
    @property
    def qwen_image_edit_unet(self) -> Path:
        """Qwen Image Edit 2509 UNET (for image-to-image editing)"""
        return self.settings.models_diffusion / "qwen-image-edit" / "qwen_image_edit_2509_fp8_e4m3fn.safetensors"

    @property
    def qwen_image_vae(self) -> Path:
        """Qwen Image VAE"""
        return self.settings.models_vae / "qwen_image_vae.safetensors"

    @property
    def qwen_text_encoder(self) -> Path:
        """Qwen Text Encoder (umt5_xxl)"""
        return self.settings.models_text_encoders / "qwen" / "qwen_2.5_vl_7b_fp8_scaled.safetensors"

    @property
    def qwen_multi_angle_lora(self) -> Path:
        """Multi-Angle LoRA (镜头转换)"""
        return self.settings.models_loras / "镜头转换.safetensors"

    @property
    def qwen_edit_lightning_lora(self) -> Path:
        """Qwen Edit Lightning LoRA (4-step fast editing)"""
        return self.settings.models_loras / "qwen-image-edit-lightning" / "Qwen-Image-Edit-Lightning-4steps-V1.0.safetensors"

    # WanVideo Models (Watermark Removal)
    @property
    def wan_minimax_remover_unet(self) -> Path:
        """WanVideo MiniMaxRemover UNET (watermark removal)"""
        return self.settings.models_unet / "Wan2_1-MiniMaxRemover_1_3B_fp16.safetensors"

    @property
    def wan_vae(self) -> Path:
        """WanVideo VAE"""
        return self.settings.models_vae / "Wan2_1_VAE_bf16.safetensors"

    @property
    def wan_vae_alt(self) -> Path:
        """WanVideo VAE (alternative)"""
        return self.settings.models_vae / "wan_2.1_vae.safetensors"

    @property
    def wan_text_encoder(self) -> Path:
        """WanVideo Text Encoder (umt5_xxl)"""
        return self.settings.models_text_encoders / "umt5_xxl_fp16.safetensors"

    @property
    def wan_text_encoder_fp8(self) -> Path:
        """WanVideo Text Encoder FP8 (optimized)"""
        return self.settings.models_text_encoders / "umt5_xxl_fp8_e4m3fn_scaled.safetensors"

    # WanVideo I2V Models (Image-to-Video)
    @property
    def wan_i2v_high_noise(self) -> Path:
        """WanVideo I2V High Noise Model"""
        return self.settings.models_diffusion / "wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors"

    @property
    def wan_i2v_low_noise(self) -> Path:
        """WanVideo I2V Low Noise Model"""
        return self.settings.models_diffusion / "wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors"

    @property
    def wan_i2v_lightning_high(self) -> Path:
        """WanVideo I2V Lightning LoRA (High Noise)"""
        return self.settings.models_loras / "wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors"

    @property
    def wan_i2v_lightning_low(self) -> Path:
        """WanVideo I2V Lightning LoRA (Low Noise)"""
        return self.settings.models_loras / "wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors"

    # FLUX Models
    @property
    def flux_checkpoint(self) -> Path:
        """FLUX Checkpoint (JuggernautXL)"""
        return self.settings.models_checkpoints / "juggernautXL_v9Rdphoto2Lightning.safetensors"

    # Inpainting Models
    @property
    def fooocus_inpaint_head(self) -> Path:
        """Fooocus Inpaint Head"""
        return self.settings.models_inpaint / "fooocus_inpaint_head.pth"

    @property
    def fooocus_inpaint_patch(self) -> Path:
        """Fooocus Inpaint Patch"""
        return self.settings.models_inpaint / "inpaint.fooocus.patch"

    @property
    def lama_model(self) -> Path:
        """LAMA Inpainting Model"""
        return self.settings.models_lama / "big-lama.pt"

    # SAM Models (Segmentation)
    @property
    def sam_vit_b(self) -> Path:
        """SAM ViT-B Model"""
        return Path(self.settings.comfyui_models_base) / "sams" / "sam_vit_b_01ec64.pth"

    @property
    def sam_vit_h(self) -> Path:
        """SAM ViT-H Model"""
        return Path(self.settings.comfyui_models_base) / "sams" / "sam_vit_h_4b8939.pth"

    # GroundingDINO Models
    @property
    def grounding_dino_config(self) -> Path:
        """GroundingDINO Config"""
        return Path(self.settings.comfyui_models_base) / "grounding-dino" / "GroundingDINO_SwinT_OGC.cfg.py"

    @property
    def grounding_dino_weights(self) -> Path:
        """GroundingDINO Weights"""
        return Path(self.settings.comfyui_models_base) / "grounding-dino" / "groundingdino_swint_ogc.pth"

    def get_model_info(self) -> dict:
        """Get information about all available models"""
        models = {}

        # Check which models exist
        model_checks = {
            "qwen_image_edit": self.qwen_image_edit_unet,
            "qwen_vae": self.qwen_image_vae,
            "qwen_multi_angle_lora": self.qwen_multi_angle_lora,
            "qwen_edit_lightning_lora": self.qwen_edit_lightning_lora,
            "wan_minimax_remover": self.wan_minimax_remover_unet,
            "wan_vae": self.wan_vae,
            "wan_i2v_high_noise": self.wan_i2v_high_noise,
            "wan_i2v_low_noise": self.wan_i2v_low_noise,
            "flux_checkpoint": self.flux_checkpoint,
            "lama_inpaint": self.lama_model,
            "sam_vit_b": self.sam_vit_b,
            "sam_vit_h": self.sam_vit_h,
        }

        for name, path in model_checks.items():
            models[name] = {
                "path": str(path),
                "exists": path.exists() if isinstance(path, Path) else False,
                "size_mb": round(path.stat().st_size / (1024 * 1024), 2) if path.exists() else 0
            }

        return models


# Global instances
settings = Settings()
model_paths = ModelPaths(settings)
