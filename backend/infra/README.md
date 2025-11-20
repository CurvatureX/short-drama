# AWS CDK Infrastructure - GPU Orchestration System

**CDK Version**: 2.100.0
**Language**: Python 3.11+
**Purpose**: Infrastructure as Code for GPU task orchestration system

---

## Overview

This CDK app defines all AWS infrastructure needed for the GPU orchestration system:

- **SQS Queue** + DLQ for task queuing
- **DynamoDB Table** with GSI for task state
- **IAM Roles** for orchestrator, GPU instance, and Lambda
- **Lambda Function** for auto-shutdown
- **CloudWatch Alarm** for 30-minute idle detection

---

## Architecture

```
CDK Stacks:
├── SqsStack           → SQS Queue + DLQ
├── DynamoDbStack      → DynamoDB Table + GSI
├── IamStack           → IAM Roles (depends on SQS + DynamoDB)
├── LambdaStack        → Lambda Function (depends on IAM)
└── AlarmStack         → CloudWatch Alarm (depends on Lambda + SQS)
```

**Stack Dependencies:**
```
SqsStack ────┐
             ├──→ IamStack ──→ LambdaStack ──→ AlarmStack
DynamoDbStack┘                      ↑
                                    │
SqsStack ───────────────────────────┘
```

---

## Prerequisites

### 1. Install AWS CDK

```bash
# Install Node.js (CDK CLI requires it)
# macOS
brew install node

# Ubuntu/Debian
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt-get install -y nodejs

# Install CDK CLI globally
npm install -g aws-cdk

# Verify installation
cdk --version
```

### 2. Configure AWS Credentials

```bash
# Option 1: AWS CLI
aws configure

# Option 2: Environment variables
export AWS_ACCESS_KEY_ID=your_key
export AWS_SECRET_ACCESS_KEY=your_secret
export AWS_DEFAULT_REGION=us-east-1

# Verify credentials
aws sts get-caller-identity
```

### 3. Bootstrap CDK (One-time per account/region)

```bash
# Bootstrap CDK in your AWS account
cdk bootstrap aws://ACCOUNT-ID/us-east-1

# This creates:
# - S3 bucket for CDK assets
# - IAM roles for CDK deployments
# - ECR repository for Docker images
```

---

## Installation

### 1. Setup Python Environment

```bash
cd backend/infra

# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
# macOS/Linux:
source .venv/bin/activate
# Windows:
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Verify CDK Setup

```bash
# List all stacks
cdk list

# Expected output:
# gpu-orchestrator-sqs
# gpu-orchestrator-dynamodb
# gpu-orchestrator-iam
# gpu-orchestrator-lambda
# gpu-orchestrator-alarm
```

---

## Configuration

### Environment Variables

Set these before deploying:

```bash
# Required
export CDK_DEFAULT_ACCOUNT=123456789012
export CDK_DEFAULT_REGION=us-east-1

# Optional: Override GPU instance ID
export CDK_CONTEXT_GPU_INSTANCE_ID=i-0f0f6fd680921de5f
```

### CDK Context

Edit `cdk.json` to customize:

```json
{
  "context": {
    "gpu_instance_id": "i-0f0f6fd680921de5f",
    "environment": "dev"
  }
}
```

---

## Deployment

### Quick Deploy (All Stacks)

```bash
# Synthesize CloudFormation templates
cdk synth

# Deploy all stacks
cdk deploy --all

# Deploy with auto-approval (skip confirmations)
cdk deploy --all --require-approval never
```

### Deploy Individual Stacks

```bash
# Deploy in dependency order

# 1. SQS Queue
cdk deploy gpu-orchestrator-sqs

# 2. DynamoDB Table
cdk deploy gpu-orchestrator-dynamodb

# 3. IAM Roles
cdk deploy gpu-orchestrator-iam

# 4. Lambda Function
cdk deploy gpu-orchestrator-lambda

