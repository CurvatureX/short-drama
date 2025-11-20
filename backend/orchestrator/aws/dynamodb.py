"""
DynamoDB helper functions for task state management.
"""

import boto3
import time
from typing import Dict, Any, Optional
from botocore.exceptions import ClientError


def create_task(
    table_name: str,
    task_id: str,
    job_type: str,
    region: str,
    initial_status: str = 'pending'
) -> None:
    """
    Create a new task record in DynamoDB.

    Args:
        table_name: Name of the DynamoDB table
        task_id: Unique task identifier (UUID)
        job_type: Type of job (e.g., "/api/v1/camera-angle/jobs")
        region: AWS region name
        initial_status: Initial status (default: 'pending')

    Raises:
        ClientError: If AWS API call fails
    """
    dynamodb = boto3.resource('dynamodb', region_name=region)
    table = dynamodb.Table(table_name)

    try:
        current_time = int(time.time())

        table.put_item(
            Item={
                'task_id': task_id,
                'status': initial_status,
                'job_type': job_type,
                'created_at': current_time,
                'updated_at': current_time
            },
            ConditionExpression='attribute_not_exists(task_id)'  # Prevent overwrites
        )

        print(f"Task {task_id} created with status: {initial_status}")

    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            print(f"Task {task_id} already exists")
            raise ValueError(f"Task {task_id} already exists")
        else:
            print(f"Error creating task in DynamoDB: {e}")
            raise


def update_task_status(
    table_name: str,
    task_id: str,
    status: str,
    region: str,
    result_s3_uri: Optional[str] = None,
    error_message: Optional[str] = None,
    comfy_job_id: Optional[str] = None
) -> None:
    """
    Update task status and optional fields.

    Args:
        table_name: Name of the DynamoDB table
        task_id: Unique task identifier
        status: New status ('pending', 'processing', 'completed', 'failed')
        region: AWS region name
        result_s3_uri: S3 URI of the result (for completed tasks)
        error_message: Error message (for failed tasks)
        comfy_job_id: ComfyUI internal job ID

    Raises:
        ClientError: If AWS API call fails
    """
    dynamodb = boto3.resource('dynamodb', region_name=region)
    table = dynamodb.Table(table_name)

    try:
        current_time = int(time.time())

        # Build update expression dynamically
        update_expr = "SET #status = :status, updated_at = :updated_at"
        expr_attr_names = {'#status': 'status'}
        expr_attr_values = {
            ':status': status,
            ':updated_at': current_time
        }

        if result_s3_uri is not None:
            update_expr += ", result_s3_uri = :result_s3_uri"
            expr_attr_values[':result_s3_uri'] = result_s3_uri

        if error_message is not None:
            update_expr += ", error_message = :error_message"
            expr_attr_values[':error_message'] = error_message

        if comfy_job_id is not None:
            update_expr += ", comfy_job_id = :comfy_job_id"
            expr_attr_values[':comfy_job_id'] = comfy_job_id

        table.update_item(
            Key={'task_id': task_id},
            UpdateExpression=update_expr,
            ExpressionAttributeNames=expr_attr_names,
            ExpressionAttributeValues=expr_attr_values
        )

        print(f"Task {task_id} updated to status: {status}")

    except ClientError as e:
        print(f"Error updating task in DynamoDB: {e}")
        raise


def get_task_status(table_name: str, task_id: str, region: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve task information from DynamoDB.

    Args:
        table_name: Name of the DynamoDB table
        task_id: Unique task identifier
        region: AWS region name

    Returns:
        Dictionary containing task information, or None if not found

    Raises:
        ClientError: If AWS API call fails
    """
    dynamodb = boto3.resource('dynamodb', region_name=region)
    table = dynamodb.Table(table_name)

    try:
        response = table.get_item(Key={'task_id': task_id})

        item = response.get('Item')
        if item:
            print(f"Retrieved task {task_id} with status: {item.get('status')}")
        else:
            print(f"Task {task_id} not found")

        return item

    except ClientError as e:
        print(f"Error retrieving task from DynamoDB: {e}")
        raise


def query_tasks_by_status(
    table_name: str,
    status: str,
    region: str,
    limit: int = 100
) -> list:
    """
    Query tasks by status using a GSI.

    Note: This requires a Global Secondary Index named 'status-created_at-index'
    with partition key 'status' and sort key 'created_at'.

    Args:
        table_name: Name of the DynamoDB table
        status: Status to filter by
        region: AWS region name
        limit: Maximum number of items to return

    Returns:
        List of task items

    Raises:
        ClientError: If AWS API call fails
    """
    dynamodb = boto3.resource('dynamodb', region_name=region)
    table = dynamodb.Table(table_name)

    try:
        response = table.query(
            IndexName='status-created_at-index',
            KeyConditionExpression='#status = :status',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={':status': status},
            Limit=limit,
            ScanIndexForward=False  # Sort by created_at descending (newest first)
        )

        items = response.get('Items', [])
        print(f"Found {len(items)} task(s) with status: {status}")

        return items

    except ClientError as e:
        print(f"Error querying tasks by status: {e}")
        raise


def delete_task(table_name: str, task_id: str, region: str) -> None:
    """
    Delete a task from DynamoDB.

    Args:
        table_name: Name of the DynamoDB table
        task_id: Unique task identifier
        region: AWS region name

    Raises:
        ClientError: If AWS API call fails
    """
    dynamodb = boto3.resource('dynamodb', region_name=region)
    table = dynamodb.Table(table_name)

    try:
        table.delete_item(Key={'task_id': task_id})
        print(f"Task {task_id} deleted")

    except ClientError as e:
        print(f"Error deleting task from DynamoDB: {e}")
        raise


def batch_get_tasks(
    table_name: str,
    task_ids: list,
    region: str
) -> list:
    """
    Retrieve multiple tasks in a single batch operation.

    Args:
        table_name: Name of the DynamoDB table
        task_ids: List of task IDs to retrieve
        region: AWS region name

    Returns:
        List of task items (may be fewer than requested if some don't exist)

    Raises:
        ClientError: If AWS API call fails
    """
    dynamodb = boto3.resource('dynamodb', region_name=region)

    try:
        keys = [{'task_id': task_id} for task_id in task_ids]

        response = dynamodb.batch_get_item(
            RequestItems={
                table_name: {
                    'Keys': keys
                }
            }
        )

        items = response.get('Responses', {}).get(table_name, [])
        print(f"Retrieved {len(items)} task(s) from batch get")

        return items

    except ClientError as e:
        print(f"Error in batch get tasks: {e}")
        raise
