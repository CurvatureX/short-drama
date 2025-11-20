# Backend Architecture

Complete architecture documentation for the short-drama backend system.

## System Overview

The backend consists of three main services:

1. **Orchestrator** - Task submission and routing
2. **ComfyUI API Service** - GPU-bound image processing (camera angles, style transfer)
3. **Paid API Service** - CPU-bound face manipulation (face masking, face swapping)

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                          Client Applications                         │
│                    (Frontend, CLI, External APIs)                    │
└────────────┬────────────────────────────────┬───────────────────────┘
             │                                │
             ↓                                ↓
    ┌────────────────┐              ┌────────────────┐
    │   Orchestrator │              │   Orchestrator │
    │   (GPU Tasks)  │              │   (CPU Tasks)  │
    │   Port 8080    │              │   Port 8081    │
    └────────┬───────┘              └────────┬───────┘
             │                                │
             │                                │
    ┌────────↓──────────┐          ┌─────────↓─────────┐
    │  SQS Queue        │          │  SQS Queue         │
    │  gpu_tasks_queue  │          │  cpu_tasks_queue   │
    └────────┬──────────┘          └─────────┬─────────┘
             │                                │
             ↓                                ↓
    ┌────────────────────┐          ┌────────────────────┐
    │  SQS Adapter       │          │  SQS Adapter       │
    │  (GPU Instance)    │          │  (CPU Instance)    │
    └────────┬───────────┘          └────────┬───────────┘
             │                                │
             ↓                                ↓
    ┌────────────────────┐          ┌────────────────────┐
    │  ComfyUI API       │          │  Paid API Service  │
    │  Port 8000         │          │  Port 8000         │
    │  + ComfyUI 8188    │          │  (FastAPI)         │
    └────────┬───────────┘          └────────┬───────────┘
             │                                │
             │                                │
             └────────────┬───────────────────┘
                          │
                          ↓
                 ┌────────────────────┐
                 │    DynamoDB        │
                 │    task_store      │
                 │    (Task Status)   │
                 └────────┬───────────┘
                          │
                          ↓
                 ┌────────────────────┐
                 │    S3 + CloudFront │
                 │    (Results)       │
                 └────────────────────┘
