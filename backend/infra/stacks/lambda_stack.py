"""
Lambda Stack - Auto-Shutdown Function

Creates Lambda function that:
- Is triggered by CloudWatch Alarm (queue empty for 30 min)
- Checks GPU instance state
- Stops the instance if running
"""

from aws_cdk import (
    Stack,
    Duration,
    CfnOutput,
)
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_iam as iam
from constructs import Construct
import os


class LambdaStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        gpu_instance_id: str,
        lambda_role: iam.Role,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Get the path to the Lambda code
        # Lambda code is in backend/orchestrator/lambda_shutdown.py
        lambda_code_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "orchestrator"
        )

        # Lambda Function
        self.shutdown_function = lambda_.Function(
            self,
            "ShutdownGpuFunction",
            function_name="shutdown-gpu-lambda",
            description="Auto-shutdown GPU instance when queue is empty for 30 minutes",
            # Runtime
            runtime=lambda_.Runtime.PYTHON_3_11,
            # Handler
            handler="lambda_shutdown.lambda_handler",
            # Code
            code=lambda_.Code.from_asset(
                lambda_code_path,
                exclude=["*.pyc", "__pycache__", "*.md", "test_*.py", "*.txt", "aws/"]
            ),
            # Role
            role=lambda_role,
            # Timeout
            timeout=Duration.seconds(60),
            # Memory
            memory_size=128,
            # Environment variables
            # Note: AWS_REGION is automatically set by Lambda runtime
            environment={
                "GPU_INSTANCE_ID": gpu_instance_id,
            },
            # Reserved concurrent executions (optional)
            # Set to 1 to prevent multiple simultaneous executions
            reserved_concurrent_executions=1,
        )

        # Grant permissions to be invoked by CloudWatch Alarms
        self.shutdown_function.add_permission(
            "AllowCloudWatchInvoke",
            principal=iam.ServicePrincipal("lambda.alarms.cloudwatch.amazonaws.com"),
            action="lambda:InvokeFunction",
            source_account=self.account,
        )

        # Outputs
        CfnOutput(
            self,
            "FunctionArn",
            value=self.shutdown_function.function_arn,
            description="ARN of the GPU shutdown Lambda function",
            export_name=f"{construct_id}-FunctionArn"
        )

        CfnOutput(
            self,
            "FunctionName",
            value=self.shutdown_function.function_name,
            description="Name of the GPU shutdown Lambda function",
            export_name=f"{construct_id}-FunctionName"
        )