# 5. CloudWatch Alarm
cdk deploy gpu-orchestrator-alarm
```

### View Deployment Progress

CDK will show:
- Resources being created/updated/deleted
- CloudFormation events
- Stack outputs (Queue URL, Table Name, etc.)

---

## Stack Details

### 1. SQS Stack

**Creates:**
- Main queue: `gpu_tasks_queue`
  - Visibility timeout: 300 seconds (5 min)
  - Receive wait time: 20 seconds (long polling)
  - Retention: 1 day
- Dead Letter Queue: `gpu_tasks_queue_dlq`
  - Max receive count: 3 (retry 3 times)
  - Retention: 14 days

**Outputs:**
- `QueueUrl`: URL of main queue
- `QueueArn`: ARN of main queue
- `DLQUrl`: URL of DLQ

### 2. DynamoDB Stack

**Creates:**
- Table: `task_store`
  - Partition key: `task_id` (String)
  - Billing: PAY_PER_REQUEST
  - Point-in-time recovery: Enabled
  - TTL attribute: `ttl` (optional)
- GSI: `status-created_at-index`
  - Partition key: `status` (String)
  - Sort key: `created_at` (Number)

**Outputs:**
- `TableName`: Name of table
- `TableArn`: ARN of table

### 3. IAM Stack

**Creates:**
- `orchestrator-task-role`
  - SQS: SendMessage, GetQueueAttributes
  - DynamoDB: PutItem, GetItem, UpdateItem, Query
  - EC2: DescribeInstances, StartInstances
- `gpu-instance-role`
  - SQS: ReceiveMessage, DeleteMessage, ChangeMessageVisibility
  - DynamoDB: GetItem, UpdateItem
  - S3: GetObject, PutObject
- `lambda-gpu-shutdown-role`
  - EC2: DescribeInstances, StopInstances
  - CloudWatch Logs: CreateLogGroup, CreateLogStream, PutLogEvents

**Outputs:**
- Role ARNs for each role
- Instance profile ARN

### 4. Lambda Stack

**Creates:**
- Function: `shutdown-gpu-lambda`
  - Runtime: Python 3.11
  - Memory: 128 MB
  - Timeout: 60 seconds
  - Code: `backend/orchestrator/lambda_shutdown.py`
  - Environment: GPU_INSTANCE_ID, AWS_REGION

**Outputs:**
- `FunctionArn`: ARN of Lambda function
- `FunctionName`: Name of function

### 5. Alarm Stack

**Creates:**
- Alarm: `QueueEmptyFor30Min`
  - Metric: ApproximateNumberOfMessagesVisible
  - Threshold: 0
  - Evaluation: 6 periods × 5 min = 30 min
  - Action: Invoke Lambda function

**Outputs:**
- `AlarmName`: Name of alarm
- `AlarmArn`: ARN of alarm

---

## Useful Commands

### CDK Commands

```bash
# Synthesize CloudFormation templates
cdk synth

# Show differences between deployed and local
cdk diff

# Deploy specific stack
cdk deploy gpu-orchestrator-sqs

# Destroy all stacks (DANGEROUS!)
cdk destroy --all

# List all stacks
cdk list

# Show stack outputs
aws cloudformation describe-stacks \
  --stack-name gpu-orchestrator-sqs \
  --query 'Stacks[0].Outputs'
```

### Verify Deployment

```bash
# Check SQS queue
aws sqs get-queue-url --queue-name gpu_tasks_queue

# Check DynamoDB table
aws dynamodb describe-table --table-name task_store

# Check Lambda function
aws lambda get-function --function-name shutdown-gpu-lambda

# Check CloudWatch alarm
aws cloudwatch describe-alarms --alarm-names QueueEmptyFor30Min

# Test Lambda function
aws lambda invoke \
  --function-name shutdown-gpu-lambda \
  --payload '{"source":"test"}' \
  response.json
```

---

## Cost Estimation

### Monthly Costs (Estimated)

| Resource | Usage | Cost |
|----------|-------|------|
| SQS Queue | 1M requests | Free tier |
| DynamoDB | 1M read/write | ~$5 |
| Lambda | 100K invocations | Free tier |
| CloudWatch Alarm | 1 alarm | Free tier |
| **Total** | | **~$5/month** |

**Notes:**
- GPU instance cost NOT included (managed separately)
- Free tier applies for first 12 months
- Actual cost depends on usage

---

## Updating Infrastructure

### Modify Stack Code

1. Edit stack files in `stacks/`
2. Test locally: `cdk synth`
3. Preview changes: `cdk diff`
4. Deploy: `cdk deploy`

### Example: Change Queue Visibility Timeout

```python
# In stacks/sqs_stack.py
self.queue = sqs.Queue(
    # ...
    visibility_timeout=Duration.seconds(600),  # Changed from 300 to 600
)
```

```bash
# Preview changes
cdk diff gpu-orchestrator-sqs

