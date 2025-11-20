#!/bin/bash

set -e

# ========================================
# ECS Service Setup Script
# ========================================
# This script creates the initial ECS service, cluster,
# and required infrastructure.
#
# Run this ONCE before deploying with deploy-to-ecs.sh
# ========================================

# Configuration
AWS_REGION=${AWS_REGION:-us-east-1}
ECS_CLUSTER=${ECS_CLUSTER:-short-drama-cluster}
SERVICE_NAME=${SERVICE_NAME:-short-drama-backend}
TASK_FAMILY=${TASK_FAMILY:-short-drama-backend}
VPC_ID=${VPC_ID}
SUBNET_IDS=${SUBNET_IDS}  # Comma-separated subnet IDs
SECURITY_GROUP_ID=${SECURITY_GROUP_ID}

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check required variables
check_variables() {
    log_info "Checking required variables..."

    if [ -z "$VPC_ID" ]; then
        log_error "VPC_ID is required. Set it before running this script."
        exit 1
    fi

    if [ -z "$SUBNET_IDS" ]; then
        log_error "SUBNET_IDS is required (comma-separated). Set it before running this script."
        exit 1
    fi

    if [ -z "$SECURITY_GROUP_ID" ]; then
        log_warn "SECURITY_GROUP_ID not set. Will create a default security group."
    fi

    log_info "Variables check passed"
}

# Create ECS cluster
create_cluster() {
    log_info "Creating ECS cluster: $ECS_CLUSTER"

    if aws ecs describe-clusters --clusters $ECS_CLUSTER --region $AWS_REGION | grep -q "ACTIVE"; then
        log_info "Cluster already exists"
    else
        aws ecs create-cluster \
            --cluster-name $ECS_CLUSTER \
            --region $AWS_REGION
        log_info "Cluster created"
    fi
}

# Create security group if not provided
create_security_group() {
    if [ -z "$SECURITY_GROUP_ID" ]; then
        log_info "Creating security group..."

        SECURITY_GROUP_ID=$(aws ec2 create-security-group \
            --group-name short-drama-backend-sg \
            --description "Security group for short-drama backend services" \
            --vpc-id $VPC_ID \
            --region $AWS_REGION \
            --query 'GroupId' \
            --output text)

        log_info "Security group created: $SECURITY_GROUP_ID"

        # Add ingress rules
        log_info "Adding ingress rules..."

        # Canvas Service (9000)
        aws ec2 authorize-security-group-ingress \
            --group-id $SECURITY_GROUP_ID \
            --protocol tcp \
            --port 9000 \
            --cidr 0.0.0.0/0 \
            --region $AWS_REGION

        # Orchestrator (8080)
        aws ec2 authorize-security-group-ingress \
            --group-id $SECURITY_GROUP_ID \
            --protocol tcp \
            --port 8080 \
            --cidr 0.0.0.0/0 \
            --region $AWS_REGION

        log_info "Ingress rules added"
    else
        log_info "Using existing security group: $SECURITY_GROUP_ID"
    fi
}

