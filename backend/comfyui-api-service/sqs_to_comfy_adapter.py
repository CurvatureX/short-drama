#!/usr/bin/env python3
"""
SQS to ComfyUI Adapter Script

This script runs on the GPU EC2 instance and acts as a bridge between
SQS task queue and the local ComfyUI Unified API.

Responsibilities:
1. Poll SQS queue for new tasks (long polling)
2. Update DynamoDB status to 'processing'
3. Call local ComfyUI API with task parameters
4. Poll ComfyUI for completion
5. Update DynamoDB with final status and results
6. Delete SQS message

Note: This script does NOT handle shutdown logic - that's handled by
CloudWatch Alarm + Lambda based on queue metrics.
"""

import os
import sys
import json
import time
import signal
import requests
from typing import Dict, Any, Optional

import boto3
from botocore.exceptions import ClientError

# Configuration from environment variables
AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')
SQS_QUEUE_URL = os.getenv('SQS_QUEUE_URL', '')
DYNAMODB_TABLE = os.getenv('DYNAMODB_TABLE', 'task_store')
COMFYUI_API_URL = os.getenv('COMFYUI_API_URL', 'http://localhost:8000')
POLL_INTERVAL = int(os.getenv('POLL_INTERVAL', '20'))  # Long polling wait time

# Initialize AWS clients
sqs_client = boto3.client('sqs', region_name=AWS_REGION)
dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
table = dynamodb.Table(DYNAMODB_TABLE)

# Global flag for graceful shutdown
shutdown_flag = False


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    global shutdown_flag
    print(f"\nReceived signal {signum}. Initiating graceful shutdown...")
    shutdown_flag = True


def update_task_status(
    task_id: str,
    status: str,
    result_s3_uri: Optional[str] = None,
    error_message: Optional[str] = None,
    comfy_job_id: Optional[str] = None
):
    """Update task status in DynamoDB"""
    try:
        current_time = int(time.time())
        update_expr = "SET #status = :status, updated_at = :updated_at"
        expr_attr_names = {'#status': 'status'}
        expr_attr_values = {
            ':status': status,
            ':updated_at': current_time
        }

        if result_s3_uri:
            update_expr += ", result_s3_uri = :result_s3_uri"
            expr_attr_values[':result_s3_uri'] = result_s3_uri

        if error_message:
            update_expr += ", error_message = :error_message"
            expr_attr_values[':error_message'] = error_message

        if comfy_job_id:
            update_expr += ", comfy_job_id = :comfy_job_id"
            expr_attr_values[':comfy_job_id'] = comfy_job_id

        table.update_item(
            Key={'task_id': task_id},
            UpdateExpression=update_expr,
            ExpressionAttributeNames=expr_attr_names,
            ExpressionAttributeValues=expr_attr_values
        )
        print(f"✓ Updated task {task_id} status to: {status}")

    except Exception as e:
        print(f"✗ Error updating task status in DynamoDB: {e}")
        raise


def poll_comfyui_status(job_id: str, timeout: int = 600) -> Dict[str, Any]:
    """
    Poll ComfyUI API for job completion.

    Args:
        job_id: ComfyUI job ID
        timeout: Maximum time to wait (seconds)

    Returns:
        Final job status dictionary
    """
    start_time = time.time()
    poll_count = 0

    while time.time() - start_time < timeout:
        if shutdown_flag:
            raise Exception("Shutdown requested during polling")

        try:
            response = requests.get(
                f"{COMFYUI_API_URL}/api/v1/jobs/{job_id}",
                timeout=10
            )
            response.raise_for_status()
            job_status = response.json()

            poll_count += 1
            status = job_status.get('status')

            if status == 'completed':
                print(f"✓ ComfyUI job {job_id} completed (polled {poll_count} times)")
                return job_status
            elif status == 'failed':
                print(f"✗ ComfyUI job {job_id} failed: {job_status.get('error')}")
                return job_status
            elif status in ('pending', 'processing'):
                # Still processing, wait and retry
                time.sleep(2)
            else:
                print(f"⚠ Unknown status '{status}' for ComfyUI job {job_id}")
                time.sleep(2)

        except requests.RequestException as e:
            print(f"⚠ Error polling ComfyUI status: {e}")
            time.sleep(5)

    raise Exception(f"Timeout waiting for ComfyUI job {job_id} after {timeout} seconds")


