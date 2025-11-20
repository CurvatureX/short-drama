"""
Infrastructure Stack - Shared infrastructure for backend services

Creates the foundational infrastructure that all services depend on:
- VPC with public and private subnets
- Application Load Balancer with routing
- ECS Cluster
- Security Groups
- Target Groups
"""

from aws_cdk import (
    Stack,
    Duration,
    CfnOutput,
)
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_elasticloadbalancingv2 as elbv2
from aws_cdk import aws_servicediscovery as servicediscovery
from constructs import Construct


class InfrastructureStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ==================== VPC ====================
        self.vpc = ec2.Vpc(
            self,
            "BackendVPC",
            max_azs=2,
            nat_gateways=1,
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

        # ==================== ECS Cluster ====================
        self.cluster = ecs.Cluster(
            self,
            "BackendCluster",
            cluster_name="short-drama-backend-cluster",
            vpc=self.vpc,
            container_insights=True,
        )

        # ==================== Service Discovery ====================
        self.namespace = servicediscovery.PrivateDnsNamespace(
            self,
            "ServiceDiscoveryNamespace",
            name="backend.local",
            vpc=self.vpc,
            description="Service discovery namespace for backend services",
        )

        # ==================== Security Groups ====================
        # ALB Security Group
        self.alb_sg = ec2.SecurityGroup(
            self,
            "AlbSecurityGroup",
            vpc=self.vpc,
            description="Security group for Backend ALB",
            allow_all_outbound=True,
        )
        self.alb_sg.add_ingress_rule(
            ec2.Peer.any_ipv4(),
            ec2.Port.tcp(80),
            "Allow HTTP from internet"
        )

        # ECS Security Group
        self.ecs_sg = ec2.SecurityGroup(
            self,
            "EcsSecurityGroup",
            vpc=self.vpc,
            description="Security group for ECS tasks",
            allow_all_outbound=True,
        )

        # Allow traffic from ALB to ECS tasks
        self.ecs_sg.add_ingress_rule(
            self.alb_sg,
            ec2.Port.tcp(8080),
            "Allow traffic from ALB to Orchestrator"
        )
        self.ecs_sg.add_ingress_rule(
            self.alb_sg,
            ec2.Port.tcp(9000),
            "Allow traffic from ALB to Canvas Service"
        )

        # Allow ECS tasks to communicate with each other
        self.ecs_sg.add_ingress_rule(
            self.ecs_sg,
            ec2.Port.all_traffic(),
            "Allow inter-service communication"
        )

        # ==================== Application Load Balancer ====================
        self.alb = elbv2.ApplicationLoadBalancer(
            self,
            "BackendALB",
            vpc=self.vpc,
            internet_facing=True,
            load_balancer_name="short-drama-backend-alb",
            security_group=self.alb_sg,
        )

        # ==================== Target Groups ====================
        # Orchestrator target group
        self.orchestrator_tg = elbv2.ApplicationTargetGroup(
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
        self.canvas_tg = elbv2.ApplicationTargetGroup(
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

        # ==================== ALB Listeners and Routing ====================
        # Default listener forwards to Canvas Service (handles most paths)
        self.listener = self.alb.add_listener(
            "HttpListener",
            port=80,
            protocol=elbv2.ApplicationProtocol.HTTP,
            default_action=elbv2.ListenerAction.forward(
                target_groups=[self.canvas_tg]
            ),
        )

        # Orchestrator route: /api/v1/* (higher priority to override default)
        self.listener.add_action(
            "OrchestratorRoute",
            priority=10,
            conditions=[
                elbv2.ListenerCondition.path_patterns(["/api/v1/*", "/api/v1"])
            ],
            action=elbv2.ListenerAction.forward(target_groups=[self.orchestrator_tg]),
        )

        # ==================== Outputs ====================
        CfnOutput(
            self,
            "LoadBalancerDNS",
            value=self.alb.load_balancer_dns_name,
            description="DNS name of the Application Load Balancer",
            export_name=f"{construct_id}-ALB-DNS"
        )

        CfnOutput(
            self,
            "VpcId",
            value=self.vpc.vpc_id,
            description="VPC ID",
            export_name=f"{construct_id}-VPC-ID"
        )

        CfnOutput(
            self,
            "ClusterName",
            value=self.cluster.cluster_name,
            description="ECS Cluster Name",
            export_name=f"{construct_id}-Cluster-Name"
        )

        CfnOutput(
            self,
            "ClusterArn",
            value=self.cluster.cluster_arn,
            description="ECS Cluster ARN",
            export_name=f"{construct_id}-Cluster-ARN"
        )
