"""
S3 service for uploading and downloading generated images/videos
"""

import boto3
from botocore.exceptions import ClientError
import logging
from typing import Optional
from datetime import datetime
from io import BytesIO
from PIL import Image
import requests
from config import settings

logger = logging.getLogger(__name__)


class S3Service:
    """Service for managing file uploads to S3"""

    def __init__(self):
        self.s3_client = boto3.client(
            "s3",
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region_name=settings.aws_region,
            endpoint_url=settings.s3_endpoint_url,
        )
        self.bucket_name = settings.s3_bucket_name

    def upload_file(
        self,
        file_data: bytes,
        session_id: str,
        file_extension: str = "png",
        content_type: str = "image/png",
        s3_folder: str = "images",  # "images" or "videos"
    ) -> Optional[str]:
        """
        Upload file to S3

        Args:
            file_data: File content as bytes
            session_id: Unique session identifier
            file_extension: File extension (png, jpg, mp4, etc.)
            content_type: MIME type of the file
            s3_folder: S3 folder prefix (images or videos)

        Returns:
            S3 URL of the uploaded file or None if failed
        """
        try:
            # Generate S3 key with timestamp and session_id
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            s3_key = f"{s3_folder}/{timestamp}_{session_id}.{file_extension}"

            # Upload to S3
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=file_data,
                ContentType=content_type,
            )

            # Generate URL
            if settings.s3_endpoint_url:
                # For S3-compatible services
                url = f"{settings.s3_endpoint_url}/{self.bucket_name}/{s3_key}"
            else:
                # For AWS S3
                url = f"https://{self.bucket_name}.s3.{settings.aws_region}.amazonaws.com/{s3_key}"

            logger.info(f"File uploaded to S3: {url}")
            return url

        except ClientError as e:
            logger.error(f"S3 upload error: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error during S3 upload: {str(e)}")
            return None

    def generate_presigned_url(
        self, s3_key: str, expiration: int = 3600
    ) -> Optional[str]:
        """
        Generate a presigned URL for private S3 objects

        Args:
            s3_key: S3 object key
            expiration: URL expiration time in seconds

        Returns:
            Presigned URL or None if failed
        """
        try:
            url = self.s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket_name, "Key": s3_key},
                ExpiresIn=expiration,
            )
            return url
        except ClientError as e:
            logger.error(f"Error generating presigned URL: {str(e)}")
            return None

    def check_bucket_exists(self) -> bool:
        """Check if the S3 bucket exists"""
        try:
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            return True
        except ClientError:
            logger.error(f"Bucket {self.bucket_name} does not exist or is not accessible")
            return False

    def download_image_from_url(self, url: str) -> Optional[Image.Image]:
        """
        Download image from URL (S3 or HTTP/HTTPS)

        Args:
            url: URL to download image from

        Returns:
            PIL Image or None if failed
        """
        try:
            logger.info(f"Downloading image from: {url}")

            # Check if it's an S3 URL from our bucket
            if self.bucket_name in url and "s3" in url.lower():
                # Extract S3 key from URL
                s3_key = self._extract_s3_key_from_url(url)
                if s3_key:
                    return self.download_image_from_s3(s3_key)

            # Otherwise, download via HTTP/HTTPS
            response = requests.get(url, timeout=30)
            response.raise_for_status()

            # Load image from response content
            image = Image.open(BytesIO(response.content))

            # Convert to RGB if necessary
            if image.mode != "RGB":
                image = image.convert("RGB")

            logger.info(f"Successfully downloaded image: {image.size}")
            return image

        except Exception as e:
            logger.error(f"Failed to download image from {url}: {str(e)}")
            return None

    def download_image_from_s3(self, s3_key: str) -> Optional[Image.Image]:
        """
        Download image directly from S3

        Args:
            s3_key: S3 object key

        Returns:
            PIL Image or None if failed
        """
        try:
            logger.info(f"Downloading from S3: {s3_key}")

            # Download from S3
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=s3_key
            )

            # Load image from S3 response
            image_data = response['Body'].read()
            image = Image.open(BytesIO(image_data))

            # Convert to RGB if necessary
            if image.mode != "RGB":
                image = image.convert("RGB")

            logger.info(f"Successfully downloaded from S3: {image.size}")
            return image

        except ClientError as e:
            logger.error(f"S3 download error for {s3_key}: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Error loading image from S3: {str(e)}")
            return None

    def _extract_s3_key_from_url(self, url: str) -> Optional[str]:
        """
        Extract S3 key from S3 URL

        Args:
            url: S3 URL

        Returns:
            S3 key or None
        """
        try:
            # Handle different S3 URL formats
            # Format 1: https://bucket-name.s3.region.amazonaws.com/key
            # Format 2: https://s3.region.amazonaws.com/bucket-name/key
            # Format 3: https://endpoint-url/bucket-name/key

            if f"{self.bucket_name}.s3" in url:
                # Format 1
                parts = url.split(f"{self.bucket_name}.s3")
                if len(parts) > 1:
                    key = parts[1].split("/", 2)[-1]
                    return key
            elif f"s3." in url and f"/{self.bucket_name}/" in url:
                # Format 2
                parts = url.split(f"/{self.bucket_name}/")
                if len(parts) > 1:
                    return parts[1]
            elif settings.s3_endpoint_url and settings.s3_endpoint_url in url:
                # Format 3 (custom endpoint)
                parts = url.split(f"/{self.bucket_name}/")
                if len(parts) > 1:
                    return parts[1]

            logger.warning(f"Could not extract S3 key from URL: {url}")
            return None

        except Exception as e:
            logger.error(f"Error extracting S3 key: {str(e)}")
            return None


# Singleton instance
s3_service = S3Service()
