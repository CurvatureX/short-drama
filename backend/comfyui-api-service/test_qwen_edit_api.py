#!/usr/bin/env python3
"""
Test script for ComfyUI Qwen Edit API service
"""

import requests
import time
import sys

API_HOST = "34.203.11.145"
API_PORT = 8001
BASE_URL = f"http://{API_HOST}:{API_PORT}"

def test_health_check():
    """Test health check endpoint"""
    print("Testing health check...")
    try:
        response = requests.get(f"{BASE_URL}/qwen-edit/health", timeout=5)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        return response.status_code == 200
    except Exception as e:
        print(f"Error: {e}")
        return False

def test_submit_job(image_url, prompt, image2_url=None, image3_url=None, steps=4, cfg=1.0):
    """Submit a Qwen image editing job"""
    print(f"\nSubmitting job...")
    print(f"Image 1: {image_url}")
    if image2_url:
        print(f"Image 2: {image2_url}")
    if image3_url:
        print(f"Image 3: {image3_url}")
    print(f"Prompt: {prompt}")
    print(f"Steps: {steps}")
    print(f"CFG: {cfg}")

    try:
        payload = {
            "image_url": image_url,
            "prompt": prompt,
            "steps": steps,
            "cfg": cfg
        }

        if image2_url:
            payload["image2_url"] = image2_url
        if image3_url:
            payload["image3_url"] = image3_url

        response = requests.post(
            f"{BASE_URL}/qwen-edit/edit",
            json=payload,
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
            response = requests.get(f"{BASE_URL}/qwen-edit/status/{job_id}", timeout=5)
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
    print("ComfyUI Qwen Edit API Service Test")
    print("=" * 60)

    # Test 1: Health check
    print("\n[Test 1] Health Check")
    print("-" * 60)
    if not test_health_check():
        print("✗ Health check failed!")
        sys.exit(1)
    print("✓ Health check passed!")

    # Test 2: Submit job
    print("\n[Test 2] Submit Qwen Edit Job")
    print("-" * 60)

    # Example with single image
    image_url = "https://example.com/test-image.jpg"
    prompt = "提取黑白线稿"

    # Example with multiple images (optional)
    # image2_url = "https://example.com/test-image2.jpg"
    # image3_url = "https://example.com/test-image3.jpg"

    print("\nNOTE: Please update the image_url in the script with a valid URL")
    print(f"Supported formats:")
    print(f"  - S3 URI: s3://bucket-name/path/to/image.jpg")
    print(f"  - HTTP URL: http://example.com/image.jpg")
    print(f"  - HTTPS URL: https://example.com/image.jpg")
    print(f"\nCurrent URL: {image_url}")
    print(f"\nYou can also provide optional image2_url and image3_url for multi-image editing")

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
