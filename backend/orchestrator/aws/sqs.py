"""
SQS helper functions for message queue operations.
"""

import boto3
from typing import Dict, Any, Optional, List
from botocore.exceptions import ClientError


def send_message(
    queue_url: str,
    message_body: str,
    region: str,
    message_attributes: Optional[Dict[str, Any]] = None,
    delay_seconds: int = 0
) -> Dict[str, Any]:
    """
    Send a message to an SQS queue.

    Args:
        queue_url: The URL of the SQS queue
        message_body: The message content (typically JSON string)
        region: AWS region name
        message_attributes: Optional message attributes
        delay_seconds: Delay before message becomes visible (0-900 seconds)

    Returns:
        Dictionary containing MessageId and other response data

    Raises:
        ClientError: If AWS API call fails
    """
    sqs_client = boto3.client('sqs', region_name=region)

    try:
        params = {
            'QueueUrl': queue_url,
            'MessageBody': message_body,
            'DelaySeconds': delay_seconds
        }

        if message_attributes:
            params['MessageAttributes'] = message_attributes

        response = sqs_client.send_message(**params)

        result = {
            'MessageId': response['MessageId'],
            'MD5OfMessageBody': response['MD5OfMessageBody']
        }

        print(f"Message sent to queue. MessageId: {result['MessageId']}")
        return result

    except ClientError as e:
        print(f"Error sending message to SQS: {e}")
        raise


def receive_messages(
    queue_url: str,
    region: str,
    max_messages: int = 1,
    wait_time_seconds: int = 20,
    visibility_timeout: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Receive messages from an SQS queue using long polling.

    Args:
        queue_url: The URL of the SQS queue
        region: AWS region name
        max_messages: Maximum number of messages to retrieve (1-10)
        wait_time_seconds: Long polling wait time (0-20 seconds, 20 recommended)
        visibility_timeout: Override queue's visibility timeout (in seconds)

    Returns:
        List of message dictionaries

    Raises:
        ClientError: If AWS API call fails
    """
    sqs_client = boto3.client('sqs', region_name=region)

    try:
        params = {
            'QueueUrl': queue_url,
            'MaxNumberOfMessages': max_messages,
            'WaitTimeSeconds': wait_time_seconds,
            'AttributeNames': ['All'],
            'MessageAttributeNames': ['All']
        }

        if visibility_timeout is not None:
            params['VisibilityTimeout'] = visibility_timeout

        response = sqs_client.receive_message(**params)

        messages = response.get('Messages', [])
        print(f"Received {len(messages)} message(s) from queue")

        return messages

    except ClientError as e:
        print(f"Error receiving messages from SQS: {e}")
        raise


def delete_message(queue_url: str, receipt_handle: str, region: str) -> None:
    """
    Delete a message from an SQS queue.

    This should be called after successfully processing a message.

    Args:
        queue_url: The URL of the SQS queue
        receipt_handle: The receipt handle of the message to delete
        region: AWS region name

    Raises:
        ClientError: If AWS API call fails
    """
    sqs_client = boto3.client('sqs', region_name=region)

    try:
        sqs_client.delete_message(
            QueueUrl=queue_url,
            ReceiptHandle=receipt_handle
        )
        print(f"Message deleted from queue")

    except ClientError as e:
        print(f"Error deleting message from SQS: {e}")
        raise


def change_message_visibility(
    queue_url: str,
    receipt_handle: str,
    visibility_timeout: int,
    region: str
) -> None:
    """
    Change the visibility timeout of a message.

    Useful for extending processing time or making a message immediately visible again.

    Args:
        queue_url: The URL of the SQS queue
        receipt_handle: The receipt handle of the message
        visibility_timeout: New visibility timeout in seconds (0 to make immediately visible)
        region: AWS region name

    Raises:
        ClientError: If AWS API call fails
    """
    sqs_client = boto3.client('sqs', region_name=region)

    try:
        sqs_client.change_message_visibility(
            QueueUrl=queue_url,
            ReceiptHandle=receipt_handle,
            VisibilityTimeout=visibility_timeout
        )
        print(f"Message visibility timeout changed to {visibility_timeout} seconds")

    except ClientError as e:
        print(f"Error changing message visibility: {e}")
        raise


def get_queue_attributes(queue_url: str, region: str) -> Dict[str, Any]:
    """
    Get attributes of an SQS queue.

    Args:
        queue_url: The URL of the SQS queue
        region: AWS region name

    Returns:
        Dictionary of queue attributes

    Raises:
        ClientError: If AWS API call fails
    """
    sqs_client = boto3.client('sqs', region_name=region)

    try:
        response = sqs_client.get_queue_attributes(
            QueueUrl=queue_url,
            AttributeNames=['All']
        )

        return response.get('Attributes', {})

    except ClientError as e:
        print(f"Error getting queue attributes: {e}")
        raise


def purge_queue(queue_url: str, region: str) -> None:
    """
    Delete all messages from an SQS queue.

    WARNING: This is irreversible and should only be used for testing/cleanup.

    Args:
        queue_url: The URL of the SQS queue
        region: AWS region name

    Raises:
        ClientError: If AWS API call fails
    """
    sqs_client = boto3.client('sqs', region_name=region)

    try:
        sqs_client.purge_queue(QueueUrl=queue_url)
        print(f"Queue purged successfully")

    except ClientError as e:
        print(f"Error purging queue: {e}")
        raise
