# GPU Task Orchestrator Service

Production-ready async task orchestration system for GPU-accelerated image processing with cost optimization.

**Version**: 1.0.0
**Status**: Production Ready

## Overview

The Orchestrator Service is the **single entry point** for all GPU processing requests. It implements a facade pattern that accepts client requests, queues them in SQS, manages GPU instance lifecycle automatically, and returns results via CDN.

### Key Features

- ✅ **Async by Design**: Returns `202 Accepted` within 1 second
- ✅ **Auto-scaling**: Starts GPU instances on-demand, shuts down after 30 minutes idle
- ✅ **Cost Optimized**: GPU only runs when needed (~$200/month vs $500+ always-on)
- ✅ **RESTful API**: Clean versioned endpoints matching ComfyUI API structure
- ✅ **Reliable**: Uses DynamoDB for state, SQS for queuing, S3+CDN for results
- ✅ **Container-ready**: Docker support for ECS Fargate deployment

## Architecture

```
Client → Orchestrator → SQS Queue → GPU Instance (Adapter) → ComfyUI API → S3 + CDN
           ↓                           ↓                          ↓
       DynamoDB                    DynamoDB                    DynamoDB
       (PENDING)                   (PROCESSING)                (COMPLETED)
```

### Components

**Orchestrator Responsibilities:**
1. Accept API requests (camera-angle, qwen-image-edit)
2. Generate unique `task_id` (UUID)
3. Write `PENDING` status to DynamoDB
4. Send task to SQS queue with request body
5. Start GPU instance if stopped (EC2 API)
6. Return `task_id` immediately (202 Accepted)

**Orchestrator does NOT:**
- Process tasks (handled by GPU instance adapter)
- Shut down instances (handled by CloudWatch + Lambda)
- Store results (handled by ComfyUI API → S3)

**SQS Adapter (on GPU Instance):**
- Polls SQS queue every 20 seconds
- Updates task status to `PROCESSING` in DynamoDB
- Calls ComfyUI Unified API on localhost:8000
- Polls ComfyUI for completion
- Updates task status to `COMPLETED` or `FAILED`
- Stores result CDN URL in DynamoDB

**Auto-Shutdown System:**
- CloudWatch Alarm monitors SQS queue depth
- Triggers Lambda after 30 minutes of empty queue
- Lambda stops GPU instance to save costs

## Prerequisites

### AWS Resources Required

1. **SQS Queue**: `gpu_tasks_queue`
   - Visibility timeout: 300 seconds (5 minutes)
   - Long polling enabled (20 seconds)
   - Dead Letter Queue (DLQ) recommended

2. **DynamoDB Table**: `task_store`
   - Partition key: `task_id` (String)
   - GSI: `status-created_at-index`
     - Partition key: `status` (String)
     - Sort key: `created_at` (Number)
   - TTL: Optional, on `created_at` field (7-30 days)

3. **EC2 GPU Instance**: (e.g., `i-0f0f6fd680921de5f`)
   - Instance type: g4dn.xlarge or g5.xlarge
   - IAM instance profile with SQS/DynamoDB/S3 permissions
   - Must run SQS Adapter + ComfyUI Unified API
   - Security group: Allow outbound to AWS services

4. **IAM Roles**:
   - **Orchestrator Role**: SQS SendMessage, DynamoDB PutItem/GetItem/UpdateItem, EC2 DescribeInstances/StartInstances
   - **GPU Instance Profile**: SQS ReceiveMessage/DeleteMessage, DynamoDB UpdateItem, S3 GetObject/PutObject

5. **Lambda Function**: `shutdown-gpu-lambda`
   - Triggered by CloudWatch Alarm
   - Stops GPU instance after idle period

6. **CloudWatch Alarm**: `QueueEmptyFor30Min`
   - Metric: SQS ApproximateNumberOfMessagesVisible
   - Threshold: 0 messages for 30 minutes
   - Action: Trigger Lambda

## Installation

### Local Development

```bash
cd backend/orchestrator

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
export AWS_DEFAULT_REGION=us-east-1
export SQS_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/ACCOUNT_ID/gpu_tasks_queue
export DYNAMODB_TABLE=task_store
export GPU_INSTANCE_ID=i-0f0f6fd680921de5f

# Run locally
python orchestrator_api.py
```

The service will start on `http://localhost:8080`

### Docker Build

