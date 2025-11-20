#!/bin/bash

set -e

# ========================================
# ECS Deployment Script
# ========================================
# This script builds Docker images, pushes them to ECR,
# and deploys them to ECS Fargate.
#
# Prerequisites:
# - AWS CLI configured with appropriate credentials
# - Docker installed and running
# - ECR repositories created
# - ECS cluster created
# - IAM roles created (ecsTaskExecutionRole, ecsTaskRole)
# ========================================

# Configuration
AWS_REGION=${AWS_REGION:-us-east-1}
AWS_ACCOUNT_ID=${AWS_ACCOUNT_ID}
ECS_CLUSTER=${ECS_CLUSTER:-short-drama-cluster}
SERVICE_NAME=${SERVICE_NAME:-short-drama-backend}
TASK_FAMILY=${TASK_FAMILY:-short-drama-backend}

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Helper functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."

    if ! command -v aws &> /dev/null; then
        log_error "AWS CLI is not installed"
        exit 1
    fi

    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed"
        exit 1
    fi

    if [ -z "$AWS_ACCOUNT_ID" ]; then
        log_warn "AWS_ACCOUNT_ID not set, attempting to retrieve..."
        AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
        log_info "AWS Account ID: $AWS_ACCOUNT_ID"
    fi

    log_info "Prerequisites check passed"
}

# Create ECR repositories if they don't exist
create_ecr_repos() {
    log_info "Ensuring ECR repositories exist..."

    for repo in canvas-service orchestrator; do
        if ! aws ecr describe-repositories --repository-names $repo --region $AWS_REGION &> /dev/null; then
            log_info "Creating ECR repository: $repo"
            aws ecr create-repository \
                --repository-name $repo \
                --region $AWS_REGION \
                --image-scanning-configuration scanOnPush=true
        else
            log_info "ECR repository already exists: $repo"
        fi
    done
}

# Login to ECR
ecr_login() {
    log_info "Logging into ECR..."
    aws ecr get-login-password --region $AWS_REGION | \
        docker login --username AWS --password-stdin ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com
}

# Build and push Docker images
build_and_push() {
    log_info "Building and pushing Docker images..."

    # Canvas Service
    log_info "Building canvas-service..."
    docker build -t canvas-service:latest ./canvas_service
    docker tag canvas-service:latest ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/canvas-service:latest
    log_info "Pushing canvas-service to ECR..."
    docker push ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/canvas-service:latest

    # Orchestrator
    log_info "Building orchestrator..."
    docker build -t orchestrator:latest ./orchestrator
    docker tag orchestrator:latest ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/orchestrator:latest
    log_info "Pushing orchestrator to ECR..."
    docker push ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/orchestrator:latest

    log_info "Docker images built and pushed successfully"
}

# Update task definition with actual account ID
update_task_definition() {
    log_info "Updating task definition with account ID..."

    sed "s/YOUR_ACCOUNT_ID/${AWS_ACCOUNT_ID}/g" ecs-task-definition.json > ecs-task-definition-updated.json

    log_info "Task definition updated"
}

# Register task definition with ECS
register_task_definition() {
    log_info "Registering task definition with ECS..."

    aws ecs register-task-definition \
        --cli-input-json file://ecs-task-definition-updated.json \
        --region $AWS_REGION

    log_info "Task definition registered"
}

# Create CloudWatch log group
create_log_group() {
    log_info "Creating CloudWatch log group..."

    if ! aws logs describe-log-groups --log-group-name-prefix /ecs/short-drama-backend --region $AWS_REGION | grep -q "/ecs/short-drama-backend"; then
        aws logs create-log-group \
            --log-group-name /ecs/short-drama-backend \
            --region $AWS_REGION
        log_info "Log group created"
    else
        log_info "Log group already exists"
    fi
}

# Update or create ECS service
update_or_create_service() {
    log_info "Checking if ECS service exists..."

    if aws ecs describe-services --cluster $ECS_CLUSTER --services $SERVICE_NAME --region $AWS_REGION | grep -q "ACTIVE"; then
        log_info "Updating existing ECS service..."
        aws ecs update-service \
            --cluster $ECS_CLUSTER \
            --service $SERVICE_NAME \
            --task-definition $TASK_FAMILY \
            --force-new-deployment \
            --region $AWS_REGION
        log_info "Service updated"
    else
        log_warn "Service does not exist. Please create it manually or run setup script."
        log_info "Service creation requires VPC and subnet configuration."
    fi
}

# Main deployment flow
main() {
    log_info "Starting ECS deployment..."

    check_prerequisites
    create_ecr_repos
    ecr_login
    build_and_push
    update_task_definition
    create_log_group
    register_task_definition
    update_or_create_service

    log_info "Deployment completed successfully!"
    log_info ""
    log_info "Next steps:"
    log_info "1. Verify deployment: aws ecs describe-services --cluster $ECS_CLUSTER --services $SERVICE_NAME"
    log_info "2. Check logs: aws logs tail /ecs/short-drama-backend --follow"
    log_info "3. If service doesn't exist, run: ./setup-ecs-service.sh"
}

# Run main function
main