```

## Service Details

### 1. Orchestrator

**Location**: `/backend/orchestrator/`

**Purpose**: Receives task requests and routes them to appropriate queues.

**Components**:
- `orchestrator_api.py` - GPU task orchestrator (ComfyUI tasks)
- `cpu_orchestrator_api.py` - CPU task orchestrator (Paid API tasks)

**Endpoints**:

**GPU Tasks** (Port 8080):
- `POST /api/v1/camera-angle/tasks` - Camera angle transformation
- `POST /api/v1/qwen-image-edit/tasks` - Image editing
- `GET /api/v1/tasks/{task_id}` - Task status

**CPU Tasks** (Port 8081):
- `POST /api/v1/face-mask/tasks` - Create face mask
- `POST /api/v1/face-swap/tasks` - Apply face swap
- `POST /api/v1/full-face-swap/tasks` - Full pipeline
- `GET /api/v1/tasks/{task_id}` - Task status

**Flow**:
1. Receive task request via REST API
2. Generate task ID (UUID)
3. Create task record in DynamoDB (status: pending)
4. Send message to appropriate SQS queue
5. Return task ID to client
6. Client polls for status

### 2. ComfyUI API Service

**Location**: `/backend/comfyui-api-service/`

**Purpose**: GPU-accelerated image processing using ComfyUI workflows.

**Instance Type**: GPU instance (g4dn.xlarge, g5.xlarge, etc.)

**Components**:
- `unified_api.py` - REST API wrapper for ComfyUI
- `sqs_to_comfy_adapter.py` - SQS queue consumer
- ComfyUI workflows in `/workflows/`

**Endpoints** (Port 8000):
- `POST /api/v1/camera-angle/jobs` - Camera angle transformation
- `POST /api/v1/qwen-image-edit/jobs` - Image editing (1-3 images)
- `GET /api/v1/jobs/{job_id}` - Job status

**Workflows**:
- `camera-angle-api.json` - Camera perspective transformation
- `qwen-image-edit-api.json` - Image style transfer

**Models**:
- Qwen-Image-Edit with camera angle LoRA
- Qwen-Rapid-AIO-NSFW-v11

### 3. Paid API Service

**Location**: `/backend/paid-api-service/`

**Purpose**: CPU-bound face manipulation using external APIs (QWEN3-VL, SeeDream).

**Instance Type**: CPU instance (t3.medium, t3.large, etc.)

**Components**:
- `api_service.py` - REST API for face manipulation
- `sqs_adapter.py` - SQS queue consumer
- `face_swap.py` - Core business logic
- `image-to-image/seedream.py` - SeeDream API client

**Endpoints** (Port 8000):
- `POST /api/v1/face-mask/jobs` - Create face mask
- `POST /api/v1/face-swap/jobs` - Apply face swap
- `POST /api/v1/full-face-swap/jobs` - Full pipeline
- `GET /api/v1/jobs/{job_id}` - Job status

**External APIs**:
- QWEN3-VL (Dashscope) - Face detection
- SeeDream (Volcano Engine ARK) - Image generation

## Data Flow

### Task Submission Flow

```
Client → Orchestrator → SQS Queue → SQS Adapter → API Service → Result
```

**Detailed Steps**:

1. **Client submits task**
   - POST request to orchestrator
   - Includes task parameters (image URLs, prompts, etc.)

2. **Orchestrator processes request**
   - Generates UUID for task
   - Creates DynamoDB record (status: pending)
   - Sends message to SQS queue
   - Returns task ID to client

3. **SQS Adapter polls queue**
   - Long polling (20 seconds)
   - Receives message
   - Updates DynamoDB (status: processing)

4. **SQS Adapter calls API Service**
   - POST to local API endpoint
   - Receives job ID
   - Stores job ID in DynamoDB

5. **SQS Adapter polls API Service**
   - GET /api/v1/jobs/{job_id}
   - Polls every 2 seconds
   - Waits for completion

6. **API Service processes job**
   - Downloads input images
   - Performs processing (GPU/CPU)
   - Uploads results to S3
   - Updates job status

7. **SQS Adapter finalizes task**
   - Updates DynamoDB with result URL
   - Deletes SQS message
   - Task complete

8. **Client polls for result**
   - GET /api/v1/tasks/{task_id}
   - Receives result URL (CloudFront CDN)

## AWS Infrastructure

### SQS Queues

**GPU Task Queue**:
- Name: `gpu_tasks_queue`
- Visibility Timeout: 300 seconds (5 minutes)
- Dead Letter Queue: `gpu_tasks_dlq`

**CPU Task Queue**:
- Name: `cpu_tasks_queue`
- Visibility Timeout: 600 seconds (10 minutes)
- Dead Letter Queue: `cpu_tasks_dlq`

### DynamoDB

**Table**: `task_store`

**Schema**:
```
Partition Key: task_id (String)
Attributes:
  - status: String (pending, processing, completed, failed)
  - job_type: String (API path)
  - created_at: Number (Unix timestamp)
  - updated_at: Number (Unix timestamp)
  - result_url: String (CloudFront URL)
  - error_message: String (error details)
  - api_job_id: String (internal job ID)
```

**GSI**: `status-created_at-index`
- Partition Key: status
- Sort Key: created_at

### S3 Buckets

**Bucket**: `short-drama-assets`

**Structure**:
```
short-drama-assets/
├── images/
│   ├── comfyui-results/
│   │   ├── camera-angle/{job-id}.png
│   │   └── qwen-image-edit/{job-id}.png
│   └── face_swap/{timestamp}_{id}.png
└── seedream/{timestamp}_{id}.jpg
```

**CloudFront CDN**: `https://d3bg7alr1qwred.cloudfront.net`

## Deployment

### Prerequisites

**All Instances**:
- AWS IAM instance profile with appropriate permissions
- Ubuntu 22.04 LTS
- Python 3.10+

**GPU Instance**:
- NVIDIA GPU (T4, A10G, etc.)
- CUDA 12.1+
- ComfyUI installed

**CPU Instance**:
- No GPU required
- API keys configured (QWEN3-VL, SeeDream)

### IAM Permissions