```bash
# Build image
docker build -t gpu-orchestrator:latest .

# Run locally
docker run -p 8080:8080 \
  -e AWS_DEFAULT_REGION=us-east-1 \
  -e SQS_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/ACCOUNT_ID/gpu_tasks_queue \
  -e DYNAMODB_TABLE=task_store \
  -e GPU_INSTANCE_ID=i-0f0f6fd680921de5f \
  gpu-orchestrator:latest

# Test
curl http://localhost:8080/health
```

## API Endpoints

### Camera Angle Transformation

```bash
POST /api/v1/camera-angle/jobs
Content-Type: application/json

{
  "image_url": "https://short-drama-assets.s3.amazonaws.com/images/input.jpg",
  "prompt": "将镜头转为俯视",
  "seed": 12345,        // optional
  "steps": 8            // optional, default: 8
}
```

**Response** (202 Accepted):
```json
{
  "job_id": "a1b2c3d4-5e6f-7g8h-9i0j-k1l2m3n4o5p6",
  "status": "pending",
  "result_s3_uri": null,
  "error": null
}
```

### Image Editing (Qwen-Rapid-AIO)

```bash
POST /api/v1/qwen-image-edit/jobs
Content-Type: application/json

{
  "image_url": "https://short-drama-assets.s3.amazonaws.com/images/main.jpg",
  "image2_url": "https://short-drama-assets.s3.amazonaws.com/images/ref1.jpg",  // optional
  "image3_url": "https://short-drama-assets.s3.amazonaws.com/images/ref2.jpg",  // optional
  "prompt": "black and white sketch",
  "steps": 4,                    // optional, default: 4
  "cfg": 1.0,                    // optional
  "sampler_name": "sa_solver",   // optional
  "scheduler": "beta",           // optional
  "denoise": 1.0                 // optional
}
```

### Check Job Status

```bash
GET /api/v1/jobs/{job_id}
```

**Response** (200 OK):
```json
{
  "job_id": "a1b2c3d4-5e6f-7g8h-9i0j-k1l2m3n4o5p6",
  "status": "completed",
  "result_s3_uri": "https://d3bg7alr1qwred.cloudfront.net/images/comfyui-results/qwen-image-edit/job-id.png",
  "error": null
}
```

**Status values**:
- `pending`: Task queued, waiting for GPU
- `processing`: GPU is processing the task
- `completed`: Processing finished, result available
- `failed`: Processing failed, check error field

### Health Check

```bash
GET /health
```

**Response**:
```json
{
  "status": "healthy",
  "service": "gpu-task-orchestrator",
  "version": "1.0.0"
}
```

## Deployment Options

### Option 1: AWS ECS Fargate (Recommended)

**Benefits:**
- Serverless container management
- Auto-restart on crashes
- Load balancing with ALB
- ~$68/month (single task)

**Deployment Steps:**

```bash
cd backend/infra

# Set AWS credentials
export CDK_DEFAULT_ACCOUNT=982081090398
export CDK_DEFAULT_REGION=us-east-1

# Deploy all infrastructure (including ECS)
cdk deploy --all --require-approval never

# Or deploy ECS stack only (if others already deployed)
cdk deploy gpu-orchestrator-ecs
```

**Infrastructure Created:**
- VPC with public/private subnets
- Application Load Balancer (ALB)
- ECS Cluster + Fargate Service (1 task)
- ECR Repository for Docker images
- CloudWatch Logs

**Access:**
- ALB DNS: `gpu-orchestrator-alb-XXXXXX.us-east-1.elb.amazonaws.com`
- Health: `http://<ALB-DNS>/health`

### Option 2: EC2 Instance

**Benefits:**
- Lower cost (~$12/month for t4g.small ARM)
- Simple deployment

**Deployment Steps:**

```bash
# Launch EC2 instance
aws ec2 run-instances --instance-type t4g.small --image-id ami-XXXXX

# SSH to instance
ssh -i key.pem ubuntu@instance-ip

# Install dependencies
sudo apt update
sudo apt install -y python3 python3-pip python3-venv

# Clone repo and setup
cd /opt
sudo git clone <repo>
cd backend/orchestrator
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Create systemd service
sudo nano /etc/systemd/system/orchestrator.service
```