def process_task(message: Dict[str, Any]):
    """
    Process a single task from SQS.

    This is the core business logic:
    1. Parse task from SQS message
    2. Update status to 'processing'
    3. Call ComfyUI API
    4. Poll for completion
    5. Update final status
    6. Delete SQS message
    """
    receipt_handle = message['ReceiptHandle']
    body = json.loads(message['Body'])

    task_id = body.get('task_id')
    api_path = body.get('api_path')
    request_body = body.get('request_body')

    print(f"\n{'='*60}")
    print(f"Processing task: {task_id}")
    print(f"API path: {api_path}")
    print(f"{'='*60}")

    try:
        # Step 1: Update DynamoDB to PROCESSING
        update_task_status(task_id, 'processing')

        # Step 2: Submit job to local ComfyUI API
        print(f"→ Submitting to ComfyUI: POST {COMFYUI_API_URL}{api_path}")
        response = requests.post(
            f"{COMFYUI_API_URL}{api_path}",
            json=request_body,
            timeout=30
        )
        response.raise_for_status()
        comfy_response = response.json()

        comfy_job_id = comfy_response.get('job_id')
        if not comfy_job_id:
            raise Exception("ComfyUI did not return a job_id")

        print(f"✓ ComfyUI accepted task. Job ID: {comfy_job_id}")

        # Update DynamoDB with ComfyUI job ID
        update_task_status(task_id, 'processing', comfy_job_id=comfy_job_id)

        # Step 3: Poll ComfyUI for completion
        print(f"→ Polling ComfyUI for completion...")
        final_status = poll_comfyui_status(comfy_job_id)

        # Step 4: Update DynamoDB with final status
        if final_status['status'] == 'completed':
            update_task_status(
                task_id,
                'completed',
                result_s3_uri=final_status.get('result_s3_uri')
            )
            print(f"✓ Task {task_id} completed successfully")
            print(f"  Result: {final_status.get('result_s3_uri')}")

        elif final_status['status'] == 'failed':
            update_task_status(
                task_id,
                'failed',
                error_message=final_status.get('error', 'Unknown error')
            )
            print(f"✗ Task {task_id} failed: {final_status.get('error')}")

        # Step 5: Delete message from SQS (task completed)
        sqs_client.delete_message(
            QueueUrl=SQS_QUEUE_URL,
            ReceiptHandle=receipt_handle
        )
        print(f"✓ Deleted message from SQS queue")

    except Exception as e:
        # Task failed - update DynamoDB but DO NOT delete SQS message
        # This allows the message to become visible again for retry
        error_msg = str(e)
        print(f"✗ Error processing task {task_id}: {error_msg}")

        try:
            update_task_status(task_id, 'failed', error_message=error_msg)
        except Exception as db_error:
            print(f"✗ Failed to update error status in DynamoDB: {db_error}")

        # Don't delete SQS message - let it retry or go to DLQ
        print(f"⚠ SQS message will become visible again for retry")


def main_loop():
    """
    Main polling loop.

    Continuously polls SQS for messages and processes them.
    Uses long polling (20 seconds) to reduce API calls and costs.
    """
    print(f"\n{'='*60}")
    print(f"SQS to ComfyUI Adapter Started")
    print(f"{'='*60}")
    print(f"AWS Region: {AWS_REGION}")
    print(f"SQS Queue: {SQS_QUEUE_URL}")
    print(f"DynamoDB Table: {DYNAMODB_TABLE}")
    print(f"ComfyUI API: {COMFYUI_API_URL}")
    print(f"Poll Interval: {POLL_INTERVAL} seconds (long polling)")
    print(f"{'='*60}\n")

    # Verify ComfyUI is accessible
    try:
        response = requests.get(f"{COMFYUI_API_URL}/health", timeout=5)
        if response.status_code == 200:
            print(f"✓ ComfyUI API is healthy\n")
        else:
            print(f"⚠ ComfyUI API returned status {response.status_code}\n")
    except Exception as e:
        print(f"⚠ Warning: Cannot reach ComfyUI API: {e}")
        print(f"  Continuing anyway - will retry on each task\n")

    consecutive_errors = 0
    max_consecutive_errors = 10

    while not shutdown_flag:
        try:
            # Long poll SQS for messages
            print(f"Polling SQS queue (waiting up to {POLL_INTERVAL} seconds)...")
            response = sqs_client.receive_message(
                QueueUrl=SQS_QUEUE_URL,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=POLL_INTERVAL,
                AttributeNames=['All'],
                MessageAttributeNames=['All'],
                VisibilityTimeout=300  # 5 minutes to process
            )

            messages = response.get('Messages', [])

            if messages:
                consecutive_errors = 0  # Reset error counter
                for message in messages:
                    if shutdown_flag:
                        print("Shutdown requested, stopping message processing")
                        break
                    process_task(message)
            else:
                print("No messages received (queue empty)")

        except ClientError as e:
            consecutive_errors += 1
            print(f"✗ AWS Error (#{consecutive_errors}): {e}")

            if consecutive_errors >= max_consecutive_errors:
                print(f"✗ Too many consecutive errors ({max_consecutive_errors}). Exiting.")
                break

            time.sleep(10)  # Wait before retry

        except KeyboardInterrupt:
            print("\nKeyboard interrupt received")
            break

        except Exception as e:
            consecutive_errors += 1
            print(f"✗ Unexpected error (#{consecutive_errors}): {e}")

            if consecutive_errors >= max_consecutive_errors:
                print(f"✗ Too many consecutive errors ({max_consecutive_errors}). Exiting.")
                break

            time.sleep(10)

    print("\nAdapter shutting down gracefully...")


if __name__ == "__main__":
    # Validate configuration
    if not SQS_QUEUE_URL:
        print("ERROR: SQS_QUEUE_URL environment variable not set")
        sys.exit(1)

    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    try:
        main_loop()
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)

    print("Adapter stopped.")
    sys.exit(0)
