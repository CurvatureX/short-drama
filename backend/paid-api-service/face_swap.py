"""
Face Swap Service using QWEN3-VL for face detection and SeeDream for face reconstruction
"""

import os
import sys
import boto3
import requests
from PIL import Image, ImageDraw
from io import BytesIO
from datetime import datetime
import uuid
import json
import re
from dashscope import MultiModalConversation

# Add the image-to-image directory to the path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(current_dir, 'image-to-image'))
from seedream import SeeDreamClient, ImageSize


# Default prompt for face swapping
DEFAULT_FACE_SWAP_PROMPT = """Replace the black masked face in image 1 using the identity from Image 2.
Keep everything outside the black mask unchanged: hair, head shape, pose, background, lighting, color grading, and expression.
Only reconstruct the facial features inside the mask, matching Image 2's identity accurately while maintaining Image 1's camera angle and lighting.
Blend the new face naturally into the surrounding skin."""


def detect_face_with_qwen(image_path, api_key):
    """
    Use QWEN3-VL to detect person's face (without hair)

    Args:
        image_path: Path to the image file
        api_key: Dashscope API key

    Returns:
        Detection result dictionary containing face bounding boxes
    """
    messages = [
        {
            "role": "user",
            "content": [
                {"image": f"file://{image_path}"},
                {
                    "text": """Detect all people's faces in the image.
For each person, return the bounding box that covers only the face (forehead to chin, excluding hair).
Return in JSON format:
[
  {"bbox": [x1, y1, x2, y2], "gender": "male/female"}
]"""
                }
            ]
        }
    ]

    response = MultiModalConversation.call(
        api_key=api_key,
        model="qwen3-vl-plus",
        messages=messages,
    )

    result_text = response.output.choices[0].message.content[0]["text"]
    print("QWEN3-VL Detection Response:")
    print(result_text)
    print("-" * 80)

    # Extract coordinates
    try:
        result = json.loads(result_text.strip().strip('`').strip('json').strip())

        # Return object array
        if isinstance(result, list) and len(result) > 0:
            faces = []
            for item in result:
                if isinstance(item, dict):
                    # Try multiple possible key names
                    bbox = None
                    for key in ["bbox_2d", "bbox", "head_bbox", "face_bbox"]:
                        if key in item:
                            bbox = item[key]
                            break

                    if bbox:
                        faces.append({
                            "normalized_bbox": bbox,
                            "label": item.get("label", ""),
                            "gender": item.get("gender", "unknown")
                        })

            if faces:
                return {"faces": faces}

    except Exception as e:
        print(f"JSON parsing error: {e}")

    # If parsing fails, try to extract all coordinates
    arrays = re.findall(r'\[(\d+),\s*(\d+),\s*(\d+),\s*(\d+)\]', result_text)
    if arrays:
        faces = []
        for arr in arrays:
            coords = [int(x) for x in arr]
            faces.append({"normalized_bbox": coords, "label": "", "gender": "unknown"})
        return {"faces": faces}

    return {"faces": [], "raw_response": result_text}


def convert_normalized_to_pixels(normalized_bbox, img_width, img_height, norm_range=1000):
    """
    Convert normalized coordinates to pixel coordinates

    Args:
        normalized_bbox: Normalized bounding box [x1, y1, x2, y2]
        img_width: Image width in pixels
        img_height: Image height in pixels
        norm_range: Normalization range (default 1000)

    Returns:
        Pixel coordinates [x1, y1, x2, y2]
    """
    x1_norm, y1_norm, x2_norm, y2_norm = normalized_bbox

    x1 = int(x1_norm / norm_range * img_width)
    y1 = int(y1_norm / norm_range * img_height)
    x2 = int(x2_norm / norm_range * img_width)
    y2 = int(y2_norm / norm_range * img_height)

    return [x1, y1, x2, y2]


def create_elliptical_mask_for_face(bbox, img_width, img_height,
                                     expand_factor=1.05):
    """
    Create elliptical mask covering the face only (no hair)

    Args:
        bbox: [x1, y1, x2, y2] - Face bounding box
        img_width: Image width
        img_height: Image height
        expand_factor: Slight expansion factor for smooth edges - default 1.05 (5% extra)

    Returns:
        Ellipse bounding box [x1, y1, x2, y2]
    """
    x1, y1, x2, y2 = bbox

    # Calculate width and height of the detected bbox
    width = x2 - x1
    height = y2 - y1

    # Calculate center point
    center_x = (x1 + x2) / 2
    center_y = (y1 + y2) / 2

    # Calculate ellipse radii with minimal expansion (just for smooth edges)
    ellipse_width_radius = (width / 2) * expand_factor
    ellipse_height_radius = (height / 2) * expand_factor

    # Ellipse bounding box
    ellipse_bbox = [
        max(0, center_x - ellipse_width_radius),
        max(0, center_y - ellipse_height_radius),
        min(img_width, center_x + ellipse_width_radius),
        min(img_height, center_y + ellipse_height_radius)
    ]

    return ellipse_bbox