**systemd service file:**
```ini
[Unit]
Description=GPU Task Orchestrator
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/backend/orchestrator
Environment="AWS_DEFAULT_REGION=us-east-1"
Environment="SQS_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/982081090398/gpu_tasks_queue"
Environment="DYNAMODB_TABLE=task_store"
Environment="GPU_INSTANCE_ID=i-0f0f6fd680921de5f"
ExecStart=/opt/backend/orchestrator/venv/bin/python /opt/backend/orchestrator/orchestrator_api.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
# Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable orchestrator
sudo systemctl start orchestrator

# Check status
sudo systemctl status orchestrator
curl http://localhost:8080/health
```

### Option 3: Docker Compose (Development)

```bash
cd backend/orchestrator

# Start service
docker-compose up -d

# View logs
docker-compose logs -f

# Stop service
docker-compose down
```

## Testing

### Local Testing

```bash
# Start orchestrator locally
python orchestrator_api.py

# In another terminal - test health
curl http://localhost:8080/health

# Submit camera angle job
curl -X POST http://localhost:8080/api/v1/camera-angle/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "image_url": "https://short-drama-assets.s3.amazonaws.com/images/in-the-mood-for-love.jpg",
    "prompt": "将镜头转为俯视",
    "steps": 8
  }'

# Get job ID from response, then check status
curl http://localhost:8080/api/v1/jobs/{job_id}
```

### End-to-End Testing

```bash
# Submit job and wait for completion
JOB_ID=$(curl -s -X POST http://localhost:8080/api/v1/qwen-image-edit/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "image_url": "https://short-drama-assets.s3.amazonaws.com/images/in-the-mood-for-love.jpg",
    "prompt": "black and white sketch",
    "steps": 4
  }' | jq -r '.job_id')

echo "Job ID: $JOB_ID"

# Poll status every 5 seconds
while true; do
  STATUS=$(curl -s http://localhost:8080/api/v1/jobs/$JOB_ID | jq -r '.status')
  echo "Status: $STATUS"

  if [ "$STATUS" = "completed" ] || [ "$STATUS" = "failed" ]; then
    curl -s http://localhost:8080/api/v1/jobs/$JOB_ID | jq .
    break
  fi

  sleep 5
done
```

### Python Client Example

```python
import requests
import time

BASE_URL = "http://localhost:8080/api/v1"

# Submit job
response = requests.post(
    f"{BASE_URL}/qwen-image-edit/jobs",
    json={
        "image_url": "https://short-drama-assets.s3.amazonaws.com/images/input.jpg",
        "prompt": "artistic sketch",
        "steps": 4
    }
)
job_id = response.json()['job_id']
print(f"Job submitted: {job_id}")

# Poll for completion
while True:
    status_response = requests.get(f"{BASE_URL}/jobs/{job_id}")
    status_data = status_response.json()

    print(f"Status: {status_data['status']}")

    if status_data['status'] == 'completed':
        print(f"Result: {status_data['result_s3_uri']}")
        break
    elif status_data['status'] == 'failed':
        print(f"Error: {status_data['error']}")
        break

    time.sleep(5)
```

## Monitoring

### Key Metrics

**Orchestrator Metrics:**
- API response time (should be < 1 second)
- Request rate (requests per minute)
- Error rate (failed to queue tasks)

**SQS Metrics:**
- `ApproximateNumberOfMessagesVisible` (queue depth)
- `ApproximateAgeOfOldestMessage` (backlog age)
- Should be 0 most of the time

**DynamoDB Metrics:**
- Read/Write capacity units
- Throttled requests (should be 0)

**GPU Instance Metrics:**
- State (running/stopped)
- Uptime (should match job processing time + 30 min)

### CloudWatch Logs

```bash
# Orchestrator logs (if running in ECS)
aws logs tail /ecs/gpu-orchestrator --follow

# Adapter logs (on GPU instance)
ssh -i key.pem ubuntu@gpu-instance "sudo journalctl -u sqs-adapter -f"

# ComfyUI API logs (on GPU instance)
ssh -i key.pem ubuntu@gpu-instance "sudo journalctl -u comfyui-unified-api -f"
```

## Troubleshooting

### Task Stuck in "pending"

**Symptoms**: Job status remains `pending` for > 5 minutes

**Checks:**
```bash
# 1. Check GPU instance state
aws ec2 describe-instances --instance-ids i-0f0f6fd680921de5f \
  --query 'Reservations[0].Instances[0].State.Name'

# 2. Check SQS queue has messages
aws sqs get-queue-attributes \
  --queue-url https://sqs.us-east-1.amazonaws.com/982081090398/gpu_tasks_queue \
  --attribute-names ApproximateNumberOfMessages

# 3. Check adapter is running on GPU instance
ssh -i key.pem ubuntu@gpu-instance "sudo systemctl status sqs-adapter"

# 4. Check adapter logs for errors
ssh -i key.pem ubuntu@gpu-instance "sudo journalctl -u sqs-adapter -n 50"
```

