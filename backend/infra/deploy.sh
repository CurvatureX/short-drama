#!/bin/bash
# Quick deployment script for GPU Orchestration CDK infrastructure

set -e

echo "=========================================="
echo "GPU Orchestration Infrastructure Deployment"
echo "=========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running in the correct directory
if [ ! -f "app.py" ]; then
    echo -e "${RED}Error: Please run this script from the backend/infra directory${NC}"
    exit 1
fi

# Step 1: Check prerequisites
echo "Step 1: Checking prerequisites..."

# Check AWS CLI
if ! command -v aws &> /dev/null; then
    echo -e "${RED}Error: AWS CLI is not installed${NC}"
    echo "Install: https://aws.amazon.com/cli/"
    exit 1
fi

# Check CDK CLI
if ! command -v cdk &> /dev/null; then
    echo -e "${RED}Error: AWS CDK is not installed${NC}"
    echo "Install: npm install -g aws-cdk"
    exit 1
fi

# Check Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: Python 3 is not installed${NC}"
    exit 1
fi

echo -e "${GREEN}✓ All prerequisites installed${NC}"
echo ""

# Step 2: Verify AWS credentials
echo "Step 2: Verifying AWS credentials..."

if ! aws sts get-caller-identity &> /dev/null; then
    echo -e "${RED}Error: AWS credentials not configured${NC}"
    echo "Run: aws configure"
    exit 1
fi

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION=$(aws configure get region)
REGION=${REGION:-us-east-1}

echo -e "${GREEN}✓ AWS Account: $ACCOUNT_ID${NC}"
echo -e "${GREEN}✓ Region: $REGION${NC}"
echo ""

# Set environment variables
export CDK_DEFAULT_ACCOUNT=$ACCOUNT_ID
export CDK_DEFAULT_REGION=$REGION

# Load environment variables from backend/.env for Canvas Service configuration
echo "Loading environment variables from backend/.env..."
if [ -f "../.env" ]; then
    set -a  # Automatically export all variables
    source ../.env
    set +a
    echo -e "${GREEN}✓ Environment variables loaded${NC}"
else
    echo -e "${YELLOW}Warning: backend/.env not found. Canvas Service may fail without required env vars.${NC}"
fi

# Step 3: Setup Python environment
echo "Step 3: Setting up Python environment..."

if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

echo "Activating virtual environment..."
source .venv/bin/activate

echo "Installing Python dependencies..."
pip install -q --upgrade pip
pip install -q -r requirements.txt

echo -e "${GREEN}✓ Python environment ready${NC}"
echo ""

# Step 4: Bootstrap CDK (if needed)
echo "Step 4: Checking CDK bootstrap status..."

if ! aws cloudformation describe-stacks --stack-name CDKToolkit --region $REGION &> /dev/null; then
    echo -e "${YELLOW}CDK not bootstrapped in this account/region${NC}"
    read -p "Bootstrap CDK now? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Bootstrapping CDK..."
        cdk bootstrap aws://$ACCOUNT_ID/$REGION
        echo -e "${GREEN}✓ CDK bootstrapped${NC}"
    else
        echo -e "${RED}Cannot deploy without CDK bootstrap${NC}"
        exit 1
    fi
else
    echo -e "${GREEN}✓ CDK already bootstrapped${NC}"
fi
echo ""

# Step 5: Synthesize CloudFormation templates
echo "Step 5: Synthesizing CloudFormation templates..."
cdk synth > /dev/null
echo -e "${GREEN}✓ Templates synthesized${NC}"
echo ""

# Step 6: Show what will be deployed
echo "Step 6: Stacks to be deployed:"
cdk list
echo ""

# Step 7: Preview changes
echo "Step 7: Previewing changes..."
echo -e "${YELLOW}Running 'cdk diff' to show what will change...${NC}"
echo ""
cdk diff
echo ""

# Step 8: Confirm deployment
read -p "Deploy all stacks? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Deployment cancelled"
    exit 0
fi

# Step 9: Deploy
echo ""
echo "Step 9: Deploying infrastructure..."
echo -e "${YELLOW}This may take 5-10 minutes...${NC}"
echo ""

cdk deploy --all --require-approval never

# Step 10: Show outputs
echo ""
echo "=========================================="
echo "Deployment Complete!"
echo "=========================================="
echo ""

echo "Stack Outputs:"
echo ""

# Get SQS Queue URL
QUEUE_URL=$(aws cloudformation describe-stacks \
    --stack-name gpu-orchestrator-sqs \
    --query 'Stacks[0].Outputs[?OutputKey==`QueueUrl`].OutputValue' \
    --output text 2>/dev/null || echo "N/A")

# Get DynamoDB Table Name
TABLE_NAME=$(aws cloudformation describe-stacks \
    --stack-name gpu-orchestrator-dynamodb \
    --query 'Stacks[0].Outputs[?OutputKey==`TableName`].OutputValue' \
    --output text 2>/dev/null || echo "N/A")

# Get Lambda Function Name
LAMBDA_NAME=$(aws cloudformation describe-stacks \
    --stack-name gpu-orchestrator-lambda \
    --query 'Stacks[0].Outputs[?OutputKey==`FunctionName`].OutputValue' \
    --output text 2>/dev/null || echo "N/A")

echo "SQS Queue URL:       $QUEUE_URL"
echo "DynamoDB Table:      $TABLE_NAME"
echo "Lambda Function:     $LAMBDA_NAME"
echo ""

echo "Next Steps:"
echo "1. Update orchestrator .env file with SQS_QUEUE_URL"
echo "2. Update GPU instance adapter service with SQS_QUEUE_URL"
echo "3. Attach IAM role 'gpu-instance-role' to GPU EC2 instance"
echo "4. Deploy orchestrator to Fargate"
echo "5. Deploy adapter script to GPU instance"
echo ""

echo -e "${GREEN}Infrastructure deployment complete!${NC}"
