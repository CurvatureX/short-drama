"""
SeeDream API Client for Image-to-Image Generation
Uses Doubao's SeeDream 4.0 model via Volcano Engine ARK API
"""

import os
import requests
import boto3
from typing import List, Optional, Literal, Dict, Any, Union
from dataclasses import dataclass
from enum import Enum
from io import BytesIO
import uuid
from datetime import datetime


class ImageSize(str, Enum):
    """Supported image sizes for SeeDream API"""

    SQUARE_2K = "2048x2048"  # 1:1 aspect ratio
    LANDSCAPE_4_3 = "2304x1728"  # 4:3 aspect ratio
    PORTRAIT_3_4 = "1728x2304"  # 3:4 aspect ratio
    LANDSCAPE_16_9 = "2560x1440"  # 16:9 aspect ratio
    PORTRAIT_9_16 = "1440x2560"  # 9:16 aspect ratio
    LANDSCAPE_3_2 = "2496x1664"  # 3:2 aspect ratio
    PORTRAIT_2_3 = "1664x2496"  # 2:3 aspect ratio
    ULTRAWIDE_21_9 = "3024x1296"  # 21:9 aspect ratio


class ResponseFormat(str, Enum):
    """Response format for generated images"""

    URL = "url"
    B64_JSON = "b64_json"


class SequentialGeneration(str, Enum):
    """Sequential image generation mode"""

    ENABLED = "enabled"
    DISABLED = "disabled"


@dataclass
class SeeDreamResponse:
    """Response from SeeDream API"""

    image_urls: List[str]
    created: int
    raw_response: Dict[str, Any]


