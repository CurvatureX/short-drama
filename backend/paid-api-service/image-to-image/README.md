# SeeDream Image-to-Image API

Python client for Volcano Engine's ARK API using the Doubao SeeDream 4.0 model for image-to-image generation.

## Features

- **Image Transformation**: Transform images based on text prompts
- **Multi-Image Support**: Process 1-2 input images simultaneously
- **Automatic S3 Upload**: Generated images are automatically uploaded to S3 with permanent CloudFront URLs
- **Automatic Size Detection**: Intelligently detects optimal output size based on input image aspect ratio
- **Flexible Sizing**: Support for 8 different aspect ratios (1:1, 4:3, 3:4, 16:9, 9:16, 3:2, 2:3, 21:9)
- **Batch Processing**: Generate 2-4 variations concurrently with graceful error handling
- **Retry Mechanism**: Built-in retry logic with exponential backoff
- **Type Safety**: Full type hints and enums for better IDE support
- **Error Handling**: Comprehensive error handling and validation

## Installation

```bash
# Install dependencies
pip install requests boto3

# Optional: Install Pillow for automatic size detection
pip install Pillow

# Set up environment variables
export ARK_API_KEY='your_ark_api_key_here'
export AWS_ACCESS_KEY='your_aws_access_key'
export AWS_ACCESS_SECRET='your_aws_secret_key'
export AWS_DEFAULT_REGION='us-east-1'
export S3_BUCKET_NAME='your-s3-bucket'
export CLOUDFRONT_DOMAIN='https://your-cloudfront-domain.cloudfront.net'
```

**Dependencies:**
- `requests` (required): For making HTTP requests
- `boto3` (required): For S3 upload functionality
- `Pillow` (optional): For automatic image size detection based on aspect ratio

**Environment Variables:**
- `ARK_API_KEY` (required): Your Volcano Engine ARK API key
- `S3_BUCKET_NAME` (required): AWS S3 bucket name for storing generated images
- `CLOUDFRONT_DOMAIN` (required): CloudFront domain for serving images
- `AWS_ACCESS_KEY` (required): AWS access key
- `AWS_ACCESS_SECRET` (required): AWS secret key
- `AWS_DEFAULT_REGION` (optional): AWS region, defaults to us-east-1

## Quick Start

```python
from seedream import SeeDreamClient, ImageSize

# Initialize client (auto_upload_s3=True by default)
client = SeeDreamClient()

# Generate image - returns permanent CloudFront URL
response = client.generate(
    prompt="Transform this image with vibrant colors",
    image=["https://example.com/image.png"]
    # size is automatically detected from input image aspect ratio
)

# Get permanent CloudFront URL
print(f"CloudFront URL: {response.image_urls[0]}")
# Output: https://your-cdn.cloudfront.net/seedream/20241119_123456_abc123.jpg

# Disable S3 upload (returns temporary Volcano Engine URLs)
client_no_s3 = SeeDreamClient(auto_upload_s3=False)
response = client_no_s3.generate(
    prompt="Transform this image",
    image=["https://example.com/image.png"]
)
# Returns temporary pre-signed URL that expires in 24 hours
```

## Usage Examples

### Auto-Detect Size (Recommended)

The client automatically detects the best output size based on your input image's aspect ratio:

```python
client = SeeDreamClient()

# No size specified - automatically matches input image aspect ratio
response = client.generate(
    prompt="Make this image more vibrant and add dramatic lighting",
    image=["https://example.com/input.png"]
)

# Or explicitly use "auto"
response = client.generate(
    prompt="Enhance colors",
    image=["https://example.com/input.png"],
    size="auto"
)
```

**Note:** Auto-detection requires the `Pillow` library. Install with: `pip install Pillow`

### Manual Size Selection

```python
client = SeeDreamClient()

response = client.generate(
    prompt="Transform this image",
    image=["https://example.com/input.png"],
    size=ImageSize.LANDSCAPE_4_3
)
```

### Clothing Transfer

```python
response = client.generate(
    prompt="Transfer the clothing from image 1 to image 2",
    image=[
        "https://example.com/person.png",
        "https://example.com/clothing.png"
    ],
    size=ImageSize.SQUARE_2K
)
```

