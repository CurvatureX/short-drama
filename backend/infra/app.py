#!/usr/bin/env python3
"""
AWS CDK App for GPU Orchestration System

This CDK app defines all AWS infrastructure needed for the
cost-optimized GPU task orchestration system.

Infrastructure includes:
- SQS Queue with DLQ
- DynamoDB Table with GSI
- IAM Roles (Orchestrator, GPU Instance, Lambda)
- Lambda Function (Auto-shutdown)
- CloudWatch Alarm (30-min idle detection)
"""

import os
from aws_cdk import (
    App,
    Environment,
    Tags,
)
from stacks.sqs_stack import SqsStack
from stacks.dynamodb_stack import DynamoDbStack
from stacks.iam_stack import IamStack
from stacks.lambda_stack import LambdaStack
from stacks.alarm_stack import AlarmStack
from stacks.infrastructure_stack import InfrastructureStack
from stacks.orchestrator_service_stack import OrchestratorServiceStack
from stacks.canvas_service_stack import CanvasServiceStack

app = App()

# Get configuration from environment or use defaults
account = os.environ.get('CDK_DEFAULT_ACCOUNT', os.environ.get('AWS_ACCOUNT_ID'))
region = os.environ.get('CDK_DEFAULT_REGION', 'us-east-1')

# Define environment
env = Environment(account=account, region=region)

# Configuration
gpu_instance_id = app.node.try_get_context('gpu_instance_id') or os.environ.get('GPU_INSTANCE_ID', 'i-0f0f6fd680921de5f')
project_name = 'gpu-orchestrator'

# Canvas Service configuration from environment
s3_bucket = os.environ.get('S3_BUCKET_NAME', 'short-drama-assets')
supabase_url = os.environ.get('SUPABASE_URL', '')
supabase_key = os.environ.get('SUPABASE_SECRET_KEY', '')
cloudfront_domain = os.environ.get('CLOUDFRONT_DOMAIN', 'https://d3bg7alr1qwred.cloudfront.net')

# CORS configuration - comma-separated list of allowed origins
cors_origins = os.environ.get('CORS_ORIGINS', 'https://canvas.starmates.ai,https://www.starmates.ai')

# Stack 1: SQS Queue with DLQ
sqs_stack = SqsStack(
    app,
    f"{project_name}-sqs",
    queue_name="gpu_tasks_queue",
    env=env,
    description="SQS Queue for GPU task orchestration"
)

# Stack 2: DynamoDB Table
dynamodb_stack = DynamoDbStack(
    app,
    f"{project_name}-dynamodb",
    table_name="task_store",
    env=env,
    description="DynamoDB table for task state management"
)

# Stack 3: IAM Roles
iam_stack = IamStack(
    app,
    f"{project_name}-iam",
    queue_arn=sqs_stack.queue.queue_arn,
    dlq_arn=sqs_stack.dlq.queue_arn,
    table_arn=dynamodb_stack.table.table_arn,
    table_index_arn=f"{dynamodb_stack.table.table_arn}/index/*",
    gpu_instance_id=gpu_instance_id,
    env=env,
    description="IAM roles for orchestrator, GPU instance, and Lambda"
)

# Stack 4: Lambda Function (Auto-shutdown)
lambda_stack = LambdaStack(
    app,
    f"{project_name}-lambda",
    gpu_instance_id=gpu_instance_id,
    lambda_role=iam_stack.lambda_role,
    env=env,
    description="Lambda function for GPU auto-shutdown"
)

# Stack 5: CloudWatch Alarm (30-min idle detection)
alarm_stack = AlarmStack(
    app,
    f"{project_name}-alarm",
    queue=sqs_stack.queue,
    lambda_function=lambda_stack.shutdown_function,
    env=env,
    description="CloudWatch alarm for 30-minute idle detection"
)

# Stack 6: Infrastructure (VPC, ALB, ECS Cluster, Security Groups)
infrastructure_stack = InfrastructureStack(
    app,
    f"{project_name}-infrastructure",
    env=env,
    description="Shared infrastructure for backend services (VPC, ALB, ECS Cluster)"
)

# Stack 7: Orchestrator Service
orchestrator_service_stack = OrchestratorServiceStack(
    app,
    f"{project_name}-orchestrator-service",
    vpc=infrastructure_stack.vpc,
    cluster=infrastructure_stack.cluster,
    target_group=infrastructure_stack.orchestrator_tg,
    ecs_security_group=infrastructure_stack.ecs_sg,
    namespace=infrastructure_stack.namespace,
    queue_url=sqs_stack.queue.queue_url,
    table_name=dynamodb_stack.table.table_name,
    gpu_instance_id=gpu_instance_id,
    orchestrator_role=iam_stack.orchestrator_role,
    cors_origins=cors_origins,
    env=env,
    description="ECS Fargate service for GPU task orchestrator"
)

# Stack 8: Canvas Service
canvas_service_stack = CanvasServiceStack(
    app,
    f"{project_name}-canvas-service",
    vpc=infrastructure_stack.vpc,
    cluster=infrastructure_stack.cluster,
    target_group=infrastructure_stack.canvas_tg,
    ecs_security_group=infrastructure_stack.ecs_sg,
    namespace=infrastructure_stack.namespace,
    s3_bucket=s3_bucket,
    supabase_url=supabase_url,
    supabase_key=supabase_key,
    cloudfront_domain=cloudfront_domain,
    cors_origins=cors_origins,
    env=env,
    description="ECS Fargate service for Canvas image editing"
)

# Add explicit dependencies
# Note: Some dependencies are implicit (e.g., AlarmStack uses lambda_function from LambdaStack)
# CDK will automatically figure out the dependency graph
iam_stack.add_dependency(sqs_stack)
iam_stack.add_dependency(dynamodb_stack)

# Infrastructure stack has no dependencies (creates base resources)

# Service stacks depend on infrastructure and IAM stacks
orchestrator_service_stack.add_dependency(infrastructure_stack)
orchestrator_service_stack.add_dependency(iam_stack)
orchestrator_service_stack.add_dependency(sqs_stack)
orchestrator_service_stack.add_dependency(dynamodb_stack)

canvas_service_stack.add_dependency(infrastructure_stack)
# Canvas service doesn't depend on IAM, SQS, or DynamoDB stacks

# Add tags to all resources
Tags.of(app).add("Project", "GPU-Orchestrator")
Tags.of(app).add("ManagedBy", "CDK")
Tags.of(app).add("Environment", app.node.try_get_context('environment') or 'dev')

app.synth()
