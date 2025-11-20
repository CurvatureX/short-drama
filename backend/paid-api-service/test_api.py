#!/usr/bin/env python3
"""
Test script for Paid API Service

Tests all endpoints to verify functionality.
"""

import os
import sys
import time
import requests
from typing import Optional

# Configuration
API_URL = os.getenv('API_URL', 'http://localhost:8000')

# Test image URLs
TEST_SOURCE_IMAGE = "https://ark-project.tos-cn-beijing.volces.com/doc_image/seedream4_imagesToimage_1.png"
TEST_TARGET_IMAGE = "https://ark-project.tos-cn-beijing.volces.com/doc_image/seedream4_imagesToimage_2.png"


def test_health_check():
    """Test health check endpoint"""
    print("\n" + "="*60)
    print("Test 1: Health Check")
    print("="*60)

    try:
        response = requests.get(f"{API_URL}/health", timeout=5)
        response.raise_for_status()
        result = response.json()

        print(f"✓ Health check passed")
        print(f"  Status: {result.get('status')}")
        if result.get('missing_env_vars'):
            print(f"  ⚠ Missing env vars: {result['missing_env_vars']}")

        return True

    except Exception as e:
        print(f"✗ Health check failed: {e}")
        return False


def poll_job_status(job_id: str, timeout: int = 300) -> Optional[dict]:
    """Poll job status until completion"""
    start_time = time.time()
    poll_count = 0

    print(f"\nPolling job {job_id}...")

    while time.time() - start_time < timeout:
        try:
            response = requests.get(f"{API_URL}/api/v1/jobs/{job_id}", timeout=10)
            response.raise_for_status()
            status = response.json()

            poll_count += 1
            current_status = status.get('status')

            print(f"  [{poll_count}] Status: {current_status}")

            if current_status == 'completed':
                print(f"✓ Job completed after {poll_count} polls")
                return status
            elif current_status == 'failed':
                print(f"✗ Job failed: {status.get('error')}")
                return status
            elif current_status in ('pending', 'processing'):
                time.sleep(2)
            else:
                print(f"⚠ Unknown status: {current_status}")
                time.sleep(2)

        except Exception as e:
            print(f"⚠ Error polling: {e}")
            time.sleep(5)

    print(f"✗ Timeout after {timeout} seconds")
    return None


def test_face_mask():
    """Test face mask endpoint"""
    print("\n" + "="*60)
    print("Test 2: Face Mask")
    print("="*60)

    try:
        # Submit job
        payload = {
            "image_url": TEST_SOURCE_IMAGE,
            "face_index": 0
        }

        print(f"Submitting face mask job...")
        print(f"  Image: {TEST_SOURCE_IMAGE}")

        response = requests.post(
            f"{API_URL}/api/v1/face-mask/jobs",
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        result = response.json()

        job_id = result.get('job_id')
        print(f"✓ Job submitted: {job_id}")

        # Poll for completion
        final_status = poll_job_status(job_id)

        if final_status and final_status['status'] == 'completed':
            print(f"✓ Face mask test passed")
            print(f"  Result URL: {final_status.get('result_url')}")
            return True
        else:
            print(f"✗ Face mask test failed")
            return False

    except Exception as e:
        print(f"✗ Face mask test error: {e}")
        return False


def test_face_swap_with_mask(masked_url: str):
    """Test face swap endpoint with a masked image"""
    print("\n" + "="*60)
    print("Test 3: Face Swap (with pre-masked image)")
    print("="*60)

    try:
        # Submit job
        payload = {
            "masked_image_url": masked_url,
            "target_face_url": TEST_TARGET_IMAGE,
            "size": "auto"
        }

        print(f"Submitting face swap job...")
        print(f"  Masked: {masked_url}")
        print(f"  Target: {TEST_TARGET_IMAGE}")

        response = requests.post(
            f"{API_URL}/api/v1/face-swap/jobs",
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        result = response.json()

        job_id = result.get('job_id')
        print(f"✓ Job submitted: {job_id}")

        # Poll for completion
        final_status = poll_job_status(job_id)

        if final_status and final_status['status'] == 'completed':
            print(f"✓ Face swap test passed")
            print(f"  Result URL: {final_status.get('result_url')}")
            return True
        else:
            print(f"✗ Face swap test failed")
            return False

    except Exception as e:
        print(f"✗ Face swap test error: {e}")
        return False


def test_full_face_swap():
    """Test full face swap pipeline"""
    print("\n" + "="*60)
    print("Test 4: Full Face Swap Pipeline")
    print("="*60)

    try:
        # Submit job
        payload = {
            "source_image_url": TEST_SOURCE_IMAGE,
            "target_face_url": TEST_TARGET_IMAGE,
            "face_index": 0,
            "size": "auto"
        }

        print(f"Submitting full face swap job...")
        print(f"  Source: {TEST_SOURCE_IMAGE}")
        print(f"  Target: {TEST_TARGET_IMAGE}")

        response = requests.post(
            f"{API_URL}/api/v1/full-face-swap/jobs",
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        result = response.json()

        job_id = result.get('job_id')
        print(f"✓ Job submitted: {job_id}")

        # Poll for completion
        final_status = poll_job_status(job_id, timeout=600)  # Longer timeout for full pipeline

        if final_status and final_status['status'] == 'completed':
            print(f"✓ Full face swap test passed")
            print(f"  Result URL: {final_status.get('result_url')}")
            return True
        else:
            print(f"✗ Full face swap test failed")
            return False

    except Exception as e:
        print(f"✗ Full face swap test error: {e}")
        return False


def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("Paid API Service Test Suite")
    print("="*60)
    print(f"API URL: {API_URL}")

    results = {}

    # Test 1: Health check
    results['health'] = test_health_check()

    if not results['health']:
        print("\n✗ Health check failed. Cannot proceed with other tests.")
        sys.exit(1)

    # Test 2: Face mask
    results['face_mask'] = test_face_mask()

    # Test 4: Full pipeline (most important test)
    results['full_pipeline'] = test_full_face_swap()

    # Summary
    print("\n" + "="*60)
    print("Test Summary")
    print("="*60)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test_name, passed_test in results.items():
        status = "✓ PASS" if passed_test else "✗ FAIL"
        print(f"  {status}: {test_name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n✓ All tests passed!")
        sys.exit(0)
    else:
        print(f"\n✗ {total - passed} test(s) failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
