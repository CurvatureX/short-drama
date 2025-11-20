"""
IAM Stack - Identity and Access Management

Creates IAM roles for:
1. Orchestrator (Fargate task)
2. GPU Instance (EC2)
3. Lambda (Auto-shutdown)
"""

from aws_cdk import (
    Stack,
    CfnOutput,
)
from aws_cdk import aws_iam as iam
from constructs import Construct


class IamStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        queue_arn: str,
        dlq_arn: str,
        table_arn: str,
        table_index_arn: str,
        gpu_instance_id: str,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ===================================================================
        # 1. Orchestrator Task Role (Fargate/ECS)
        # ===================================================================

        self.orchestrator_role = iam.Role(
            self,
            "OrchestratorTaskRole",
            role_name="gpu-orchestrator-task-role",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            description="IAM role for GPU Orchestrator Fargate task",
        )

        # SQS permissions (send messages to both GPU and CPU queues)
        self.orchestrator_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "sqs:SendMessage",
                    "sqs:GetQueueAttributes",
                    "sqs:GetQueueUrl",
                ],
                resources=[
                    queue_arn,  # GPU tasks queue
                    f"arn:aws:sqs:{self.region}:{self.account}:cpu_tasks_queue",  # CPU tasks queue
                ]
            )
        )

        # DynamoDB permissions (read/write tasks)
        self.orchestrator_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "dynamodb:PutItem",
                    "dynamodb:GetItem",
                    "dynamodb:UpdateItem",
                    "dynamodb:Query",
                    "dynamodb:DescribeTable",  # For health checks
                ],
                resources=[table_arn, table_index_arn]
            )
        )

        # EC2 permissions (describe and start GPU instance)
        self.orchestrator_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "ec2:DescribeInstances",
                ],
                resources=["*"],  # DescribeInstances doesn't support resource-level permissions
            )
        )

        self.orchestrator_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "ec2:StartInstances",
                ],
                resources=[f"arn:aws:ec2:{self.region}:{self.account}:instance/{gpu_instance_id}"],
                conditions={
                    "StringEquals": {
                        "ec2:ResourceTag/Purpose": "GPU-ComfyUI"
                    }
                }
            )
        )

        # ===================================================================
        # 2. GPU Instance Role (EC2)
        # ===================================================================

        self.gpu_instance_role = iam.Role(
            self,
            "GpuInstanceRole",
            role_name="gpu-instance-role",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            description="IAM role for GPU EC2 instance running SQS adapter",
        )

        # SQS permissions (receive, delete, change visibility)
        self.gpu_instance_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "sqs:ReceiveMessage",
                    "sqs:DeleteMessage",
                    "sqs:ChangeMessageVisibility",
                    "sqs:GetQueueAttributes",
                    "sqs:GetQueueUrl",
                ],
                resources=[queue_arn]
            )
        )

        # DynamoDB permissions (read/write task status)
        self.gpu_instance_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "dynamodb:GetItem",
                    "dynamodb:UpdateItem",
                    "dynamodb:PutItem",
                ],
                resources=[table_arn]
            )
        )

        # S3 permissions (upload results, download inputs)
        # Note: Replace with specific bucket ARN in production
        self.gpu_instance_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "s3:GetObject",
                    "s3:PutObject",
                    "s3:PutObjectAcl",
                ],
                resources=["arn:aws:s3:::*/*"]  # TODO: Restrict to specific bucket
            )
        )

        # Create Instance Profile for EC2
        self.gpu_instance_profile = iam.CfnInstanceProfile(
            self,
            "GpuInstanceProfile",
            instance_profile_name="gpu-instance-profile",
            roles=[self.gpu_instance_role.role_name]
        )

        # ===================================================================
        # 3. Lambda Execution Role (Auto-shutdown)
        # ===================================================================

        self.lambda_role = iam.Role(
            self,
            "LambdaShutdownRole",
            role_name="lambda-gpu-shutdown-role",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description="IAM role for GPU auto-shutdown Lambda function",
            managed_policies=[
                # Basic Lambda execution (CloudWatch Logs)
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ]
        )

        # EC2 permissions (describe and stop GPU instance)
        self.lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "ec2:DescribeInstances",
                ],
                resources=["*"],  # DescribeInstances doesn't support resource-level permissions
            )
        )

        self.lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "ec2:StopInstances",
                ],
                resources=[f"arn:aws:ec2:{self.region}:{self.account}:instance/{gpu_instance_id}"],
                conditions={
                    "StringEquals": {
                        "ec2:ResourceTag/Purpose": "GPU-ComfyUI"
                    }
                }
            )
        )

        # ===================================================================
        # Outputs
        # ===================================================================

        CfnOutput(
            self,
            "OrchestratorRoleArn",
            value=self.orchestrator_role.role_arn,
            description="ARN of the Orchestrator task role",
            export_name=f"{construct_id}-OrchestratorRoleArn"
        )

        CfnOutput(
            self,
            "GpuInstanceRoleArn",
            value=self.gpu_instance_role.role_arn,
            description="ARN of the GPU instance role",
            export_name=f"{construct_id}-GpuInstanceRoleArn"
        )

        CfnOutput(
            self,
            "GpuInstanceProfileArn",
            value=self.gpu_instance_profile.attr_arn,
            description="ARN of the GPU instance profile",
            export_name=f"{construct_id}-GpuInstanceProfileArn"
        )

        CfnOutput(
            self,
            "LambdaRoleArn",
            value=self.lambda_role.role_arn,
            description="ARN of the Lambda shutdown role",
            export_name=f"{construct_id}-LambdaRoleArn"
        )