# Deploy
cdk deploy gpu-orchestrator-sqs
```

---

## Troubleshooting

### "cdk command not found"

```bash
npm install -g aws-cdk
```

### "Unable to resolve AWS account"

```bash
# Set environment variables
export CDK_DEFAULT_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
export CDK_DEFAULT_REGION=us-east-1
```

### "Stack already exists"

```bash
# If stack exists but not managed by CDK
# Import existing resources or delete and recreate
cdk import gpu-orchestrator-sqs
```

### "Lambda deployment failed"

```bash
# Check Lambda code path
ls ../orchestrator/lambda_shutdown.py

# Re-synthesize
cdk synth gpu-orchestrator-lambda
```

### "Permission denied"

```bash
# Check IAM permissions
aws sts get-caller-identity

# Ensure you have CloudFormation permissions
```

---

## Security Best Practices

### 1. Least Privilege IAM

- IAM roles follow principle of least privilege
- Resource-specific permissions where possible
- Tag-based conditions for EC2 operations

### 2. Encryption

```python
# Add encryption to SQS queue (in sqs_stack.py)
from aws_cdk import aws_kms as kms

kms_key = kms.Key(self, "QueueKey", enable_key_rotation=True)

self.queue = sqs.Queue(
    # ...
    encryption=sqs.QueueEncryption.KMS,
    encryption_master_key=kms_key,
)
```

### 3. Point-in-Time Recovery

DynamoDB already has PITR enabled:
```python
point_in_time_recovery=True,
```

---

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Deploy CDK

on:
  push:
    branches: [main]
    paths:
      - 'backend/infra/**'

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2

      - uses: actions/setup-node@v2
        with:
          node-version: '18'

      - uses: actions/setup-python@v2
        with:
          python-version: '3.11'

      - name: Install CDK
        run: npm install -g aws-cdk

      - name: Install dependencies
        run: |
          cd backend/infra
          pip install -r requirements.txt

      - name: Deploy
        env:
          AWS_ACCESS_KEY_ID: ${{ secrets.AWS_ACCESS_KEY_ID }}
          AWS_SECRET_ACCESS_KEY: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
        run: |
          cd backend/infra
          cdk deploy --all --require-approval never
```

---

## Cleanup

### Destroy All Resources

```bash
# WARNING: This deletes all infrastructure!
cdk destroy --all

# Destroy specific stack
cdk destroy gpu-orchestrator-alarm
```

**Note:** DynamoDB table and DLQ have `RemovalPolicy.RETAIN` - they won't be deleted automatically to prevent data loss.

---

## Next Steps

1. **Deploy Infrastructure**: Run `cdk deploy --all`
2. **Attach IAM Role to GPU Instance**: See GPU setup guide
3. **Deploy Orchestrator**: Build and deploy Fargate service
4. **Deploy Adapter**: Copy adapter script to GPU instance
5. **Test End-to-End**: Submit test job and verify workflow

---

## Related Documentation

- **Main Design**: `../design.md`
- **Orchestrator**: `../orchestrator/README.md`
- **Deployment Guide**: `../orchestrator/DEPLOYMENT.md`
- **Implementation Status**: `../IMPLEMENTATION_STATUS.md`

---

## Docker Compose (Canvas Service)

A compose file is provided to run the image-upload canvas backend locally.

Steps:
- Ensure you have Docker installed
- Set environment variables for Supabase and S3
- Start the service

```bash
cd backend/infra
export SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=...
export S3_BUCKET=your-bucket AWS_DEFAULT_REGION=us-east-1
docker compose up --build
```

Service runs at `http://localhost:9000`.

---

## Support

For issues:
1. Check CloudFormation console for stack events
2. Review CDK synthesis output: `cdk synth`
3. Check AWS service quotas
4. Verify IAM permissions

---

## License

Proprietary - All Rights Reserved
