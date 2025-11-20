#!/usr/bin/env python3
"""
Test script for ComfyUI API service
"""

import requests
import time
import sys

API_HOST = "34.203.11.145"
API_PORT = 8000
BASE_URL = f"http://{API_HOST}:{API_PORT}"

def test_health_check():
    """Test health check endpoint"""
    print("Testing health check...")
    try:
        response = requests.get(f"{BASE_URL}/camera-angle/health", timeout=5)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        return response.status_code == 200
    except Exception as e:
        print(f"Error: {e}")
        return False

def test_submit_job(image_url, prompt, steps=8):
    """Submit an image editing job"""
    print(f"\nSubmitting job...")
    print(f"Image: {image_url}")
    print(f"Prompt: {prompt}")
    print(f"Steps: {steps}")

    try:
        response = requests.post(
            f"{BASE_URL}/camera-angle/edit",
            json={
                "image_url": image_url,
                "prompt": prompt,
                "steps": steps
            },
            timeout=10
        )
        print(f"Status: {response.status_code}")
        result = response.json()
        print(f"Job ID: {result.get('job_id')}")
        print(f"Status: {result.get('status')}")
        return result.get('job_id')
    except Exception as e:
        print(f"Error: {e}")
        return None

def test_get_status(job_id, max_wait=300):
    """Poll job status until completion"""
    print(f"\nPolling job status: {job_id}")

    start_time = time.time()
    while time.time() - start_time < max_wait:
        try:
            response = requests.get(f"{BASE_URL}/camera-angle/status/{job_id}", timeout=5)
            result = response.json()
            status = result.get('status')

            print(f"Status: {status}")

            if status == 'completed':
                print(f"✓ Job completed!")
                print(f"Result S3 URI: {result.get('result_s3_uri')}")
                return True
            elif status == 'failed':
                print(f"✗ Job failed!")
                print(f"Error: {result.get('error')}")
                return False
            elif status in ['pending', 'processing']:
                print(f"  Waiting... ({int(time.time() - start_time)}s elapsed)")
                time.sleep(5)
            else:
                print(f"Unknown status: {status}")
                return False

        except Exception as e:
            print(f"Error polling status: {e}")
            time.sleep(5)

    print(f"✗ Timeout after {max_wait}s")
    return False

def main():
    """Main test function"""
    print("=" * 60)
    print("ComfyUI API Service Test")
    print("=" * 60)

    # Test 1: Health check
    print("\n[Test 1] Health Check")
    print("-" * 60)
    if not test_health_check():
        print("✗ Health check failed!")
        sys.exit(1)
    print("✓ Health check passed!")

    # Test 2: Submit job (example - replace with actual S3 URI)
    print("\n[Test 2] Submit Image Editing Job")
    print("-" * 60)

    # You can use S3 URI or HTTPS URL
    # Example 1: S3 URI
    # image_url = "s3://your-bucket/test-images/test.jpg"

    # Example 2: HTTPS URL
    image_url = "https://example.com/test-image.jpg"

    prompt = "将镜头转为俯视"

    print("\nNOTE: Please update the image_url in the script with a valid URL")
    print(f"Supported formats:")
    print(f"  - S3 URI: s3://bucket-name/path/to/image.jpg")
    print(f"  - HTTP URL: http://example.com/image.jpg")
    print(f"  - HTTPS URL: https://example.com/image.jpg")
    print(f"\nCurrent URL: {image_url}")

    response = input("\nDo you want to continue with job submission test? (yes/no): ")
    if response.lower() != 'yes':
        print("Skipping job submission test")
        return

    job_id = test_submit_job(image_url, prompt)
    if not job_id:
        print("✗ Failed to submit job!")
        sys.exit(1)
    print("✓ Job submitted successfully!")

    # Test 3: Poll status
    print("\n[Test 3] Poll Job Status")
    print("-" * 60)
    if test_get_status(job_id):
        print("\n✓ All tests passed!")
    else:
        print("\n✗ Job processing failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()