### With Retry Logic

```python
response = client.generate_with_retry(
    prompt="Transform this landscape into winter scene",
    image=["https://example.com/summer.png"],
    max_retries=3,
    size=ImageSize.LANDSCAPE_16_9
)
```

### Batch Generation

Generate 2-4 images concurrently with graceful error handling:

```python
# Generate 3 variations of the same transformation
responses = client.batch_generate(
    prompt="Apply artistic watercolor effect",
    image=["https://example.com/input.png"],
    batch_size=3,
    size=ImageSize.SQUARE_2K
)

# Process all successfully generated images
# Note: If some generations fail, you'll get warnings but still receive the successful ones
print(f"Successfully generated {len(responses)} out of 3 images")
for i, response in enumerate(responses, 1):
    print(f"Variant {i}: {response.image_urls[0]}")
```

### Batch Generation with Retry

```python
# Generate 4 images with automatic retry
responses = client.batch_generate_with_retry(
    prompt="Convert to anime style",
    image=["https://example.com/photo.png"],
    batch_size=4,
    max_retries=3,
    size=ImageSize.PORTRAIT_9_16
)

print(f"Successfully generated {len(responses)} variations")
```

### Custom Configuration

```python
from seedream import (
    SeeDreamClient,
    ImageSize,
    ResponseFormat,
    SequentialGeneration
)

client = SeeDreamClient(api_key="custom_key")

response = client.generate(
    prompt="Your transformation prompt",
    image=["https://example.com/input.png"],
    size=ImageSize.PORTRAIT_9_16,
    sequential_image_generation=SequentialGeneration.ENABLED,
    response_format=ResponseFormat.URL,
    timeout=120
)

# Batch generation example
responses = client.batch_generate(
    prompt="Generate multiple variations",
    image=["https://example.com/input.png"],
    batch_size=4,
    size=ImageSize.SQUARE_2K,
    response_format=ResponseFormat.URL,
    timeout=120
)
```

## API Reference

### SeeDreamClient

Main client for interacting with the SeeDream API.

#### Constructor

```python
SeeDreamClient(api_key: Optional[str] = None)
```

- `api_key`: ARK API key. Falls back to `ARK_API_KEY` environment variable if not provided.

#### Methods

##### generate()

```python
generate(
    prompt: str,
    image: List[str],
    size: Optional[Union[ImageSize, str]] = None,
    sequential_image_generation: SequentialGeneration = SequentialGeneration.DISABLED,
    response_format: ResponseFormat = ResponseFormat.URL,
    timeout: int = 60
) -> SeeDreamResponse
```

Generate images using the SeeDream API.

**Parameters:**
- `prompt`: Text description of desired transformation
- `image`: List of 1-2 image URLs
- `size`: Output size. Options:
  - `None` (default): Auto-detect from first image's aspect ratio
  - `"auto"`: Explicitly request auto-detection
  - `ImageSize` enum: Specific size (e.g., SQUARE_2K, LANDSCAPE_16_9, PORTRAIT_9_16)
  - String: Pixel format (e.g., "2048x2048", "2560x1440")
- `sequential_image_generation`: Enable sequential generation mode
- `response_format`: Response format (url or b64_json)
- `timeout`: Request timeout in seconds

**Note:**
- Auto-detection requires the `Pillow` library (`pip install Pillow`)
- Both `watermark` and `stream` are always set to `false` for all generated images

**Returns:** `SeeDreamResponse` object containing generated image URLs

##### generate_with_retry()

```python
generate_with_retry(
    prompt: str,
    image: List[str],
    max_retries: int = 3,
    **kwargs
) -> SeeDreamResponse
```

Generate images with automatic retry on failure.

**Parameters:**
- `prompt`: Text description
- `image`: List of image URLs
- `max_retries`: Maximum retry attempts
- `**kwargs`: Additional arguments for `generate()`

##### batch_generate()

```python
batch_generate(
    prompt: str,
    image: List[str],
    batch_size: int = 2,
    size: Optional[Union[ImageSize, str]] = None,
    response_format: ResponseFormat = ResponseFormat.URL,
    timeout: int = 120
) -> List[SeeDreamResponse]
```

