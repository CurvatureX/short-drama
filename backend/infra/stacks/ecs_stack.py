"""
ECS Stack - Canvas Service and Orchestrator Deployment

Creates ECS Fargate services for both Canvas Service and Orchestrator:
- VPC with public and private subnets
- Application Load Balancer with path-based routing
- ECS Cluster and two Fargate services
- ECR repositories for Docker images
- Auto-scaling configuration
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
from constructs import Construct


class EcsStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        queue_url: str,
        table_name: str,
        gpu_instance_id: str,
        orchestrator_role: iam.Role,
        s3_bucket: str,
        supabase_url: str,
        supabase_key: str,
        cloudfront_domain: str,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ==================== VPC ====================
        # Create VPC with public subnets for ALB and NAT Gateways
        # Private subnets for ECS tasks
        self.vpc = ec2.Vpc(
            self,
            "BackendVPC",
            max_azs=2,  # Deploy across 2 AZs for high availability
            nat_gateways=1,  # Cost optimization: 1 NAT gateway
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="Private",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24,
                ),
            ],
        )

        # ==================== ECR Repositories ====================
        # Import existing ECR repositories (created outside of CDK)
        # This allows us to use pre-existing repositories with images already pushed
        self.orchestrator_repo = ecr.Repository.from_repository_name(
            self,
            "OrchestratorRepo",
            repository_name="orchestrator"
        )

        self.canvas_repo = ecr.Repository.from_repository_name(
            self,
            "CanvasServiceRepo",
            repository_name="canvas-service"
        )

        # ==================== ECS Cluster ====================
        self.cluster = ecs.Cluster(
            self,
            "BackendCluster",
            cluster_name="short-drama-backend-cluster",
            vpc=self.vpc,
            container_insights=True,  # Enable CloudWatch Container Insights
        )

        # ==================== IAM Roles ====================
        # Task execution role (for pulling images, logging)
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

        # ==================== CloudWatch Log Groups ====================
        orchestrator_log_group = logs.LogGroup(
            self,
            "OrchestratorLogGroup",
            log_group_name="/ecs/orchestrator",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY,
        )

        canvas_log_group = logs.LogGroup(
            self,
            "CanvasLogGroup",
            log_group_name="/ecs/canvas-service",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # ==================== Orchestrator Task Definition ====================
        orchestrator_task = ecs.FargateTaskDefinition(
            self,
            "OrchestratorTask",
            family="orchestrator-task",
            cpu=512,  # 0.5 vCPU
            memory_limit_mib=1024,  # 1 GB RAM
            execution_role=task_execution_role,
            task_role=orchestrator_role,
        )

        orchestrator_container = orchestrator_task.add_container(
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
                log_group=orchestrator_log_group,
            ),
            health_check=ecs.HealthCheck(
                command=["CMD-SHELL", "curl -f http://localhost:8080/health || exit 1"],
                interval=Duration.seconds(30),
                timeout=Duration.seconds(5),
                retries=3,
                start_period=Duration.seconds(60),
            ),
        )

        orchestrator_container.add_port_mappings(
            ecs.PortMapping(container_port=8080, protocol=ecs.Protocol.TCP)
        )

        # ==================== Canvas Service Task Definition ====================
        canvas_task = ecs.FargateTaskDefinition(
            self,
            "CanvasTask",
            family="canvas-service-task",
            cpu=256,  # 0.25 vCPU
            memory_limit_mib=512,  # 512 MB RAM
            execution_role=task_execution_role,
            task_role=canvas_task_role,
        )

        canvas_container = canvas_task.add_container(
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
                log_group=canvas_log_group,
            ),
            health_check=ecs.HealthCheck(
                command=["CMD-SHELL", "curl -f http://localhost:9000/health || exit 1"],
                interval=Duration.seconds(30),
                timeout=Duration.seconds(5),
                retries=3,
                start_period=Duration.seconds(60),
            ),
        )

        canvas_container.add_port_mappings(
            ecs.PortMapping(container_port=9000, protocol=ecs.Protocol.TCP)
        )

        # ==================== Application Load Balancer ====================
        # Security group for ALB
        alb_sg = ec2.SecurityGroup(
            self,
            "AlbSecurityGroup",
            vpc=self.vpc,
            description="Security group for Backend ALB",
            allow_all_outbound=True,
        )

        # Allow HTTP traffic from internet
        alb_sg.add_ingress_rule(
            ec2.Peer.any_ipv4(),
            ec2.Port.tcp(80),
            "Allow HTTP from internet"
        )

        # Application Load Balancer
        alb = elbv2.ApplicationLoadBalancer(
            self,
            "BackendALB",
            vpc=self.vpc,
            internet_facing=True,
            load_balancer_name="short-drama-backend-alb",
            security_group=alb_sg,
        )

        # ==================== Target Groups ====================
        # Orchestrator target group
        orchestrator_tg = elbv2.ApplicationTargetGroup(
            self,
            "OrchestratorTargetGroup",
            vpc=self.vpc,
            port=8080,
            protocol=elbv2.ApplicationProtocol.HTTP,
            target_type=elbv2.TargetType.IP,
            health_check=elbv2.HealthCheck(
                path="/health",
                interval=Duration.seconds(30),
                timeout=Duration.seconds(5),
                healthy_threshold_count=2,
                unhealthy_threshold_count=3,
            ),
            deregistration_delay=Duration.seconds(30),
        )

        # Canvas Service target group
        canvas_tg = elbv2.ApplicationTargetGroup(
            self,
            "CanvasTargetGroup",
            vpc=self.vpc,
            port=9000,
            protocol=elbv2.ApplicationProtocol.HTTP,
            target_type=elbv2.TargetType.IP,
            health_check=elbv2.HealthCheck(
                path="/health",
                interval=Duration.seconds(30),
                timeout=Duration.seconds(5),
                healthy_threshold_count=2,
                unhealthy_threshold_count=3,
            ),
            deregistration_delay=Duration.seconds(30),
        )

        # ==================== ALB Listeners ====================
        # Default listener forwards to Canvas Service (since it handles most paths)
        listener = alb.add_listener(
            "HttpListener",
            port=80,
            protocol=elbv2.ApplicationProtocol.HTTP,
            default_action=elbv2.ListenerAction.forward(
                target_groups=[canvas_tg]
            ),
        )

        # Add path-based routing rules
        # Orchestrator: /api/v1/* and /health (higher priority to override default)
        listener.add_action(
            "OrchestratorRoute",
            priority=10,
            conditions=[
                elbv2.ListenerCondition.path_patterns(["/api/v1/*", "/api/v1"])
            ],
            action=elbv2.ListenerAction.forward(target_groups=[orchestrator_tg]),
        )

        # All other paths go to Canvas Service (default action)

        # ==================== Security Groups for ECS ====================
        # Security group for ECS tasks
        ecs_sg = ec2.SecurityGroup(
            self,
            "EcsSecurityGroup",
            vpc=self.vpc,
            description="Security group for Backend ECS tasks",
            allow_all_outbound=True,
        )

        # Allow traffic from ALB
        ecs_sg.add_ingress_rule(
            alb_sg,
            ec2.Port.tcp(8080),
            "Allow Orchestrator traffic from ALB"
        )
        ecs_sg.add_ingress_rule(
            alb_sg,
            ec2.Port.tcp(9000),
            "Allow Canvas traffic from ALB"
        )

        # Allow services to communicate with each other
        ecs_sg.add_ingress_rule(
            ecs_sg,
            ec2.Port.all_traffic(),
            "Allow inter-service communication"
        )

        # ==================== Fargate Services ====================
        # Orchestrator service
        self.orchestrator_service = ecs.FargateService(
            self,
            "OrchestratorService",
            cluster=self.cluster,
            task_definition=orchestrator_task,
            service_name="orchestrator-service",
            desired_count=1,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            security_groups=[ecs_sg],
            health_check_grace_period=Duration.seconds(60),
            circuit_breaker=ecs.DeploymentCircuitBreaker(rollback=True),
        )

        self.orchestrator_service.attach_to_application_target_group(orchestrator_tg)

        # Canvas Service
        self.canvas_service = ecs.FargateService(
            self,
            "CanvasService",
            cluster=self.cluster,
            task_definition=canvas_task,
            service_name="canvas-service",
            desired_count=1,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            security_groups=[ecs_sg],
            health_check_grace_period=Duration.seconds(60),
            circuit_breaker=ecs.DeploymentCircuitBreaker(rollback=True),
        )

        self.canvas_service.attach_to_application_target_group(canvas_tg)

        # ==================== Service Discovery (Optional) ====================
        # Enable service discovery for inter-service communication
        namespace = self.cluster.add_default_cloud_map_namespace(
            name="backend.local",
        )

        self.orchestrator_service.enable_cloud_map(
            name="orchestrator",
            cloud_map_namespace=namespace,
        )

        self.canvas_service.enable_cloud_map(
            name="canvas-service",
            cloud_map_namespace=namespace,
        )

        # ==================== Outputs ====================
        CfnOutput(
            self,
            "LoadBalancerDNS",
            value=alb.load_balancer_dns_name,
            description="DNS name of the Application Load Balancer",
            export_name=f"{construct_id}-LoadBalancerDNS"
        )

        CfnOutput(
            self,
            "OrchestratorURL",
            value=f"http://{alb.load_balancer_dns_name}/api/v1",
            description="URL of the Orchestrator service",
            export_name=f"{construct_id}-OrchestratorURL"
        )

        CfnOutput(
            self,
            "CanvasServiceURL",
            value=f"http://{alb.load_balancer_dns_name}",
            description="URL of the Canvas service",
            export_name=f"{construct_id}-CanvasServiceURL"
        )

        CfnOutput(
            self,
            "OrchestratorEcrUri",
            value=self.orchestrator_repo.repository_uri,
            description="ECR repository URI for orchestrator images",
            export_name=f"{construct_id}-OrchestratorEcrUri"
        )

        CfnOutput(
            self,
            "CanvasEcrUri",
            value=self.canvas_repo.repository_uri,
            description="ECR repository URI for canvas service images",
            export_name=f"{construct_id}-CanvasEcrUri"
        )

        CfnOutput(
            self,
            "ClusterName",
            value=self.cluster.cluster_name,
            description="Name of the ECS cluster",
            export_name=f"{construct_id}-ClusterName"
        )

        CfnOutput(
            self,
            "OrchestratorServiceName",
            value=self.orchestrator_service.service_name,
            description="Name of the Orchestrator ECS service",
            export_name=f"{construct_id}-OrchestratorServiceName"
        )

        CfnOutput(
            self,
            "CanvasServiceName",
            value=self.canvas_service.service_name,
            description="Name of the Canvas ECS service",
            export_name=f"{construct_id}-CanvasServiceName"
        )