# Create Application Load Balancer (optional but recommended)
create_alb() {
    log_info "Creating Application Load Balancer..."

    # Convert comma-separated subnet IDs to space-separated
    SUBNETS=$(echo $SUBNET_IDS | tr ',' ' ')

    ALB_ARN=$(aws elbv2 create-load-balancer \
        --name short-drama-backend-alb \
        --subnets $SUBNETS \
        --security-groups $SECURITY_GROUP_ID \
        --scheme internet-facing \
        --type application \
        --ip-address-type ipv4 \
        --region $AWS_REGION \
        --query 'LoadBalancers[0].LoadBalancerArn' \
        --output text 2>/dev/null || echo "")

    if [ -z "$ALB_ARN" ]; then
        log_warn "ALB might already exist or creation failed. Continuing..."
        return
    fi

    log_info "ALB created: $ALB_ARN"

    # Create target groups
    log_info "Creating target groups..."

    # Canvas Service target group
    CANVAS_TG_ARN=$(aws elbv2 create-target-group \
        --name canvas-service-tg \
        --protocol HTTP \
        --port 9000 \
        --vpc-id $VPC_ID \
        --target-type ip \
        --health-check-path /health \
        --region $AWS_REGION \
        --query 'TargetGroups[0].TargetGroupArn' \
        --output text 2>/dev/null || echo "")

    # Orchestrator target group
    ORCH_TG_ARN=$(aws elbv2 create-target-group \
        --name orchestrator-tg \
        --protocol HTTP \
        --port 8080 \
        --vpc-id $VPC_ID \
        --target-type ip \
        --health-check-path /health \
        --region $AWS_REGION \
        --query 'TargetGroups[0].TargetGroupArn' \
        --output text 2>/dev/null || echo "")

    log_info "Target groups created"

    # Create listeners
    log_info "Creating ALB listeners..."

    # Canvas Service listener (port 9000)
    aws elbv2 create-listener \
        --load-balancer-arn $ALB_ARN \
        --protocol HTTP \
        --port 9000 \
        --default-actions Type=forward,TargetGroupArn=$CANVAS_TG_ARN \
        --region $AWS_REGION 2>/dev/null || log_warn "Canvas listener creation failed"

    # Orchestrator listener (port 8080)
    aws elbv2 create-listener \
        --load-balancer-arn $ALB_ARN \
        --protocol HTTP \
        --port 8080 \
        --default-actions Type=forward,TargetGroupArn=$ORCH_TG_ARN \
        --region $AWS_REGION 2>/dev/null || log_warn "Orchestrator listener creation failed"

    log_info "ALB setup completed"

    # Save target group ARNs for service creation
    export CANVAS_TG_ARN
    export ORCH_TG_ARN
}

# Create ECS service
create_service() {
    log_info "Creating ECS service: $SERVICE_NAME"

    # Convert comma-separated subnet IDs to proper JSON array
    SUBNET_ARRAY=$(echo $SUBNET_IDS | jq -R 'split(",") | map(ltrimstr(" ") | rtrimstr(" "))')

    # Create service configuration
    cat > /tmp/ecs-service-config.json <<EOF
{
    "cluster": "$ECS_CLUSTER",
    "serviceName": "$SERVICE_NAME",
    "taskDefinition": "$TASK_FAMILY",
    "desiredCount": 1,
    "launchType": "FARGATE",
    "networkConfiguration": {
        "awsvpcConfiguration": {
            "subnets": $SUBNET_ARRAY,
            "securityGroups": ["$SECURITY_GROUP_ID"],
            "assignPublicIp": "ENABLED"
        }
    },
    "healthCheckGracePeriodSeconds": 60
}
EOF

    aws ecs create-service \
        --cli-input-json file:///tmp/ecs-service-config.json \
        --region $AWS_REGION

    log_info "ECS service created"
    rm /tmp/ecs-service-config.json
}

# Main setup flow
main() {
    log_info "Starting ECS setup..."

    check_variables
    create_cluster
    create_security_group
    # create_alb  # Uncomment if you want ALB
    create_service

    log_info "Setup completed successfully!"
    log_info ""
    log_info "Security Group ID: $SECURITY_GROUP_ID"
    log_info ""
    log_info "Next steps:"
    log_info "1. Deploy your application: ./deploy-to-ecs.sh"
    log_info "2. Check service status: aws ecs describe-services --cluster $ECS_CLUSTER --services $SERVICE_NAME"
    log_info "3. Get task public IP: aws ecs describe-tasks --cluster $ECS_CLUSTER --tasks \$(aws ecs list-tasks --cluster $ECS_CLUSTER --service-name $SERVICE_NAME --query 'taskArns[0]' --output text) --query 'tasks[0].attachments[0].details[?name==\`networkInterfaceId\`].value' --output text | xargs -I {} aws ec2 describe-network-interfaces --network-interface-ids {} --query 'NetworkInterfaces[0].Association.PublicIp' --output text"
}

main