def mask_face_with_ellipse(image_path, detection_result, face_index=0):
    """
    Create black elliptical mask on the specified face

    Args:
        image_path: Path to the input image
        detection_result: Detection result from QWEN3-VL
        face_index: Index of the face to mask (default: 0, first detected face)

    Returns:
        PIL Image with black masked face
    """
    img = Image.open(image_path)
    img_width, img_height = img.size

    print(f"Image size: {img_width} x {img_height}")

    faces = detection_result.get("faces", [])
    if not faces:
        print("Error: No faces detected")
        if "raw_response" in detection_result:
            print("Raw response:", detection_result["raw_response"])
        raise ValueError("No faces detected in the image")

    if face_index >= len(faces):
        raise ValueError(f"Face index {face_index} out of range (detected {len(faces)} faces)")

    print(f"Detected {len(faces)} face(s), masking face #{face_index}")

    # Create mask layer
    mask = Image.new('L', (img_width, img_height), 0)
    mask_draw = ImageDraw.Draw(mask)

    face = faces[face_index]
    normalized_bbox = face.get("normalized_bbox")
    if not normalized_bbox:
        raise ValueError(f"No bounding box found for face #{face_index}")

    print(f"\nFace #{face_index}:")
    print(f"  QWEN normalized coordinates: {normalized_bbox}")

    # Convert to pixel coordinates
    pixel_bbox = convert_normalized_to_pixels(normalized_bbox, img_width, img_height)
    print(f"  Pixel coordinates: {pixel_bbox}")

    # Create elliptical mask
    ellipse_bbox = create_elliptical_mask_for_face(pixel_bbox, img_width, img_height)
    print(f"  Ellipse mask boundary: {ellipse_bbox}")

    # Draw ellipse on mask
    mask_draw.ellipse(ellipse_bbox, fill=255)

    # Create black layer
    black_layer = Image.new('RGB', (img_width, img_height), 'black')

    # Composite black layer onto original image using mask
    img.paste(black_layer, mask=mask)

    print(f"Masked face #{face_index}")
    return img


def upload_image_to_s3(image, s3_bucket, cloudfront_domain, prefix="face_swap"):
    """
    Upload PIL Image to S3 and return CloudFront URL

    Args:
        image: PIL Image object
        s3_bucket: S3 bucket name
        cloudfront_domain: CloudFront domain
        prefix: S3 key prefix

    Returns:
        CloudFront URL of the uploaded image
    """
    # Save image to bytes
    buffer = BytesIO()
    image.save(buffer, format='PNG')
    buffer.seek(0)

    # Generate unique S3 key
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    unique_id = str(uuid.uuid4())[:8]
    s3_key = f"{prefix}/{timestamp}_{unique_id}.png"

    # Upload to S3
    s3_client = boto3.client(
        's3',
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY"),
        aws_secret_access_key=os.getenv("AWS_ACCESS_SECRET"),
        region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1")
    )

    s3_client.put_object(
        Bucket=s3_bucket,
        Key=s3_key,
        Body=buffer.getvalue(),
        ContentType='image/png',
        CacheControl='public, max-age=31536000'
    )

    # Return CloudFront URL
    cloudfront_url = f"{cloudfront_domain.rstrip('/')}/{s3_key}"
    print(f"Uploaded to S3: {cloudfront_url}")
    return cloudfront_url


def create_face_mask(
    source_image_url: str,
    face_index: int = 0
) -> str:
    """
    API 1: Create black elliptical mask on detected face

    This method:
    1. Downloads the source image
    2. Uses QWEN3-VL to detect faces
    3. Creates a black elliptical mask on the specified face
    4. Uploads the masked image to S3

    Args:
        source_image_url: URL of the source image
        face_index: Index of the face to mask (default: 0, first detected face)

    Returns:
        CloudFront URL of the masked image

    Example:
        masked_url = create_face_mask(
            source_image_url="https://example.com/person.jpg",
            face_index=0
        )
    """
    # Validate environment variables
    dashscope_key = os.getenv("DASHSCOPE_API_KEY")
    s3_bucket = os.getenv("S3_BUCKET_NAME")
    cloudfront_domain = os.getenv("CLOUDFRONT_DOMAIN")

    if not dashscope_key:
        raise ValueError("DASHSCOPE_API_KEY environment variable not set")
    if not s3_bucket:
        raise ValueError("S3_BUCKET_NAME environment variable not set")
    if not cloudfront_domain:
        raise ValueError("CLOUDFRONT_DOMAIN environment variable not set")

    print("=" * 80)
    print("Create Face Mask - Step by Step")
    print("=" * 80)

    # Step 1: Download source image
    print("\n[Step 1/3] Downloading source image...")
    response = requests.get(source_image_url, timeout=30)
    response.raise_for_status()

    # Save to temporary file
    temp_dir = "/tmp/face_swap"
    os.makedirs(temp_dir, exist_ok=True)
    temp_input_path = f"{temp_dir}/source_{uuid.uuid4()}.png"

    with open(temp_input_path, 'wb') as f:
        f.write(response.content)
    print(f"✓ Downloaded to: {temp_input_path}")

    # Step 2: Detect face and create mask
    print("\n[Step 2/3] Detecting face with QWEN3-VL and creating black mask...")
    detection_result = detect_face_with_qwen(temp_input_path, dashscope_key)
    masked_image = mask_face_with_ellipse(temp_input_path, detection_result, face_index)
    print("✓ Created black elliptical mask on face")

    # Step 3: Upload masked image to S3
    print("\n[Step 3/3] Uploading masked image to S3...")
    masked_image_url = upload_image_to_s3(masked_image, s3_bucket, cloudfront_domain)
    print(f"✓ Masked image URL: {masked_image_url}")

    # Cleanup temporary file
    try:
        os.remove(temp_input_path)
    except:
        pass

    print("=" * 80)
    print("Face Mask Creation Complete!")
    print("=" * 80)

    return masked_image_url


