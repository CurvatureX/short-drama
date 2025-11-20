#!/bin/bash
# Build and push Docker images to ECR for both Canvas Service and Orchestrator

set -e

echo "=========================================="
echo "Building and Pushing Docker Images to ECR"
echo "=========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get AWS account and region
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION=$(aws configure get region)
REGION=${REGION:-us-east-1}

echo -e "${GREEN}AWS Account: $ACCOUNT_ID${NC}"
echo -e "${GREEN}Region: $REGION${NC}"
echo ""

# ECR repository URIs
ORCHESTRATOR_REPO="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/orchestrator"
CANVAS_REPO="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/canvas-service"

# Step 1: Login to ECR
echo "Step 1: Logging into ECR..."
aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin ${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com
echo -e "${GREEN}✓ Logged into ECR${NC}"
echo ""

# Step 2: Create ECR repositories if they don't exist
echo "Step 2: Ensuring ECR repositories exist..."

for repo in orchestrator canvas-service; do
    if ! aws ecr describe-repositories --repository-names $repo --region $REGION &> /dev/null; then
        echo "Creating repository: $repo"
        aws ecr create-repository \
            --repository-name $repo \
            --region $REGION \
            --image-scanning-configuration scanOnPush=true
        echo -e "${GREEN}✓ Repository created: $repo${NC}"
    else
        echo -e "${GREEN}✓ Repository exists: $repo${NC}"
    fi
done
echo ""

# Step 3: Build and push Orchestrator
echo "Step 3: Building Orchestrator Docker image..."
cd ../orchestrator
docker build --platform linux/amd64 -t orchestrator:latest .
docker tag orchestrator:latest $ORCHESTRATOR_REPO:latest

echo "Pushing Orchestrator to ECR..."
docker push $ORCHESTRATOR_REPO:latest
echo -e "${GREEN}✓ Orchestrator pushed to ECR${NC}"
echo ""

# Step 4: Build and push Canvas Service
echo "Step 4: Building Canvas Service Docker image..."
cd ../canvas_service
docker build --platform linux/amd64 -t canvas-service:latest .
docker tag canvas-service:latest $CANVAS_REPO:latest

echo "Pushing Canvas Service to ECR..."
docker push $CANVAS_REPO:latest
echo -e "${GREEN}✓ Canvas Service pushed to ECR${NC}"
echo ""

# Go back to infra directory
cd ../infra

echo "=========================================="
echo "Build and Push Complete!"
echo "=========================================="
echo ""
echo "Images pushed:"
echo "  Orchestrator:    $ORCHESTRATOR_REPO:latest"
echo "  Canvas Service:  $CANVAS_REPO:latest"
echo ""
echo "Next steps:"
echo "1. Deploy/update ECS services: cdk deploy gpu-orchestrator-ecs"
echo "2. Or run full deployment: ./deploy.sh"
echo ""
