"""
Configuration for Redis and AWS S3
"""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # Redis configuration
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: Optional[str] = None

    # AWS S3 configuration
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_region: str = "us-east-1"
    s3_bucket_name: str = "image-generation-outputs"
    s3_endpoint_url: Optional[str] = None  # For S3-compatible services

    # Task configuration
    task_ttl: int = 3600  # Task status TTL in seconds (1 hour)

    # Hugging Face configuration
    hf_token: Optional[str] = None
    hf_provider: str = "nebius"  # Inference provider

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
