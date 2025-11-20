# CDK Quick Start - 5 Minutes to Deploy

This guide gets your infrastructure deployed in 5 minutes.

---

## Prerequisites (2 minutes)

```bash
# Install AWS CDK CLI
npm install -g aws-cdk

# Configure AWS credentials
aws configure
# Enter: Access Key ID, Secret Access Key, Region (us-east-1)

# Verify
aws sts get-caller-identity
cdk --version
```

---

## Deploy (3 minutes)

### Option 1: Automated Script

```bash
cd backend/infra
./deploy.sh
```

The script will:
- ✅ Check prerequisites
- ✅ Setup Python environment
- ✅ Bootstrap CDK (if needed)
- ✅ Deploy all stacks
- ✅ Show outputs

### Option 2: Manual Commands

```bash
cd backend/infra

# Setup Python environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Set AWS account/region
export CDK_DEFAULT_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
export CDK_DEFAULT_REGION=us-east-1

# Bootstrap CDK (one-time)
cdk bootstrap

# Deploy all stacks
cdk deploy --all
```

---

## What Gets Deployed

| Stack | Resources | Time |
|-------|-----------|------|
| sqs | SQS Queue + DLQ | 30s |
| dynamodb | DynamoDB Table + GSI | 1m |
| iam | 3 IAM Roles | 30s |
| lambda | Lambda Function | 1m |
| alarm | CloudWatch Alarm | 30s |

**Total deployment time**: ~3-5 minutes

---

## Verify Deployment

```bash
# Check SQS queue
aws sqs get-queue-url --queue-name gpu_tasks_queue

# Check DynamoDB table
aws dynamodb describe-table --table-name task_store

# Check Lambda function
aws lambda get-function --function-name shutdown-gpu-lambda

# Check all stacks
cdk list
```

---

## Get Stack Outputs

```bash
# Get SQS Queue URL
aws cloudformation describe-stacks \
  --stack-name gpu-orchestrator-sqs \
  --query 'Stacks[0].Outputs'

# Or use CDK
cdk deploy gpu-orchestrator-sqs --outputs-file outputs.json
cat outputs.json
```

---

## Update Environment Files

After deployment, update these files with the stack outputs:

### 1. Orchestrator `.env`

```bash
# backend/.env
SQS_QUEUE_URL=<output from gpu-orchestrator-sqs>
DYNAMODB_TABLE=task_store
GPU_INSTANCE_ID=i-0f0f6fd680921de5f
```

### 2. Adapter Service File

```bash
# On GPU instance: /etc/systemd/system/sqs-adapter.service
Environment="SQS_QUEUE_URL=<output from gpu-orchestrator-sqs>"
Environment="DYNAMODB_TABLE=task_store"
```

---

## Attach IAM Role to GPU Instance

```bash
# Get instance profile ARN
aws cloudformation describe-stacks \
  --stack-name gpu-orchestrator-iam \
  --query 'Stacks[0].Outputs[?OutputKey==`GpuInstanceProfileArn`].OutputValue' \
  --output text

# Attach to EC2 instance
aws ec2 associate-iam-instance-profile \
  --instance-id i-0f0f6fd680921de5f \
  --iam-instance-profile Name=gpu-instance-profile
```

---

## Test Infrastructure

```bash
# Send test message to SQS
aws sqs send-message \
  --queue-url $(aws sqs get-queue-url --queue-name gpu_tasks_queue --query 'QueueUrl' --output text) \
  --message-body '{"task_id":"test-123","api_path":"/test","request_body":{}}'

# Verify message in queue
aws sqs get-queue-attributes \
  --queue-url $(aws sqs get-queue-url --queue-name gpu_tasks_queue --query 'QueueUrl' --output text) \
  --attribute-names ApproximateNumberOfMessages

# Test Lambda function
aws lambda invoke \
  --function-name shutdown-gpu-lambda \
  --payload '{"source":"aws.cloudwatch","detail":{"state":{"value":"ALARM"}}}' \
  response.json
cat response.json
```

---

## Common Issues

### "CDK not bootstrapped"

```bash
cdk bootstrap aws://ACCOUNT_ID/us-east-1
```

### "Permission denied"

Your AWS user needs these permissions:
- CloudFormation (full)
- SQS (full)
- DynamoDB (full)
- IAM (full)
- Lambda (full)
- CloudWatch (full)

### "Stack already exists"

```bash
# Update existing stack
cdk deploy gpu-orchestrator-sqs

# Or destroy and recreate
cdk destroy gpu-orchestrator-sqs
cdk deploy gpu-orchestrator-sqs
```

---

## Cleanup

```bash
# Destroy all infrastructure
cdk destroy --all

# Note: DynamoDB table and DLQ won't be deleted (RemovalPolicy.RETAIN)
# Delete manually if needed:
aws dynamodb delete-table --table-name task_store
aws sqs delete-queue --queue-url <dlq-url>
```

---

## Cost

**Monthly cost**: ~$5 (mostly DynamoDB)
- SQS: Free tier
- DynamoDB: ~$5
- Lambda: Free tier
- CloudWatch: Free tier

---

## Next Steps

1. ✅ **Infrastructure deployed**
2. → Deploy orchestrator to Fargate (see `../orchestrator/DEPLOYMENT.md`)
3. → Deploy adapter to GPU instance (see `../comfyui-api-service/ADAPTER_README.md`)
4. → Test end-to-end workflow (see `../QUICK_START.md`)

---

## Full Documentation

- **Detailed CDK Guide**: `README.md`
- **Stack Details**: `stacks/` directory
- **Main Design**: `../design.md`
- **Deployment Guide**: `../orchestrator/DEPLOYMENT.md`

---

**Ready to deploy?** Run `./deploy.sh` and you're done in 5 minutes! 🚀