class SeeDreamClient:
    """
    Client for SeeDream 4.0 API

    Example usage:
        client = SeeDreamClient(api_key="your_api_key")

        # Single image generation
        response = client.generate(
            prompt="Generate a beautiful landscape",
            image=["https://example.com/image.png"]
        )

        # Multi-image generation
        response = client.generate(
            prompt="Transfer clothing from image 1 to image 2",
            image=[
                "https://example.com/image1.png",
                "https://example.com/image2.png"
            ]
        )
    """

    BASE_URL = "https://ark.cn-beijing.volces.com/api/v3/images/generations"
    MODEL = "doubao-seedream-4-0-250828"

    def __init__(self, api_key: Optional[str] = None, auto_upload_s3: bool = True):
        """
        Initialize SeeDream client

        Args:
            api_key: ARK API key. If not provided, will read from ARK_API_KEY env var
            auto_upload_s3: Automatically upload generated images to S3 and return CloudFront URLs
        """
        self.api_key = api_key or os.getenv("ARK_API_KEY")
        if not self.api_key:
            raise ValueError("ARK_API_KEY must be provided or set in environment")

        self.auto_upload_s3 = auto_upload_s3

        # Initialize S3 client if auto_upload is enabled
        if self.auto_upload_s3:
            self.s3_bucket = os.getenv("S3_BUCKET_NAME")
            self.cloudfront_domain = os.getenv("CLOUDFRONT_DOMAIN")

            if not self.s3_bucket:
                raise ValueError("S3_BUCKET_NAME must be set in environment for auto S3 upload")
            if not self.cloudfront_domain:
                raise ValueError("CLOUDFRONT_DOMAIN must be set in environment for auto S3 upload")

            self.s3_client = boto3.client(
                's3',
                aws_access_key_id=os.getenv("AWS_ACCESS_KEY"),
                aws_secret_access_key=os.getenv("AWS_ACCESS_SECRET"),
                region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1")
            )

        self.session = requests.Session()
        self.session.headers.update(
            {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            }
        )

    def _get_image_dimensions(self, image_url: str) -> tuple[int, int]:
        """
        Fetch image and return its dimensions (width, height)

        Args:
            image_url: URL of the image to analyze

        Returns:
            Tuple of (width, height)

        Raises:
            Exception: If image cannot be fetched or is invalid
        """
        try:
            from PIL import Image
        except ImportError:
            raise ImportError(
                "Pillow is required for automatic image size detection. "
                "Install it with: pip install Pillow"
            )

        # Fetch image
        response = requests.get(image_url, timeout=10)
        response.raise_for_status()

        # Open and get dimensions
        img = Image.open(BytesIO(response.content))
        return img.size  # Returns (width, height)

    def _detect_best_size(self, image_url: str) -> ImageSize:
        """
        Detect the best output size based on input image aspect ratio

        Args:
            image_url: URL of the image to analyze

        Returns:
            Best matching ImageSize enum value
        """
        width, height = self._get_image_dimensions(image_url)
        aspect_ratio = width / height

        # Define aspect ratios for each size option
        size_ratios = {
            ImageSize.SQUARE_2K: 1.0,  # 1:1
            ImageSize.LANDSCAPE_4_3: 4 / 3,  # 1.333
            ImageSize.PORTRAIT_3_4: 3 / 4,  # 0.75
            ImageSize.LANDSCAPE_16_9: 16 / 9,  # 1.778
            ImageSize.PORTRAIT_9_16: 9 / 16,  # 0.5625
            ImageSize.LANDSCAPE_3_2: 3 / 2,  # 1.5
            ImageSize.PORTRAIT_2_3: 2 / 3,  # 0.667
            ImageSize.ULTRAWIDE_21_9: 21 / 9,  # 2.333
        }

        # Find closest aspect ratio
        best_size = min(
            size_ratios.items(), key=lambda item: abs(item[1] - aspect_ratio)
        )

        return best_size[0]

    def _upload_to_s3(self, image_url: str) -> str:
        """
        Download image from URL and upload to S3, return CloudFront URL

        Args:
            image_url: URL of the image to download and upload

        Returns:
            CloudFront URL of the uploaded image

        Raises:
            Exception: If download or upload fails
        """
        # Download image
        response = requests.get(image_url, timeout=30)
        response.raise_for_status()

        # Generate unique S3 key
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]

        # Detect file extension from content-type or URL
        content_type = response.headers.get('content-type', 'image/jpeg')
        if 'jpeg' in content_type or 'jpg' in content_type:
            ext = 'jpg'
        elif 'png' in content_type:
            ext = 'png'
        elif 'webp' in content_type:
            ext = 'webp'
        else:
            ext = 'jpg'  # default

        s3_key = f"seedream/{timestamp}_{unique_id}.{ext}"

        # Upload to S3
        self.s3_client.put_object(
            Bucket=self.s3_bucket,
            Key=s3_key,
            Body=response.content,
            ContentType=content_type,
            CacheControl='public, max-age=31536000'  # Cache for 1 year
        )

        # Return CloudFront URL
        cloudfront_url = f"{self.cloudfront_domain.rstrip('/')}/{s3_key}"
        return cloudfront_url

    def generate(
        self,
        prompt: str,
        image: List[str],
        size: Optional[Union[ImageSize, str]] = None,
        sequential_image_generation: SequentialGeneration = SequentialGeneration.DISABLED,
        response_format: ResponseFormat = ResponseFormat.URL,
        timeout: int = 60,
    ) -> SeeDreamResponse:
        """
        Generate images using SeeDream API

        Args:
            prompt: Text prompt describing the desired transformation
            image: List of image URLs (1-2 images supported)
            size: Output image size. If None or "auto", automatically detects based on
                  first image's aspect ratio. Can be ImageSize enum or pixel format string.
            sequential_image_generation: Whether to enable sequential generation
            response_format: Format of response (url or b64_json)
            timeout: Request timeout in seconds

        Returns:
            SeeDreamResponse object containing generated image URLs.
            If auto_upload_s3=True (default), URLs will be CloudFront URLs.
            Otherwise, temporary pre-signed URLs from Volcano Engine.

        Raises:
            ValueError: If invalid parameters provided
            requests.HTTPError: If API request fails

        Note:
            When auto_upload_s3 is enabled, images are automatically downloaded
            from Volcano Engine and uploaded to S3, then CloudFront URLs are returned.
            This ensures URLs don't expire.
        """
        if not image or len(image) > 2:
            raise ValueError("Must provide 1-2 images")

        # Auto-detect size if not specified or if "auto"
        if size is None or size == "auto":
            size = self._detect_best_size(image[0])

        # Convert string to ImageSize if needed
        if isinstance(size, str):
            # Try to find matching ImageSize
            try:
                size = ImageSize(size)
            except ValueError:
                raise ValueError(f"Invalid size: {size}")

        payload = {
            "model": self.MODEL,
            "prompt": prompt,
            "image": image,
            "sequential_image_generation": sequential_image_generation.value,
            "response_format": response_format.value,
            "size": size.value,
            "stream": False,
            "watermark": False,
        }

        response = self.session.post(self.BASE_URL, json=payload, timeout=timeout)
        response.raise_for_status()

        data = response.json()

        # Extract image URLs from response
        image_urls = []
        if "data" in data:
            for item in data["data"]:
                if "url" in item:
                    temp_url = item["url"]

                    # Upload to S3 and get CloudFront URL if enabled
                    if self.auto_upload_s3:
                        cloudfront_url = self._upload_to_s3(temp_url)
                        image_urls.append(cloudfront_url)
                    else:
                        image_urls.append(temp_url)

                elif "b64_json" in item:
                    image_urls.append(item["b64_json"])

        return SeeDreamResponse(
            image_urls=image_urls, created=data.get("created", 0), raw_response=data
        )

    def generate_with_retry(
        self, prompt: str, image: List[str], max_retries: int = 3, **kwargs
    ) -> SeeDreamResponse:
        """
        Generate images with automatic retry on failure

        Args:
            prompt: Text prompt
            image: List of image URLs
            max_retries: Maximum number of retry attempts
            **kwargs: Additional arguments passed to generate()

        Returns:
            SeeDreamResponse object

        Raises:
            requests.HTTPError: If all retries fail
        """
        last_exception = None

        for attempt in range(max_retries):
            try:
                return self.generate(prompt, image, **kwargs)
            except requests.exceptions.RequestException as e:
                last_exception = e
                if attempt < max_retries - 1:
                    # Exponential backoff
                    import time

                    time.sleep(2**attempt)
                    continue

        raise last_exception

    def batch_generate(
        self,
        prompt: str,
        image: List[str],
        batch_size: int = 2,
        size: Optional[Union[ImageSize, str]] = None,
        response_format: ResponseFormat = ResponseFormat.URL,
        timeout: int = 120,
    ) -> List[SeeDreamResponse]:
        """
        Generate multiple images concurrently using batch processing

        This method handles errors gracefully - if some generations fail, it will
        return the successful ones and emit a warning for failures.

        Args:
            prompt: Text prompt describing the desired transformation
            image: List of image URLs (1-2 images supported)
            batch_size: Number of images to generate (2-4)
            size: Output image size. If None or "auto", automatically detects based on
                  first image's aspect ratio. Can be ImageSize enum or pixel format string.
            response_format: Format of response (url or b64_json)
            timeout: Request timeout in seconds per request

        Returns:
            List of SeeDreamResponse objects for successful generations.
            May return fewer than batch_size if some generations fail.

        Raises:
            ValueError: If batch_size is not between 2-4

        Warnings:
            RuntimeWarning: Emitted if any generations fail (but doesn't stop execution)

        Example:
            responses = client.batch_generate(
                prompt="Transform this image",
                image=["https://example.com/image.png"],
                batch_size=4,
                size=ImageSize.SQUARE_2K
            )
            print(f"Successfully generated {len(responses)} out of 4 images")
            for i, response in enumerate(responses, 1):
                print(f"Batch {i}: {response.image_urls[0]}")
        """
        if batch_size < 2 or batch_size > 4:
            raise ValueError("batch_size must be between 2 and 4")

        import concurrent.futures
        import threading

        # Use ThreadPoolExecutor for concurrent API calls
        responses = []
        errors = []
        lock = threading.Lock()

        def _generate_single(index: int):
            """Helper function to generate a single image"""
            try:
                response = self.generate(
                    prompt=prompt,
                    image=image,
                    size=size,
                    response_format=response_format,
                    timeout=timeout,
                )
                with lock:
                    responses.append((index, response))
            except Exception as e:
                with lock:
                    errors.append((index, e))

        # Execute batch generation concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=batch_size) as executor:
            futures = [executor.submit(_generate_single, i) for i in range(batch_size)]
            # Wait for all to complete
            concurrent.futures.wait(futures)

        # Log errors but don't raise - return successful generations
        if errors:
            import warnings

            error_msgs = [f"Batch {idx}: {str(err)}" for idx, err in errors]
            warnings.warn(
                f"Batch generation had {len(errors)} failure(s) out of {batch_size}:\n"
                + "\n".join(error_msgs),
                RuntimeWarning,
            )

        # Sort responses by index to maintain order
        # Return only successful generations
        responses.sort(key=lambda x: x[0])
        return [resp for _, resp in responses]

    def batch_generate_with_retry(
        self,
        prompt: str,
        image: List[str],
        batch_size: int = 2,
        max_retries: int = 3,
        **kwargs,
    ) -> List[SeeDreamResponse]:
        """
        Generate multiple images concurrently with automatic retry on failure

        This method handles errors gracefully - if some generations fail after all
        retries, it will return the successful ones and emit a warning for failures.

        Args:
            prompt: Text prompt
            image: List of image URLs
            batch_size: Number of images to generate (2-4)
            max_retries: Maximum number of retry attempts per image
            **kwargs: Additional arguments passed to generate()

        Returns:
            List of SeeDreamResponse objects for successful generations.
            May return fewer than batch_size if some generations fail after retries.

        Raises:
            ValueError: If batch_size is not between 2-4

        Warnings:
            RuntimeWarning: Emitted if any generations fail after retries

        Example:
            responses = client.batch_generate_with_retry(
                prompt="Transform this image",
                image=["https://example.com/image.png"],
                batch_size=3,
                max_retries=3,
                size=ImageSize.LANDSCAPE_16_9
            )
            print(f"Successfully generated {len(responses)} images")
        """
        if batch_size < 2 or batch_size > 4:
            raise ValueError("batch_size must be between 2 and 4")

        import concurrent.futures
        import threading
        import time

        responses = []
        errors = []
        lock = threading.Lock()

        def _generate_with_retry(index: int):
            """Helper function to generate a single image with retry"""
            last_exception = None

            for attempt in range(max_retries):
                try:
                    response = self.generate(prompt=prompt, image=image, **kwargs)
                    with lock:
                        responses.append((index, response))
                    return
                except requests.exceptions.RequestException as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        # Exponential backoff
                        time.sleep(2**attempt)
                        continue

            with lock:
                errors.append((index, last_exception))

        # Execute batch generation with retry concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=batch_size) as executor:
            futures = [
                executor.submit(_generate_with_retry, i) for i in range(batch_size)
            ]
            # Wait for all to complete
            concurrent.futures.wait(futures)

        # Log errors but don't raise - return successful generations
        if errors:
            import warnings

            error_msgs = [f"Batch {idx}: {str(err)}" for idx, err in errors]
            warnings.warn(
                f"Batch generation had {len(errors)} failure(s) out of {batch_size} after {max_retries} retries:\n"
                + "\n".join(error_msgs),
                RuntimeWarning,
            )

        # Sort responses by index to maintain order
        # Return only successful generations
        responses.sort(key=lambda x: x[0])
        return [resp for _, resp in responses]


def main():
    """Example usage of SeeDream API"""
    import sys

    # Initialize client
    api_key = os.getenv("ARK_API_KEY")
    if not api_key:
        print("Error: ARK_API_KEY environment variable not set")
        sys.exit(1)

    client = SeeDreamClient(api_key=api_key)

    # Example 1: Single image generation with manual size
    print("=" * 60)
    print("Example 1: Image Generation with Manual Size")
    print("=" * 60)
    try:
        response = client.generate(
            prompt="Transfer the clothing from image 1 to image 2",
            image=[
                "https://ark-project.tos-cn-beijing.volces.com/doc_image/seedream4_imagesToimage_1.png",
                "https://ark-project.tos-cn-beijing.volces.com/doc_image/seedream4_imagesToimage_2.png",
            ],
            size=ImageSize.SQUARE_2K,
        )

        print(f"Success! Generated {len(response.image_urls)} image(s)")
        for i, url in enumerate(response.image_urls, 1):
            print(f"Image {i}: {url}")
        print()

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
