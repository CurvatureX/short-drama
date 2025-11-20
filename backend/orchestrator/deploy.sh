#!/bin/bash

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
AWS_REGION="${AWS_REGION:-us-east-1}"
AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID:-982081090398}"
STACK_NAME="gpu-orchestrator-ecs"
ECR_REPO_NAME="gpu-orchestrator"
CLUSTER_NAME="gpu-orchestrator-cluster"
SERVICE_NAME="gpu-orchestrator-service"

echo -e "${GREEN}=== GPU Orchestrator Deployment Script ===${NC}"
echo ""

# Step 1: Get ECR repository URI
echo -e "${YELLOW}Step 1: Getting ECR repository URI...${NC}"
ECR_REPO=$(aws cloudformation describe-stacks \
  --stack-name $STACK_NAME \
  --region $AWS_REGION \
  --query 'Stacks[0].Outputs[?OutputKey==`EcrRepositoryUri`].OutputValue' \
  --output text 2>/dev/null || echo "")

if [ -z "$ECR_REPO" ]; then
  echo -e "${RED}Error: Could not find ECR repository. Make sure the ECS stack is deployed.${NC}"
  echo "Run: cd ../infra && cdk deploy gpu-orchestrator-ecs"
  exit 1
fi

echo -e "${GREEN}✓ ECR Repository: $ECR_REPO${NC}"
echo ""

# Step 2: Login to ECR
echo -e "${YELLOW}Step 2: Logging into ECR...${NC}"
aws ecr get-login-password --region $AWS_REGION | \
  docker login --username AWS --password-stdin $ECR_REPO
echo -e "${GREEN}✓ Logged in to ECR${NC}"
echo ""

# Step 3: Build Docker image
echo -e "${YELLOW}Step 3: Building Docker image...${NC}"
docker build --platform linux/amd64 -t $ECR_REPO_NAME:latest .
echo -e "${GREEN}✓ Image built${NC}"
echo ""

# Step 4: Tag image
echo -e "${YELLOW}Step 4: Tagging image...${NC}"
GIT_COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo "local")
docker tag $ECR_REPO_NAME:latest $ECR_REPO:latest
docker tag $ECR_REPO_NAME:latest $ECR_REPO:$GIT_COMMIT
echo -e "${GREEN}✓ Tagged as: latest, $GIT_COMMIT${NC}"
echo ""

# Step 5: Push to ECR
echo -e "${YELLOW}Step 5: Pushing to ECR...${NC}"
docker push $ECR_REPO:latest
docker push $ECR_REPO:$GIT_COMMIT
echo -e "${GREEN}✓ Images pushed to ECR${NC}"
echo ""

# Step 6: Force new deployment
echo -e "${YELLOW}Step 6: Triggering ECS deployment...${NC}"
aws ecs update-service \
  --cluster $CLUSTER_NAME \
  --service $SERVICE_NAME \
  --force-new-deployment \
  --region $AWS_REGION \
  > /dev/null

echo -e "${GREEN}✓ Deployment triggered${NC}"
echo ""

# Step 7: Wait for deployment (optional)
echo -e "${YELLOW}Step 7: Waiting for deployment to complete...${NC}"
echo "This may take 2-5 minutes..."
echo ""

aws ecs wait services-stable \
  --cluster $CLUSTER_NAME \
  --services $SERVICE_NAME \
  --region $AWS_REGION

echo -e "${GREEN}✓ Deployment completed successfully!${NC}"
echo ""

# Step 8: Show service URL
ALB_URL=$(aws cloudformation describe-stacks \
  --stack-name $STACK_NAME \
  --region $AWS_REGION \
  --query 'Stacks[0].Outputs[?OutputKey==`LoadBalancerURL`].OutputValue' \
  --output text)

echo -e "${GREEN}=== Deployment Summary ===${NC}"
echo "Cluster: $CLUSTER_NAME"
echo "Service: $SERVICE_NAME"
echo "Image: $ECR_REPO:$GIT_COMMIT"
echo "URL: $ALB_URL"
echo ""
echo -e "${GREEN}Test the service:${NC}"
echo "  curl $ALB_URL/health"
echo "  curl $ALB_URL/"
echo ""
echo -e "${GREEN}View logs:${NC}"
echo "  aws logs tail /ecs/gpu-orchestrator --follow"
echo ""
echo -e "${GREEN}Deployment complete!${NC}"