**GPU Instance Profile**:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject"
      ],
      "Resource": "arn:aws:s3:::short-drama-assets/*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage"
      ],
      "Resource": "arn:aws:sqs:us-east-1:*:gpu_tasks_queue"
    },
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:UpdateItem",
        "dynamodb:GetItem"
      ],
      "Resource": "arn:aws:dynamodb:us-east-1:*:table/task_store"
    }
  ]
}
```

**CPU Instance Profile**: (Same as above, but with `cpu_tasks_queue`)

### Service Installation

**GPU Instance**:
```bash
# ComfyUI API Service
cd /home/ubuntu/comfyui-api-service
./setup_services.sh

# Start services
sudo systemctl start comfyui
sudo systemctl start comfyui-unified-api
sudo systemctl start sqs-adapter
```

**CPU Instance**:
```bash
# Paid API Service
cd /home/ubuntu/paid-api-service
./setup_services.sh

# Start services
sudo systemctl start paid-api
sudo systemctl start sqs-adapter
```

## Monitoring

### Service Health

```bash
# GPU Instance
curl http://localhost:8000/health
sudo systemctl status comfyui-unified-api
sudo systemctl status sqs-adapter

# CPU Instance
curl http://localhost:8000/health
sudo systemctl status paid-api
sudo systemctl status sqs-adapter
```

### Logs

```bash
# GPU Instance
sudo journalctl -u comfyui-unified-api -f
sudo journalctl -u sqs-adapter -f

# CPU Instance
sudo journalctl -u paid-api -f
sudo journalctl -u sqs-adapter -f
```

### Queue Metrics

```bash
# Check queue depth
aws sqs get-queue-attributes \
  --queue-url $QUEUE_URL \
  --attribute-names ApproximateNumberOfMessages

# Check DLQ
aws sqs get-queue-attributes \
  --queue-url $DLQ_URL \
  --attribute-names ApproximateNumberOfMessages
```

## Cost Estimation

### GPU Instance (g4dn.xlarge)
- **Instance**: ~$0.526/hour = ~$380/month
- **Storage**: 100GB EBS = ~$10/month
- **Total**: ~$390/month

### CPU Instance (t3.medium)
- **Instance**: ~$0.042/hour = ~$30/month
- **Storage**: 30GB EBS = ~$3/month
- **Total**: ~$33/month

### API Costs (per 1000 requests)
- **QWEN3-VL**: ~$10
- **SeeDream**: ~$50
- **Total**: ~$60/1000 requests

### AWS Services
- **SQS**: Free tier (1M requests/month)
- **DynamoDB**: Free tier (25 RCU/WCU)
- **S3**: ~$0.023/GB/month
- **CloudFront**: ~$0.085/GB transfer

## Troubleshooting

### Common Issues

**1. SQS messages not being processed**
- Check SQS adapter logs
- Verify queue URL configuration
- Check IAM permissions

**2. Tasks stuck in "processing"**
- Check API service logs
- Verify external API keys
- Check network connectivity

**3. Results not uploaded to S3**
- Check S3 permissions
- Verify bucket name
- Check CloudFront configuration

### Debug Commands

```bash
# Check AWS credentials
aws sts get-caller-identity

# Test SQS access
aws sqs get-queue-attributes --queue-url $QUEUE_URL

# Test DynamoDB access
aws dynamodb describe-table --table-name task_store

# Test S3 access
aws s3 ls s3://short-drama-assets/

# Check service status
systemctl status [service-name]

# View recent logs
journalctl -u [service-name] -n 100
```

## Performance Metrics

### GPU Tasks (ComfyUI)
- **Camera Angle**: ~10-15 seconds
- **Image Edit**: ~5-10 seconds
- **Throughput**: 1 job at a time (GPU memory limit)

### CPU Tasks (Paid API)
- **Face Mask**: ~3-5 seconds
- **Face Swap**: ~8-15 seconds
- **Full Pipeline**: ~12-20 seconds
- **Throughput**: Limited by API rate limits

## Security

### API Keys
- Stored in systemd service environment variables
- Never committed to git
- Rotated regularly

### Network Security
- Services listen on localhost only
- Public access via load balancer (if needed)
- SSL/TLS for external APIs

### IAM Best Practices
- Least privilege principle
- Instance profiles (no hardcoded credentials)
- Separate roles for each service

---

**Last Updated**: 2025-11-19
**Maintained By**: Short Drama Team
