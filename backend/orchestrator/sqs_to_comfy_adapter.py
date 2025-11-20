#!/usr/bin/env python3
"""
SQS to ComfyUI Adapter Service

This script runs on the GPU EC2 instance and acts as a bridge between
AWS SQS (task queue) and the local ComfyUI Unified API service.

Architecture:
- Polls SQS queue for new tasks
- Updates DynamoDB task status
- Calls local ComfyUI API at http://localhost:8000
- Polls ComfyUI for completion
- Updates DynamoDB with final results
- Deletes SQS message when done

Requirements:
- ComfyUI Unified API must be running on localhost:8000
- AWS credentials configured (via instance profile or environment)
- Environment variables: SQS_QUEUE_URL, DYNAMODB_TABLE, AWS_REGION
"""

import boto3
import json
import logging
import os
import requests
import time
from datetime import datetime
from typing import Dict, Any, Optional
from botocore.exceptions import ClientError

# ==================== Configuration ====================
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
SQS_QUEUE_URL = os.environ.get("SQS_QUEUE_URL")
DYNAMODB_TABLE = os.environ.get("DYNAMODB_TABLE", "task_store")
COMFYUI_BASE_URL = "http://localhost:8000"
POLL_INTERVAL = 20  # SQS long polling wait time (seconds)
COMFY_POLL_INTERVAL = 5  # ComfyUI status check interval (seconds)
MAX_RETRIES = 3  # Maximum retries for failed operations

# ==================== Logging Setup ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ==================== AWS Clients ====================
sqs_client = boto3.client("sqs", region_name=AWS_REGION)
dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
table = dynamodb.Table(DYNAMODB_TABLE)

# ==================== Helper Functions ====================

