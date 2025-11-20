"""
Orchestrator Service Stack

Creates the ECS Fargate service for the GPU task orchestrator:
- ECR repository reference
- Task definition with orchestrator container
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


class OrchestratorServiceStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        vpc: ec2.Vpc,
        cluster: ecs.Cluster,
        target_group: elbv2.ApplicationTargetGroup,
        ecs_security_group: ec2.SecurityGroup,
        namespace: servicediscovery.PrivateDnsNamespace,
        queue_url: str,
        table_name: str,
        gpu_instance_id: str,
        orchestrator_role: iam.Role,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ==================== ECR Repository ====================
        # Import existing ECR repository
        self.orchestrator_repo = ecr.Repository.from_repository_name(
            self,
            "OrchestratorRepo",
            repository_name="orchestrator"
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
        self.orchestrator_repo.grant_pull(task_execution_role)

        # ==================== CloudWatch Log Group ====================
        log_group = logs.LogGroup(
            self,
            "OrchestratorLogGroup",
            log_group_name="/ecs/orchestrator",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # ==================== Task Definition ====================
        task = ecs.FargateTaskDefinition(
            self,
            "OrchestratorTask",
            family="orchestrator-task",
            cpu=512,  # 0.5 vCPU
            memory_limit_mib=1024,  # 1 GB RAM
            execution_role=task_execution_role,
            task_role=orchestrator_role,
        )

        container = task.add_container(
            "OrchestratorContainer",
            container_name="orchestrator",
            image=ecs.ContainerImage.from_ecr_repository(
                self.orchestrator_repo,
                tag="latest"
            ),
            environment={
                "AWS_DEFAULT_REGION": self.region,
                "SQS_QUEUE_URL": queue_url,
                "DYNAMODB_TABLE": table_name,
                "GPU_INSTANCE_ID": gpu_instance_id,
            },
            logging=ecs.LogDriver.aws_logs(
                stream_prefix="orchestrator",
                log_group=log_group,
            ),
            health_check=ecs.HealthCheck(
                command=["CMD-SHELL", "curl -f http://localhost:8080/health || exit 1"],
                interval=Duration.seconds(30),
                timeout=Duration.seconds(5),
                retries=3,
                start_period=Duration.seconds(60),
            ),
        )

        container.add_port_mappings(
            ecs.PortMapping(container_port=8080, protocol=ecs.Protocol.TCP)
        )

        # ==================== Fargate Service ====================
        self.service = ecs.FargateService(
            self,
            "OrchestratorService",
            cluster=cluster,
            task_definition=task,
            service_name="orchestrator-service",
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
            name="orchestrator-service",
            cloud_map_namespace=namespace,
            dns_record_type=servicediscovery.DnsRecordType.A,
            dns_ttl=Duration.seconds(60),
        )

        # ==================== Outputs ====================
        CfnOutput(
            self,
            "ServiceName",
            value=self.service.service_name,
            description="Name of the Orchestrator ECS service",
            export_name=f"{construct_id}-Service-Name"
        )

        CfnOutput(
            self,
            "ServiceArn",
            value=self.service.service_arn,
            description="ARN of the Orchestrator ECS service",
            export_name=f"{construct_id}-Service-ARN"
        )

        CfnOutput(
            self,
            "ECRRepositoryUri",
            value=self.orchestrator_repo.repository_uri,
            description="ECR repository URI for orchestrator images",
            export_name=f"{construct_id}-ECR-URI"
        )
