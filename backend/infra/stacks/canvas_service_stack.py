"""
Canvas Service Stack

Creates the ECS Fargate service for the Canvas image editing service:
- ECR repository reference
- Task definition with canvas service container
- Fargate service
- Service discovery integration
"""

from aws_cdk import (
    Stack,
    Duration,
    CfnOutput,
    RemovalPolicy,
)
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_ecr as ecr
from aws_cdk import aws_iam as iam
from aws_cdk import aws_elasticloadbalancingv2 as elbv2
from aws_cdk import aws_logs as logs
from aws_cdk import aws_servicediscovery as servicediscovery
from constructs import Construct


class CanvasServiceStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        vpc: ec2.Vpc,
        cluster: ecs.Cluster,
        target_group: elbv2.ApplicationTargetGroup,
        ecs_security_group: ec2.SecurityGroup,
        namespace: servicediscovery.PrivateDnsNamespace,
        s3_bucket: str,
        supabase_url: str,
        supabase_key: str,
        cloudfront_domain: str,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ==================== ECR Repository ====================
        # Import existing ECR repository
        self.canvas_repo = ecr.Repository.from_repository_name(
            self,
            "CanvasServiceRepo",
            repository_name="canvas-service"
        )

        # ==================== IAM Roles ====================
        # Task execution role (for pulling images, writing logs)
        task_execution_role = iam.Role(
            self,
            "TaskExecutionRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AmazonECSTaskExecutionRolePolicy"
                )
            ],
        )

        # Grant ECR read permissions
        self.canvas_repo.grant_pull(task_execution_role)

        # Canvas Service task role (for S3, Supabase access)
        canvas_task_role = iam.Role(
            self,
            "CanvasTaskRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
        )

        # Grant S3 permissions to Canvas Service
        canvas_task_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "s3:GetObject",
                    "s3:PutObject",
                    "s3:PutObjectAcl",
                ],
                resources=["arn:aws:s3:::*/*"],
            )
        )

        # ==================== CloudWatch Log Group ====================
        log_group = logs.LogGroup(
            self,
            "CanvasLogGroup",
            log_group_name="/ecs/canvas-service",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # ==================== Task Definition ====================
        task = ecs.FargateTaskDefinition(
            self,
            "CanvasTask",
            family="canvas-service-task",
            cpu=256,  # 0.25 vCPU
            memory_limit_mib=512,  # 512 MB RAM
            execution_role=task_execution_role,
            task_role=canvas_task_role,
        )

        container = task.add_container(
            "CanvasContainer",
            container_name="canvas-service",
            image=ecs.ContainerImage.from_ecr_repository(
                self.canvas_repo,
                tag="latest"
            ),
            # Note: Sensitive env vars should be in Secrets Manager for production
            environment={
                "AWS_DEFAULT_REGION": self.region,
                "S3_BUCKET": s3_bucket,
                "SUPABASE_URL": supabase_url,
                "SUPABASE_SERVICE_ROLE_KEY": supabase_key,
                "CLOUDFRONT_DOMAIN": cloudfront_domain,
            },
            logging=ecs.LogDriver.aws_logs(
                stream_prefix="canvas-service",
                log_group=log_group,
            ),
            health_check=ecs.HealthCheck(
                command=["CMD-SHELL", "curl -f http://localhost:9000/health || exit 1"],
                interval=Duration.seconds(30),
                timeout=Duration.seconds(5),
                retries=3,
                start_period=Duration.seconds(60),
            ),
        )

        container.add_port_mappings(
            ecs.PortMapping(container_port=9000, protocol=ecs.Protocol.TCP)
        )

        # ==================== Fargate Service ====================
        self.service = ecs.FargateService(
            self,
            "CanvasService",
            cluster=cluster,
            task_definition=task,
            service_name="canvas-service",
            desired_count=1,
            security_groups=[ecs_security_group],
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            circuit_breaker=ecs.DeploymentCircuitBreaker(
                rollback=False  # Don't trigger CloudFormation rollback
            ),
        )

        # Attach to ALB target group
        self.service.attach_to_application_target_group(target_group)

        # Service Discovery
        self.service.enable_cloud_map(
            name="canvas-service",
            cloud_map_namespace=namespace,
            dns_record_type=servicediscovery.DnsRecordType.A,
            dns_ttl=Duration.seconds(60),
        )

        # ==================== Outputs ====================
        CfnOutput(
            self,
            "ServiceName",
            value=self.service.service_name,
            description="Name of the Canvas ECS service",
            export_name=f"{construct_id}-Service-Name"
        )

        CfnOutput(
            self,
            "ServiceArn",
            value=self.service.service_arn,
            description="ARN of the Canvas ECS service",
            export_name=f"{construct_id}-Service-ARN"
        )

        CfnOutput(
            self,
            "ECRRepositoryUri",
            value=self.canvas_repo.repository_uri,
            description="ECR repository URI for canvas service images",
            export_name=f"{construct_id}-ECR-URI"
        )