def update_task_status(
    task_id: str,
    status: str,
    result_s3_uri: Optional[str] = None,
    error_message: Optional[str] = None,
    comfy_job_id: Optional[str] = None
) -> bool:
    """Update task status in DynamoDB with retry logic."""
    for attempt in range(MAX_RETRIES):
        try:
            update_expression = "SET #status = :status, updated_at = :updated_at"
            expression_values = {
                ":status": status,
                ":updated_at": int(time.time())
            }
            expression_names = {"#status": "status"}

            if result_s3_uri:
                update_expression += ", result_s3_uri = :result_s3_uri"
                expression_values[":result_s3_uri"] = result_s3_uri

            if error_message:
                update_expression += ", error_message = :error_message"
                expression_values[":error_message"] = error_message

            if comfy_job_id:
                update_expression += ", comfy_job_id = :comfy_job_id"
                expression_values[":comfy_job_id"] = comfy_job_id

            table.update_item(
                Key={"task_id": task_id},
                UpdateExpression=update_expression,
                ExpressionAttributeValues=expression_values,
                ExpressionAttributeNames=expression_names
            )

            logger.info(f"Task {task_id} status updated to: {status}")
            return True

        except ClientError as e:
            logger.error(f"DynamoDB update failed (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
            else:
                return False

    return False


def call_comfyui_api(api_path: str, request_body: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Call local ComfyUI API and return response."""
    url = f"{COMFYUI_BASE_URL}{api_path}"

    for attempt in range(MAX_RETRIES):
        try:
            logger.info(f"Calling ComfyUI API: POST {url}")
            logger.info(f"Request body: {json.dumps(request_body, indent=2)}")

            response = requests.post(
                url,
                json=request_body,
                timeout=30
            )
            response.raise_for_status()

            result = response.json()
            logger.info(f"ComfyUI API response: {json.dumps(result, indent=2)}")
            return result

        except requests.exceptions.RequestException as e:
            logger.error(f"ComfyUI API call failed (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
            else:
                return None

    return None


def poll_comfyui_status(comfy_job_id: str, timeout: int = 600) -> Optional[Dict[str, Any]]:
    """
    Poll ComfyUI for job completion.

    Args:
        comfy_job_id: ComfyUI job ID to poll
        timeout: Maximum time to wait in seconds (default: 10 minutes)

    Returns:
        Final job status dict or None if timeout/error
    """
    url = f"{COMFYUI_BASE_URL}/api/v1/jobs/{comfy_job_id}"
    start_time = time.time()

    while True:
        elapsed = time.time() - start_time
        if elapsed > timeout:
            logger.error(f"Timeout waiting for ComfyUI job {comfy_job_id}")
            return None

        try:
            logger.info(f"Polling ComfyUI status: GET {url}")
            response = requests.get(url, timeout=10)
            response.raise_for_status()

            status_data = response.json()
            job_status = status_data.get("status")

            logger.info(f"ComfyUI job {comfy_job_id} status: {job_status}")

            if job_status in ["completed", "failed"]:
                return status_data

            # Still processing, wait before next poll
            time.sleep(COMFY_POLL_INTERVAL)

        except requests.exceptions.RequestException as e:
            logger.error(f"Error polling ComfyUI status: {e}")
            time.sleep(COMFY_POLL_INTERVAL)
            continue

    return None


def process_task(message: Dict[str, Any]) -> bool:
    """
    Process a single task from SQS.

    Returns:
        True if task was successfully processed (and message should be deleted)
        False if task failed (message should be retried)
    """
    try:
        # Parse SQS message body
        body = json.loads(message["Body"])
        task_id = body.get("task_id")
        api_path = body.get("api_path")
        request_body = body.get("request_body")

        if not all([task_id, api_path, request_body]):
            logger.error(f"Invalid message format: {body}")
            return True  # Delete malformed message

        logger.info(f"Processing task {task_id}: {api_path}")

        # Step 1: Update status to PROCESSING
        if not update_task_status(task_id, "processing"):
            logger.error(f"Failed to update task {task_id} to processing")
            return False  # Retry later

        # Step 2: Call ComfyUI API
        comfy_response = call_comfyui_api(api_path, request_body)
        if not comfy_response:
            # ComfyUI API call failed
            update_task_status(
                task_id,
                "failed",
                error_message="Failed to call ComfyUI API"
            )
            return True  # Delete message (permanent failure)

        # Step 3: Extract ComfyUI job ID
        comfy_job_id = comfy_response.get("job_id")
        if not comfy_job_id:
            logger.error(f"No job_id in ComfyUI response: {comfy_response}")
            update_task_status(
                task_id,
                "failed",
                error_message="Invalid ComfyUI response: no job_id"
            )
            return True  # Delete message

        # Update with ComfyUI job ID
        update_task_status(task_id, "processing", comfy_job_id=comfy_job_id)

        # Step 4: Poll ComfyUI until completion
        logger.info(f"Waiting for ComfyUI job {comfy_job_id} to complete...")
        final_status = poll_comfyui_status(comfy_job_id)

        if not final_status:
            # Timeout or error
            update_task_status(
                task_id,
                "failed",
                error_message="Timeout waiting for ComfyUI job completion"
            )
            return True  # Delete message

        # Step 5: Update final status in DynamoDB
        comfy_status = final_status.get("status")

        if comfy_status == "completed":
            result_s3_uri = final_status.get("result_s3_uri")
            if result_s3_uri:
                update_task_status(
                    task_id,
                    "completed",
                    result_s3_uri=result_s3_uri
                )
                logger.info(f"Task {task_id} completed successfully: {result_s3_uri}")
            else:
                update_task_status(
                    task_id,
                    "failed",
                    error_message="ComfyUI completed but no result_s3_uri"
                )
                logger.error(f"Task {task_id} completed but no result")

        elif comfy_status == "failed":
            error_message = final_status.get("error", "Unknown ComfyUI error")
            update_task_status(
                task_id,
                "failed",
                error_message=error_message
            )
            logger.error(f"Task {task_id} failed: {error_message}")

        return True  # Task processed, delete message

    except Exception as e:
        logger.error(f"Unexpected error processing task: {e}", exc_info=True)
        return False  # Retry later


def delete_message(receipt_handle: str) -> bool:
    """Delete processed message from SQS."""
    try:
        sqs_client.delete_message(
            QueueUrl=SQS_QUEUE_URL,
            ReceiptHandle=receipt_handle
        )
        logger.info("Message deleted from SQS")
        return True
    except ClientError as e:
        logger.error(f"Failed to delete SQS message: {e}")
        return False


def main():
    """Main adapter loop."""
    logger.info("=" * 60)
    logger.info("SQS to ComfyUI Adapter Service Starting")
    logger.info("=" * 60)
    logger.info(f"AWS Region: {AWS_REGION}")
    logger.info(f"SQS Queue URL: {SQS_QUEUE_URL}")
    logger.info(f"DynamoDB Table: {DYNAMODB_TABLE}")
    logger.info(f"ComfyUI Base URL: {COMFYUI_BASE_URL}")
    logger.info("=" * 60)

    # Validate environment
    if not SQS_QUEUE_URL:
        logger.error("SQS_QUEUE_URL environment variable not set!")
        return

    # Check ComfyUI API health
    try:
        response = requests.get(f"{COMFYUI_BASE_URL}/health", timeout=5)
        if response.status_code == 200:
            logger.info("ComfyUI API is healthy")
        else:
            logger.warning(f"ComfyUI API health check returned: {response.status_code}")
    except Exception as e:
        logger.warning(f"ComfyUI API health check failed: {e}")
        logger.warning("Continuing anyway - will retry on actual requests")

    logger.info("Starting message polling loop...")

    # Main polling loop
    while True:
        try:
            # Long poll SQS for messages
            response = sqs_client.receive_message(
                QueueUrl=SQS_QUEUE_URL,
                MaxNumberOfMessages=1,  # Process one at a time
                WaitTimeSeconds=POLL_INTERVAL,  # Long polling
                AttributeNames=["All"],
                MessageAttributeNames=["All"]
            )

            messages = response.get("Messages", [])

            if not messages:
                logger.debug("No messages in queue, continuing poll...")
                continue

            # Process message
            message = messages[0]
            receipt_handle = message["ReceiptHandle"]

            logger.info(f"Received message from SQS")

            # Process the task
            success = process_task(message)

            # Delete message if successfully processed
            if success:
                delete_message(receipt_handle)
            else:
                logger.warning("Task processing failed, message will be retried")
                # Message will become visible again after visibility timeout

        except ClientError as e:
            logger.error(f"SQS error: {e}")
            time.sleep(5)  # Wait before retrying

        except KeyboardInterrupt:
            logger.info("Received shutdown signal, exiting...")
            break

        except Exception as e:
            logger.error(f"Unexpected error in main loop: {e}", exc_info=True)
            time.sleep(5)  # Wait before retrying


if __name__ == "__main__":
    main()
