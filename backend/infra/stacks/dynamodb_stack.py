"""
DynamoDB Stack - Task State Management

Creates:
- Table: task_store
- Primary Key: task_id (String)
- GSI: status-created_at-index (for querying by status)
- TTL: Optional auto-deletion after 30 days
"""

from aws_cdk import (
    Stack,
    RemovalPolicy,
    CfnOutput,
)
from aws_cdk import aws_dynamodb as dynamodb
from constructs import Construct


class DynamoDbStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        table_name: str,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # DynamoDB Table
        self.table = dynamodb.Table(
            self,
            "TaskStore",
            table_name=table_name,
            # Primary Key
            partition_key=dynamodb.Attribute(
                name="task_id",
                type=dynamodb.AttributeType.STRING
            ),
            # Billing Mode
            # PAY_PER_REQUEST: No capacity planning needed, pay per request
            # Better for unpredictable workloads
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            # Removal Policy
            removal_policy=RemovalPolicy.RETAIN,  # Keep data even if stack is deleted
            # Point-in-time recovery
            point_in_time_recovery=True,
            # Time to Live (TTL)
            # Auto-delete items after 30 days (optional)
            time_to_live_attribute="ttl",
        )

        # Global Secondary Index (GSI) for querying by status
        self.table.add_global_secondary_index(
            index_name="status-created_at-index",
            partition_key=dynamodb.Attribute(
                name="status",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="created_at",
                type=dynamodb.AttributeType.NUMBER
            ),
            # Project all attributes to the index
            projection_type=dynamodb.ProjectionType.ALL,
        )

        # Outputs
        CfnOutput(
            self,
            "TableName",
            value=self.table.table_name,
            description="Name of the DynamoDB table",
            export_name=f"{construct_id}-TableName"
        )

        CfnOutput(
            self,
            "TableArn",
            value=self.table.table_arn,
            description="ARN of the DynamoDB table",
            export_name=f"{construct_id}-TableArn"
        )

        CfnOutput(
            self,
            "TableStreamArn",
            value=self.table.table_stream_arn or "N/A",
            description="ARN of the DynamoDB table stream (if enabled)",
            export_name=f"{construct_id}-TableStreamArn"
        )