def apply_face_swap(
    masked_image_url: str,
    target_face_url: str,
    prompt: str = None,
    size: ImageSize = None
) -> str:
    """
    API 2: Apply face swap using SeeDream

    This method takes a masked image (with black elliptical mask on face) and
    reconstructs the face using the target face identity.

    Args:
        masked_image_url: URL of the image with black face mask
        target_face_url: URL of the target face image (identity to use)
        prompt: Custom prompt for SeeDream (default: face swap prompt)
        size: Output image size (default: auto-detect)

    Returns:
        CloudFront URL of the final face-swapped image

    Example:
        result_url = apply_face_swap(
            masked_image_url="https://cloudfront.net/masked.png",
            target_face_url="https://example.com/celebrity.jpg"
        )
    """
    print("=" * 80)
    print("Apply Face Swap with SeeDream")
    print("=" * 80)

    print("\n[Step 1/1] Using SeeDream to swap face...")
    seedream_client = SeeDreamClient()

    if prompt is None:
        prompt = DEFAULT_FACE_SWAP_PROMPT

    result = seedream_client.generate(
        prompt=prompt,
        image=[masked_image_url, target_face_url],
        size=size  # Will auto-detect if None
    )

    final_url = result.image_urls[0]
    print(f"✓ Face swap complete!")
    print(f"✓ Final result URL: {final_url}")

    print("=" * 80)
    print("Face Swap Complete!")
    print("=" * 80)

    return final_url


def swap_with_seedream(
    source_image_url: str,
    target_face_url: str,
    face_index: int = 0,
    prompt: str = None,
    size: ImageSize = None
) -> str:
    """
    Combined API: Full face swap pipeline (calls create_face_mask + apply_face_swap)

    This method:
    1. Downloads the source image
    2. Uses QWEN3-VL to detect faces and create a black elliptical mask
    3. Uploads the masked image to S3
    4. Uses SeeDream to reconstruct the face using the target face

    Args:
        source_image_url: URL of the source image (where face will be swapped)
        target_face_url: URL of the target face image (identity to use)
        face_index: Index of the face to swap (default: 0, first detected face)
        prompt: Custom prompt for SeeDream (default: face swap prompt)
        size: Output image size (default: auto-detect)

    Returns:
        CloudFront URL of the final face-swapped image

    Example:
        result_url = swap_with_seedream(
            source_image_url="https://example.com/person.jpg",
            target_face_url="https://example.com/celebrity.jpg"
        )
    """
    print("=" * 80)
    print("Full Face Swap Pipeline")
    print("=" * 80)

    # Step 1: Create face mask
    print("\n[Pipeline Step 1/2] Creating face mask...")
    masked_image_url = create_face_mask(source_image_url, face_index)

    # Step 2: Apply face swap
    print("\n[Pipeline Step 2/2] Applying face swap...")
    final_url = apply_face_swap(masked_image_url, target_face_url, prompt, size)

    print("=" * 80)
    print("Full Pipeline Complete!")
    print("=" * 80)

    return final_url


def main():
    """Example usage of face swap"""
    import sys

    if len(sys.argv) < 3:
        print("Usage: python face_swap.py <source_image_url> <target_face_url>")
        print("\nExample:")
        print("  python face_swap.py https://example.com/person.jpg https://example.com/celebrity.jpg")
        sys.exit(1)

    source_url = sys.argv[1]
    target_url = sys.argv[2]

    result_url = swap_with_seedream(source_url, target_url)
    print(f"\n✓ Success! Face-swapped image: {result_url}")


if __name__ == "__main__":
    main()
