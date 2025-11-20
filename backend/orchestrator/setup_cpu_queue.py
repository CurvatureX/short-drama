#!/usr/bin/env python3
"""
Setup script for CPU task queue infrastructure

Creates SQS queue for CPU-bound tasks (face masking, face swapping).
Reuses existing DynamoDB table (task_store).
"""

import boto3
import json
import sys
from botocore.exceptions import ClientError

# Configuration
AWS_REGION = 'us-east-1'
QUEUE_NAME = 'cpu_tasks_queue'
DLQ_NAME = 'cpu_tasks_dlq'

# SQS Configuration
VISIBILITY_TIMEOUT = 600  # 10 minutes (CPU tasks can be slower)
MESSAGE_RETENTION = 1209600  # 14 days
MAX_RECEIVE_COUNT = 3  # Retry 3 times before moving to DLQ


def create_dead_letter_queue(sqs_client):
    """Create dead letter queue for failed tasks"""
    print(f"\n1. Creating dead letter queue: {DLQ_NAME}")

    try:
        response = sqs_client.create_queue(
            QueueName=DLQ_NAME,
            Attributes={
                'MessageRetentionPeriod': str(MESSAGE_RETENTION),
                'VisibilityTimeout': str(VISIBILITY_TIMEOUT)
            }
        )

        dlq_url = response['QueueUrl']
        print(f"✓ Dead letter queue created: {dlq_url}")

        # Get queue ARN
        attrs = sqs_client.get_queue_attributes(
            QueueUrl=dlq_url,
            AttributeNames=['QueueArn']
        )
        dlq_arn = attrs['Attributes']['QueueArn']

        return dlq_url, dlq_arn

    except ClientError as e:
        if e.response['Error']['Code'] == 'QueueAlreadyExists':
            print(f"⚠ Queue already exists: {DLQ_NAME}")
            # Get existing queue
            response = sqs_client.get_queue_url(QueueName=DLQ_NAME)
            dlq_url = response['QueueUrl']

            attrs = sqs_client.get_queue_attributes(
                QueueUrl=dlq_url,
                AttributeNames=['QueueArn']
            )
            dlq_arn = attrs['Attributes']['QueueArn']

            return dlq_url, dlq_arn
        else:
            raise


def create_cpu_task_queue(sqs_client, dlq_arn):
    """Create main CPU task queue with DLQ"""
    print(f"\n2. Creating CPU task queue: {QUEUE_NAME}")

    redrive_policy = {
        'deadLetterTargetArn': dlq_arn,
        'maxReceiveCount': MAX_RECEIVE_COUNT
    }

    try:
        response = sqs_client.create_queue(
            QueueName=QUEUE_NAME,
            Attributes={
                'VisibilityTimeout': str(VISIBILITY_TIMEOUT),
                'MessageRetentionPeriod': str(MESSAGE_RETENTION),
                'ReceiveMessageWaitTimeSeconds': '20',  # Enable long polling
                'RedrivePolicy': json.dumps(redrive_policy)
            }
        )

        queue_url = response['QueueUrl']
        print(f"✓ CPU task queue created: {queue_url}")

        # Get queue ARN
        attrs = sqs_client.get_queue_attributes(
            QueueUrl=queue_url,
            AttributeNames=['QueueArn']
        )
        queue_arn = attrs['Attributes']['QueueArn']

        return queue_url, queue_arn

    except ClientError as e:
        if e.response['Error']['Code'] == 'QueueAlreadyExists':
            print(f"⚠ Queue already exists: {QUEUE_NAME}")
            # Get existing queue
            response = sqs_client.get_queue_url(QueueName=QUEUE_NAME)
            queue_url = response['QueueUrl']

            attrs = sqs_client.get_queue_attributes(
                QueueUrl=queue_url,
                AttributeNames=['QueueArn']
            )
            queue_arn = attrs['Attributes']['QueueArn']

            return queue_url, queue_arn
        else:
            raise


def verify_dynamodb_table(dynamodb_client, table_name='task_store'):
    """Verify DynamoDB table exists"""
    print(f"\n3. Verifying DynamoDB table: {table_name}")

    try:
        response = dynamodb_client.describe_table(TableName=table_name)
        table_status = response['Table']['TableStatus']

        print(f"✓ DynamoDB table exists: {table_name}")
        print(f"  Status: {table_status}")

        return True

    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            print(f"✗ DynamoDB table not found: {table_name}")
            print(f"  Please create the table first using the GPU task setup")
            return False
        else:
            raise


def print_configuration(queue_url, queue_arn, dlq_url, dlq_arn):
    """Print configuration for services"""
    print("\n" + "="*60)
    print("CPU Task Queue Setup Complete!")
    print("="*60)

    print("\nQueue URLs:")
    print(f"  Main Queue: {queue_url}")
    print(f"  DLQ: {dlq_url}")

    print("\nQueue ARNs:")
    print(f"  Main Queue: {queue_arn}")
    print(f"  DLQ: {dlq_arn}")

    print("\nConfiguration for orchestrator:")
    print(f"  export CPU_QUEUE_URL='{queue_url}'")
    print(f"  export DYNAMODB_TABLE='task_store'")
    print(f"  export AWS_REGION='{AWS_REGION}'")

    print("\nConfiguration for paid-api-service SQS adapter:")
    print(f"  export CPU_QUEUE_URL='{queue_url}'")
    print(f"  export DYNAMODB_TABLE='task_store'")
    print(f"  export AWS_REGION='{AWS_REGION}'")
    print(f"  export PAID_API_URL='http://localhost:8000'")

    print("\nNext steps:")
    print("  1. Update orchestrator environment variables")
    print("  2. Deploy paid-api-service to CPU instance")
    print("  3. Start SQS adapter on CPU instance")
    print("  4. Test with: python test_orchestrator.py")


def main():
    """Main setup function"""
    print("="*60)
    print("CPU Task Queue Infrastructure Setup")
    print("="*60)
    print(f"Region: {AWS_REGION}")

    try:
        # Initialize AWS clients
        sqs_client = boto3.client('sqs', region_name=AWS_REGION)
        dynamodb_client = boto3.client('dynamodb', region_name=AWS_REGION)

        # Step 1: Create DLQ
        dlq_url, dlq_arn = create_dead_letter_queue(sqs_client)

        # Step 2: Create main queue
        queue_url, queue_arn = create_cpu_task_queue(sqs_client, dlq_arn)

        # Step 3: Verify DynamoDB table
        if not verify_dynamodb_table(dynamodb_client):
            print("\n✗ Setup incomplete: DynamoDB table missing")
            sys.exit(1)

        # Print configuration
        print_configuration(queue_url, queue_arn, dlq_url, dlq_arn)

        print("\n✓ Setup completed successfully!")
        sys.exit(0)

    except Exception as e:
        print(f"\n✗ Setup failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
