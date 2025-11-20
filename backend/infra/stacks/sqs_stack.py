"""
SQS Stack - Message Queue for GPU Task Orchestration

Creates:
- Main queue: gpu_tasks_queue
- Dead Letter Queue (DLQ): gpu_tasks_queue_dlq
"""

from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    CfnOutput,
)
from aws_cdk import aws_sqs as sqs
from constructs import Construct


class SqsStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        queue_name: str,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Dead Letter Queue
        self.dlq = sqs.Queue(
            self,
            "GpuTasksDLQ",
            queue_name=f"{queue_name}_dlq",
            retention_period=Duration.days(14),  # Keep failed messages for 14 days
            removal_policy=RemovalPolicy.RETAIN,  # Don't delete DLQ on stack delete
        )

        # Main Queue
        self.queue = sqs.Queue(
            self,
            "GpuTasksQueue",
            queue_name=queue_name,
            # Visibility timeout: how long a message is invisible after being received
            # Set to 5 minutes to allow task processing
            visibility_timeout=Duration.seconds(300),
            # Receive message wait time (long polling)
            # Set to 20 seconds for efficient polling
            receive_message_wait_time=Duration.seconds(20),
            # Message retention: how long messages stay in queue
            retention_period=Duration.days(1),
            # Dead Letter Queue configuration
            dead_letter_queue=sqs.DeadLetterQueue(
                max_receive_count=3,  # Retry 3 times before sending to DLQ
                queue=self.dlq
            ),
            # Removal policy
            removal_policy=RemovalPolicy.DESTROY,  # Can delete main queue
        )

        # Outputs
        CfnOutput(
            self,
            "QueueUrl",
            value=self.queue.queue_url,
            description="URL of the GPU tasks queue",
            export_name=f"{construct_id}-QueueUrl"
        )

        CfnOutput(
            self,
            "QueueArn",
            value=self.queue.queue_arn,
            description="ARN of the GPU tasks queue",
            export_name=f"{construct_id}-QueueArn"
        )

        CfnOutput(
            self,
            "DLQUrl",
            value=self.dlq.queue_url,
            description="URL of the Dead Letter Queue",
            export_name=f"{construct_id}-DLQUrl"
        )