**Solutions:**
- Start GPU instance manually if stopped: `aws ec2 start-instances --instance-ids i-XXX`
- Restart adapter: `ssh gpu-instance "sudo systemctl restart sqs-adapter"`
- Check IAM permissions on GPU instance

### Failed to Create Task in Database

**Error**: `Failed to create task in database`

**Checks:**
```bash
# 1. Verify table exists
aws dynamodb describe-table --table-name task_store

# 2. Check IAM permissions
aws sts get-caller-identity
```

**Solutions:**
- Create table if missing: `cdk deploy gpu-orchestrator-dynamodb`
- Fix IAM role permissions: Check orchestrator role has `dynamodb:PutItem`

### Failed to Queue Task

**Error**: `Failed to queue task`

**Checks:**
```bash
# 1. Verify queue exists
aws sqs get-queue-url --queue-name gpu_tasks_queue

# 2. Test queue access
aws sqs send-message \
  --queue-url https://sqs.us-east-1.amazonaws.com/982081090398/gpu_tasks_queue \
  --message-body "test"
```

**Solutions:**
- Fix SQS_QUEUE_URL environment variable
- Check IAM permissions: `sqs:SendMessage`

### GPU Instance Not Starting

**Symptoms**: Task pending, GPU instance remains stopped

**Checks:**
```bash
# Check instance state
aws ec2 describe-instances --instance-ids i-0f0f6fd680921de5f

# Check orchestrator logs for EC2 API errors
docker logs <container-id>  # If running in Docker
journalctl -u orchestrator  # If running as systemd
```

**Solutions:**
- Verify GPU_INSTANCE_ID is correct
- Check orchestrator IAM role has `ec2:StartInstances`
- Verify instance is not terminated

## File Structure

```
backend/orchestrator/
├── README.md                      # This file
├── orchestrator_api.py            # Main orchestrator service
├── sqs_to_comfy_adapter.py        # SQS adapter (deployed to GPU instance)
├── lambda_shutdown.py             # Auto-shutdown Lambda function
├── requirements.txt               # Python dependencies
├── Dockerfile                     # Container image
├── docker-compose.yml             # Local development
├── .dockerignore                  # Docker build exclusions
├── deploy.sh                      # Deployment helper script
├── aws/                           # Helper modules
│   ├── __init__.py
│   ├── dynamodb.py                # DynamoDB operations
│   ├── ec2.py                     # EC2 lifecycle management
│   └── sqs.py                     # SQS queue operations
└── test_*.py                      # Test scripts
```

## Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `AWS_DEFAULT_REGION` | AWS region | `us-east-1` |
| `SQS_QUEUE_URL` | SQS queue URL | `https://sqs.us-east-1.amazonaws.com/123/gpu_tasks_queue` |
| `DYNAMODB_TABLE` | DynamoDB table name | `task_store` |
| `GPU_INSTANCE_ID` | EC2 GPU instance ID | `i-0f0f6fd680921de5f` |

## Cost Breakdown

### Current Setup (~$200/month)

- **GPU Instance** (g4dn.xlarge): ~$150/month (avg 20% uptime)
- **Orchestrator** (ECS Fargate 1 task): ~$68/month
- **DynamoDB** (on-demand): ~$1/month
- **SQS**: ~$0.50/month
- **S3 + CloudFront**: ~$5/month
- **Data transfer**: ~$10/month

### vs Always-On GPU (~$500/month)

- **GPU Instance** (g4dn.xlarge 24/7): ~$450/month
- **Orchestrator**: ~$68/month (same)
- **Other services**: ~$16.50/month (same)

**Savings**: ~$300/month (60% reduction)

## Related Documentation

- **Infrastructure CDK**: `../infra/`
- **ComfyUI API Service**: `../comfyui-api-service/README.md`
- **Design Document**: `../design.md`

## Version History

- **v1.0.0** (2025-11-18): Production release with ECS deployment support
- **v0.9.0** (2025-11-17): Beta release with local testing
- **v0.1.0** (2025-11-13): Initial implementation

---

**Maintained By**: Short Drama Team
**Last Updated**: 2025-11-18
**License**: Proprietary - All Rights Reserved