Generate multiple images concurrently using batch processing.

**Error Handling:** This method handles errors gracefully. If some generations fail, it returns the successful ones and emits a warning (instead of raising an exception).

**Parameters:**
- `prompt`: Text description of desired transformation
- `image`: List of 1-2 image URLs
- `batch_size`: Number of images to generate (2-4)
- `size`: Output size (same options as `generate()`, defaults to auto-detection)
- `response_format`: Response format (url or b64_json)
- `timeout`: Request timeout in seconds per request

**Note:**
- Auto-detection requires the `Pillow` library (`pip install Pillow`)
- `sequential_image_generation` is always set to `disabled`
- Both `watermark` and `stream` are always `false` for batch generation

**Returns:** List of `SeeDreamResponse` objects for successful generations. May return fewer than `batch_size` if some generations fail.

**Raises:**
- `ValueError`: If batch_size is not between 2-4

**Warnings:**
- `RuntimeWarning`: Emitted if any generations fail (execution continues)

##### batch_generate_with_retry()

```python
batch_generate_with_retry(
    prompt: str,
    image: List[str],
    batch_size: int = 2,
    max_retries: int = 3,
    **kwargs
) -> List[SeeDreamResponse]
```

Generate multiple images concurrently with automatic retry on failure.

**Error Handling:** This method handles errors gracefully. If some generations fail after all retries, it returns the successful ones and emits a warning (instead of raising an exception).

**Parameters:**
- `prompt`: Text description
- `image`: List of image URLs
- `batch_size`: Number of images to generate (2-4)
- `max_retries`: Maximum retry attempts per image
- `**kwargs`: Additional arguments for `generate()`

**Returns:** List of `SeeDreamResponse` objects for successful generations. May return fewer than `batch_size` if some generations fail after retries.

**Raises:**
- `ValueError`: If batch_size is not between 2-4

**Warnings:**
- `RuntimeWarning`: Emitted if any generations fail after retries (execution continues)

### Enums

#### ImageSize
- `SQUARE_2K`: 2048x2048 (1:1 aspect ratio)
- `LANDSCAPE_4_3`: 2304x1728 (4:3 aspect ratio)
- `PORTRAIT_3_4`: 1728x2304 (3:4 aspect ratio)
- `LANDSCAPE_16_9`: 2560x1440 (16:9 aspect ratio)
- `PORTRAIT_9_16`: 1440x2560 (9:16 aspect ratio)
- `LANDSCAPE_3_2`: 2496x1664 (3:2 aspect ratio)
- `PORTRAIT_2_3`: 1664x2496 (2:3 aspect ratio)
- `ULTRAWIDE_21_9`: 3024x1296 (21:9 aspect ratio)

#### ResponseFormat
- `URL`: Return image URLs
- `B64_JSON`: Return base64-encoded images

#### SequentialGeneration
- `ENABLED`: Enable sequential generation
- `DISABLED`: Disable sequential generation

### SeeDreamResponse

Response object from the API.

**Attributes:**
- `image_urls`: List of generated image URLs or base64 strings
- `created`: Timestamp of creation
- `raw_response`: Full API response dictionary

## Testing

Run the test suite:

```bash
# Set API key
export ARK_API_KEY='your_api_key_here'

# Run tests
python test_seedream.py
```

Run the basic example:

```bash
python seedream.py
```

## Error Handling

The client includes comprehensive error handling:

```python
from seedream import SeeDreamClient
import requests

client = SeeDreamClient()

try:
    response = client.generate(
        prompt="Your prompt",
        image=["https://example.com/image.png"]
    )
except ValueError as e:
    print(f"Invalid parameters: {e}")
except requests.HTTPError as e:
    print(f"API error: {e}")
except Exception as e:
    print(f"Unexpected error: {e}")
```

## API Limits

- Maximum 2 input images per request
- Supported image formats: PNG, JPEG
- Image URLs must be publicly accessible
- Default timeout: 60 seconds

## Environment Variables

- `ARK_API_KEY`: Your Volcano Engine ARK API key (required)

## License

This client is part of the short-drama backend service.
