# Quick Start Guide - GPU Orchestration System

**Version**: 1.0.0
**Last Updated**: 2025-11-18

This is a fast-track guide to get the system running. For detailed information, see individual component READMEs.

---

## System Overview

```
Client → Orchestrator (Fargate) → SQS → GPU Instance (Adapter + ComfyUI)
                ↓                           ↓
            DynamoDB                    DynamoDB
           (PENDING)                  (COMPLETED)
```

**What it does**: Accept GPU processing requests via API, queue them, auto-start GPU instance, process tasks, auto-shutdown after 30 min idle.

---

## Prerequisites Checklist

- [ ] AWS Account with admin access
- [ ] AWS CLI configured (`aws configure`)
- [ ] GPU EC2 instance with ComfyUI installed (see design.md)
- [ ] S3 bucket for results
- [ ] Domain name for API (optional but recommended)

---

## 5-Minute Setup (Local Testing)

### 1. Clone and Install

```bash
cd backend/orchestrator
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Environment

Create `backend/.env`:
```bash
AWS_ACCESS_KEY=your_key
AWS_ACCESS_SECRET=your_secret
AWS_DEFAULT_REGION=us-east-1
SQS_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/ACCOUNT/gpu_tasks_queue
DYNAMODB_TABLE=task_store
GPU_INSTANCE_ID=i-0f0f6fd680921de5f
```

### 3. Create AWS Resources (One-time)

```bash
# Create SQS queue
aws sqs create-queue --queue-name gpu_tasks_queue --region us-east-1

# Create DynamoDB table
aws dynamodb create-table \
  --table-name task_store \
  --attribute-definitions \
    AttributeName=task_id,AttributeType=S \
    AttributeName=status,AttributeType=S \
    AttributeName=created_at,AttributeType=N \
  --key-schema AttributeName=task_id,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --global-secondary-indexes '[{
    "IndexName": "status-created_at-index",
    "KeySchema": [
      {"AttributeName": "status", "KeyType": "HASH"},
      {"AttributeName": "created_at", "KeyType": "RANGE"}
    ],
    "Projection": {"ProjectionType": "ALL"}
  }]' \
  --region us-east-1
```

### 4. Start Orchestrator

```bash
cd backend/orchestrator
python orchestrator_api.py
```

Orchestrator now running on `http://localhost:8080`

### 5. Test API

```bash
# Health check
curl http://localhost:8080/health

# Submit test job
curl -X POST http://localhost:8080/api/v1/camera-angle/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "image_url": "https://example.com/test.jpg",
    "prompt": "convert to top-down view",
    "steps": 8
  }'

# Response: {"job_id": "abc-123", "status": "pending", ...}

# Check status
curl http://localhost:8080/api/v1/jobs/abc-123
```

---

## Deploy to GPU Instance (Adapter)

### 1. Prepare Deployment Package

```bash
cd backend/comfyui-api-service
tar czf adapter.tar.gz \
  sqs_to_comfy_adapter.py \
  sqs-adapter.service \
  setup_adapter.sh
```

### 2. Copy to GPU Instance

```bash
scp -i ~/.ssh/your-key.pem adapter.tar.gz ubuntu@GPU_IP:~
```

### 3. Install on GPU Instance

```bash
ssh ubuntu@GPU_IP

# Extract
tar xzf adapter.tar.gz

# Move to service directory
sudo mkdir -p /home/ubuntu/comfyui_api_service
sudo mv sqs_to_comfy_adapter.py sqs-adapter.service setup_adapter.sh /home/ubuntu/comfyui_api_service/
sudo chown -R ubuntu:ubuntu /home/ubuntu/comfyui_api_service

# Run setup
cd /home/ubuntu/comfyui_api_service
chmod +x setup_adapter.sh
sudo ./setup_adapter.sh
# (Enter SQS Queue URL when prompted)

# Verify running
sudo systemctl status sqs-adapter
```

---

## Deploy Orchestrator to AWS (Production)

### Quick Deploy with Docker + Fargate

```bash
# 1. Create ECR repository
aws ecr create-repository --repository-name gpu-orchestrator

# 2. Login to ECR
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin ACCOUNT.dkr.ecr.us-east-1.amazonaws.com

# 3. Build image
cd backend/orchestrator
docker build -t gpu-orchestrator .

# 4. Tag and push
docker tag gpu-orchestrator:latest ACCOUNT.dkr.ecr.us-east-1.amazonaws.com/gpu-orchestrator:latest
docker push ACCOUNT.dkr.ecr.us-east-1.amazonaws.com/gpu-orchestrator:latest

# 5. Deploy to Fargate (see DEPLOYMENT.md for full ECS setup)
```

---

## Setup Auto-Shutdown (Lambda + CloudWatch)

### 1. Deploy Lambda

```bash
cd backend/orchestrator
zip lambda_shutdown.zip lambda_shutdown.py

aws lambda create-function \
  --function-name shutdown-gpu-lambda \
  --runtime python3.11 \
  --role arn:aws:iam::ACCOUNT:role/lambda-shutdown-role \
  --handler lambda_shutdown.lambda_handler \
  --zip-file fileb://lambda_shutdown.zip \
  --timeout 60 \
  --environment Variables='{GPU_INSTANCE_ID=i-0f0f6fd680921de5f,AWS_REGION=us-east-1}'
```

### 2. Create CloudWatch Alarm

