#!/usr/bin/env python3
"""
Test script for ComfyUI Unified API
"""

import requests
import time
import sys

API_HOST = "34.203.11.145"
API_PORT = 8000
BASE_URL = f"http://{API_HOST}:{API_PORT}"

def test_root():
    """Test root endpoint"""
    print("Testing root endpoint...")
    try:
        response = requests.get(f"{BASE_URL}/", timeout=5)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        return response.status_code == 200
    except Exception as e:
        print(f"Error: {e}")
        return False

def test_health():
    """Test health check"""
    print("\nTesting health check...")
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        return response.status_code == 200
    except Exception as e:
        print(f"Error: {e}")
        return False

def test_camera_angle(image_url, prompt, steps=8):
    """Test camera angle API"""
    print(f"\n=== Camera Angle Test ===")
    print(f"Image: {image_url}")
    print(f"Prompt: {prompt}")

    try:
        # Submit job
        response = requests.post(
            f"{BASE_URL}/api/v1/camera-angle/jobs",
            json={
                "image_url": image_url,
                "prompt": prompt,
                "steps": steps
            },
            timeout=10
        )
        print(f"Submit Status: {response.status_code}")
        job = response.json()
        job_id = job['job_id']
        print(f"Job ID: {job_id}")

        # Poll status
        print("\nPolling status...")
        start_time = time.time()
        while time.time() - start_time < 300:
            response = requests.get(
                f"{BASE_URL}/api/v1/camera-angle/jobs/{job_id}",
                timeout=5
            )
            status = response.json()
            print(f"Status: {status['status']}")

            if status['status'] == 'completed':
                print(f"✓ Result: {status['result_s3_uri']}")
                return True
            elif status['status'] == 'failed':
                print(f"✗ Error: {status['error']}")
                return False

            time.sleep(5)

        print("✗ Timeout")
        return False

    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def test_image_edit(image_url, prompt, image2_url=None, image3_url=None, steps=4):
    """Test image edit API"""
    print(f"\n=== Image Edit Test ===")
    print(f"Image 1: {image_url}")
    if image2_url:
        print(f"Image 2: {image2_url}")
    if image3_url:
        print(f"Image 3: {image3_url}")
    print(f"Prompt: {prompt}")

    try:
        # Submit job
        payload = {
            "image_url": image_url,
            "prompt": prompt,
            "steps": steps
        }
        if image2_url:
            payload["image2_url"] = image2_url
        if image3_url:
            payload["image3_url"] = image3_url

        response = requests.post(
            f"{BASE_URL}/api/v1/qwen-image-edit/jobs",
            json=payload,
            timeout=10
        )
        print(f"Submit Status: {response.status_code}")
        job = response.json()
        job_id = job['job_id']
        print(f"Job ID: {job_id}")

        # Poll status using unified endpoint
        print("\nPolling status (using unified endpoint)...")
        start_time = time.time()
        while time.time() - start_time < 300:
            response = requests.get(
                f"{BASE_URL}/api/v1/jobs/{job_id}",  # Unified endpoint
                timeout=5
            )
            status = response.json()
            print(f"Status: {status['status']}")

            if status['status'] == 'completed':
                print(f"✓ Result: {status['result_s3_uri']}")
                return True
            elif status['status'] == 'failed':
                print(f"✗ Error: {status['error']}")
                return False

            time.sleep(5)

        print("✗ Timeout")
        return False

    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def main():
    """Main test function"""
    print("=" * 70)
    print("ComfyUI Unified API Test Suite")
    print("=" * 70)

    # Test 1: Root endpoint
    print("\n[Test 1] Root Endpoint")
    print("-" * 70)
    if not test_root():
        print("✗ Root endpoint test failed!")
        sys.exit(1)
    print("✓ Root endpoint test passed!")

    # Test 2: Health check
    print("\n[Test 2] Health Check")
    print("-" * 70)
    if not test_health():
        print("✗ Health check failed!")
        sys.exit(1)
    print("✓ Health check passed!")

    # Test 3: Camera Angle API (optional)
    print("\n[Test 3] Camera Angle API")
    print("-" * 70)
    response = input("Do you want to test camera angle API? (yes/no): ")
    if response.lower() == 'yes':
        image_url = input("Enter image URL (or press Enter to skip): ")
        if image_url:
            prompt = input("Enter prompt (default: 将镜头转为俯视): ") or "将镜头转为俯视"
            if test_camera_angle(image_url, prompt):
                print("✓ Camera angle test passed!")
            else:
                print("✗ Camera angle test failed!")

    # Test 4: Image Edit API (optional)
    print("\n[Test 4] Image Edit API")
    print("-" * 70)
    response = input("Do you want to test image edit API? (yes/no): ")
    if response.lower() == 'yes':
        image_url = input("Enter main image URL (or press Enter to skip): ")
        if image_url:
            prompt = input("Enter prompt (default: 提取黑白线稿): ") or "提取黑白线稿"
            image2_url = input("Enter optional image 2 URL (or press Enter to skip): ") or None
            image3_url = input("Enter optional image 3 URL (or press Enter to skip): ") or None
            if test_image_edit(image_url, prompt, image2_url, image3_url):
                print("✓ Image edit test passed!")
            else:
                print("✗ Image edit test failed!")

    print("\n" + "=" * 70)
    print("✓ All basic tests completed!")
    print("=" * 70)

if __name__ == "__main__":
    main()