```bash
aws cloudwatch put-metric-alarm \
  --alarm-name QueueEmptyFor30Min \
  --metric-name ApproximateNumberOfMessagesVisible \
  --namespace AWS/SQS \
  --statistic Average \
  --period 300 \
  --evaluation-periods 6 \
  --threshold 0 \
  --comparison-operator LessThanOrEqualToThreshold \
  --dimensions Name=QueueName,Value=gpu_tasks_queue \
  --alarm-actions arn:aws:lambda:us-east-1:ACCOUNT:function:shutdown-gpu-lambda
```

---

## Testing the Complete Flow

### End-to-End Test

```bash
# 1. Ensure GPU instance is stopped
aws ec2 describe-instances --instance-ids i-0f0f6fd680921de5f

# 2. Submit job via orchestrator
curl -X POST http://localhost:8080/api/v1/camera-angle/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "image_url": "s3://your-bucket/test.jpg",
    "prompt": "test",
    "steps": 8
  }'

# Get job_id from response: {"job_id": "xyz-789", ...}

# 3. Watch orchestrator start GPU instance
aws ec2 describe-instances --instance-ids i-0f0f6fd680921de5f
# State should change from "stopped" → "pending" → "running"

# 4. Watch adapter process task (on GPU instance)
ssh ubuntu@GPU_IP
sudo journalctl -u sqs-adapter -f

# 5. Poll job status
curl http://localhost:8080/api/v1/jobs/xyz-789
# Status: pending → processing → completed

# 6. Wait 30 minutes with no new tasks
# GPU instance should auto-shutdown
```

---

## Monitoring Commands

### Check System Health

```bash
# Orchestrator
curl http://localhost:8080/health

# SQS Queue depth
aws sqs get-queue-attributes \
  --queue-url YOUR_QUEUE_URL \
  --attribute-names ApproximateNumberOfMessages

# DynamoDB items
aws dynamodb scan --table-name task_store --select COUNT

# GPU instance state
aws ec2 describe-instances \
  --instance-ids i-0f0f6fd680921de5f \
  --query 'Reservations[0].Instances[0].State.Name'

# Adapter logs
ssh ubuntu@GPU_IP sudo journalctl -u sqs-adapter -f
```

---

## Common Issues & Quick Fixes

### "Failed to create task in database"
```bash
# Check table exists
aws dynamodb describe-table --table-name task_store

# Check IAM permissions
aws sts get-caller-identity
```

### "Failed to queue task"
```bash
# Check queue exists
aws sqs get-queue-url --queue-name gpu_tasks_queue

# Test send message
aws sqs send-message --queue-url YOUR_URL --message-body "test"
```

### "GPU instance not starting"
```bash
# Check instance ID
aws ec2 describe-instances --instance-ids i-0f0f6fd680921de5f

# Start manually
aws ec2 start-instances --instance-ids i-0f0f6fd680921de5f
```

### "Adapter not processing messages"
```bash
# On GPU instance
sudo systemctl status sqs-adapter
sudo journalctl -u sqs-adapter -n 50

# Check ComfyUI API
curl http://localhost:8000/health

# Restart adapter
sudo systemctl restart sqs-adapter
```

---

## File Structure Reference

```
backend/
├── design.md                          # System architecture
├── IMPLEMENTATION_STATUS.md           # Implementation tracking
├── QUICK_START.md                     # This file
│
├── orchestrator/                      # Orchestrator service
│   ├── orchestrator_api.py           # Main FastAPI app
│   ├── requirements.txt              # Python dependencies
│   ├── README.md                     # Detailed guide
│   ├── DEPLOYMENT.md                 # Deployment guide
│   ├── lambda_shutdown.py            # Auto-shutdown Lambda
│   ├── test_ec2.py                   # Test scripts
│   ├── test_start.py
│   ├── test_stop.py
│   └── aws/                          # AWS helper modules
│       ├── ec2.py
│       ├── sqs.py
│       └── dynamodb.py
│
└── comfyui-api-service/              # GPU instance services
    ├── unified_api.py                # ComfyUI API wrapper
    ├── sqs_to_comfy_adapter.py       # SQS adapter
    ├── sqs-adapter.service           # Systemd service
    ├── setup_adapter.sh              # Setup script
    ├── ADAPTER_README.md             # Adapter guide
    └── [other API docs...]
```

---

## Next Steps

1. **Read design.md** - Understand system architecture
2. **Follow DEPLOYMENT.md** - Complete AWS setup
3. **Test locally** - Verify orchestrator works
4. **Deploy adapter** - Set up GPU instance
5. **Deploy orchestrator** - Launch on Fargate
6. **Set up monitoring** - CloudWatch dashboard
7. **Production testing** - End-to-end validation

---

## Support & Documentation

- **Design**: `design.md`
- **Orchestrator**: `orchestrator/README.md`
- **Deployment**: `orchestrator/DEPLOYMENT.md`
- **Adapter**: `comfyui-api-service/ADAPTER_README.md`
- **Status**: `IMPLEMENTATION_STATUS.md`

---

## Cost Estimate

- **GPU Instance**: $1.21/hour × 2-4 hours/day = $72-144/month
- **Fargate**: ~$15/month (0.25 vCPU, 0.5 GB, always on)
- **DynamoDB**: ~$5/month (on-demand)
- **SQS**: Free tier (< 1M requests/month)
- **Lambda**: Free tier (< 1M invocations/month)
- **Data Transfer**: ~$5-10/month

**Total**: $100-180/month

---

**Happy orchestrating!** 🚀
