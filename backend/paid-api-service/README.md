# Paid API Service

Production-ready REST API service for CPU-bound face manipulation tasks using QWEN3-VL and SeeDream (Doubao).

## Overview

A unified API service that provides face masking and face swapping capabilities. Deployed on CPU instances and integrated with AWS SQS for distributed task processing.

**Architecture**: Similar to `comfyui-api-service` but for CPU-bound paid API tasks.

## Features

- ✅ **Face Masking**: Create black elliptical masks on detected faces using QWEN3-VL
- ✅ **Face Swapping**: Apply face swap using SeeDream (Doubao) image-to-image API
- ✅ **Full Pipeline**: Combined face masking + face swapping
- ✅ **RESTful API**: Standard REST patterns with job-based architecture
- ✅ **S3 Integration**: CloudFront CDN URLs for all results
- ✅ **SQS Orchestration**: Distributed processing via SQS adapter
- ✅ **Auto-restart**: Systemd managed services

## Architecture

```
┌─────────────────┐      ┌──────────────┐      ┌─────────────────┐
│  Orchestrator   │─────→│  SQS Queue   │─────→│  SQS Adapter    │
│  (ECS/Local)    │      │ (CPU Tasks)  │      │  (CPU Instance) │
└─────────────────┘      └──────────────┘      └─────────────────┘
                                                        │
                                                        ↓
                                                ┌─────────────────┐
                                                │  Paid API       │
                                                │  Service        │
                                                │  (Port 8000)    │
                                                └─────────────────┘
                                                        │
                                                        ↓
                                                ┌─────────────────┐
                                                │ QWEN3-VL API    │
                                                │ SeeDream API    │
                                                │ S3 + CDN        │
                                                └─────────────────┘
```

## Components

### 1. API Service (`api_service.py`)
FastAPI server exposing face manipulation endpoints.

**Port**: 8000
**Endpoints**:
- `/api/v1/face-mask/jobs` - Create face mask
- `/api/v1/face-swap/jobs` - Apply face swap
- `/api/v1/full-face-swap/jobs` - Full pipeline
- `/api/v1/jobs/{job_id}` - Get job status

### 2. SQS Adapter (`sqs_adapter.py`)
Polls CPU task queue and forwards to local API.

**Function**: Bridge between SQS and local API
**Polling**: 20 second long polling
**Timeout**: 10 minutes per task

### 3. Face Swap Module (`face_swap.py`)
Core business logic for face manipulation.

**Functions**:
- `create_face_mask()` - Detect face and create mask
- `apply_face_swap()` - Swap face using SeeDream
- `swap_with_seedream()` - Full pipeline

### 4. SeeDream Client (`image-to-image/seedream.py`)
Python client for Volcano Engine ARK API.

**Features**:
- Auto S3 upload
- Multiple aspect ratios
- Batch generation support

## API Reference

### 1. Face Mask API

**Endpoint**: `POST /api/v1/face-mask/jobs`

Creates a black elliptical mask on detected face.

**Request**:
```json
{
  "image_url": "https://example.com/person.jpg",
  "face_index": 0
}
```

**Response**:
```json
{
  "job_id": "uuid-string",
  "status": "pending"
}
```

**What it does**:
1. Downloads source image
2. Uses QWEN3-VL to detect faces
3. Creates black elliptical mask on specified face
4. Uploads masked image to S3
5. Returns CloudFront URL

### 2. Face Swap API

**Endpoint**: `POST /api/v1/face-swap/jobs`

Applies face swap to a pre-masked image.

**Request**:
```json
{
  "masked_image_url": "https://cdn.cloudfront.net/masked.png",
  "target_face_url": "https://example.com/target.jpg",
  "prompt": "Replace the black masked face...",
  "size": "2048x2048"
}
```

**Response**:
```json
{
  "job_id": "uuid-string",
  "status": "pending"
}
```

**What it does**:
1. Takes masked image + target face
2. Uses SeeDream to reconstruct face
3. Uploads result to S3
4. Returns CloudFront URL

### 3. Full Face Swap API

**Endpoint**: `POST /api/v1/full-face-swap/jobs`

Complete face swap pipeline (combines steps 1 + 2).

**Request**:
```json
{
  "source_image_url": "https://example.com/person.jpg",
  "target_face_url": "https://example.com/celebrity.jpg",
  "face_index": 0,
  "prompt": null,
  "size": "auto"
}
```

**Response**:
```json
{
  "job_id": "uuid-string",
  "status": "pending"
}
```

### 4. Job Status API

**Endpoint**: `GET /api/v1/jobs/{job_id}`

Get job status and results.

**Response**:
```json
{
  "job_id": "uuid-string",
  "status": "completed",
  "result_url": "https://d3bg7alr1qwred.cloudfront.net/face_swap/result.png",
  "error": null
}
```

**Status values**: `pending`, `processing`, `completed`, `failed`

## Quick Start

### Prerequisites

- Ubuntu EC2 instance (CPU only, no GPU required)
- Python 3.10+
- AWS credentials configured (IAM instance profile)
- QWEN3-VL API key (Dashscope)
- SeeDream API key (Volcano Engine ARK)

### Installation

```bash
# Clone repository
cd /home/ubuntu
git clone <repo> paid-api-service
cd paid-api-service

# Run setup script
chmod +x setup_services.sh
./setup_services.sh
```

### Manual Installation

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export DASHSCOPE_API_KEY='your_dashscope_key'
export ARK_API_KEY='your_ark_key'
export AWS_ACCESS_KEY='your_aws_key'
export AWS_ACCESS_SECRET='your_aws_secret'
export S3_BUCKET_NAME='short-drama-assets'
export CLOUDFRONT_DOMAIN='https://d3bg7alr1qwred.cloudfront.net'

# Run API service
python api_service.py

# In another terminal, run SQS adapter
export CPU_QUEUE_URL='https://sqs.us-east-1.amazonaws.com/xxx/cpu_tasks_queue'
export DYNAMODB_TABLE='task_store'
python sqs_adapter.py
```

## Deployment

### Service Files

```bash
# Service files location
/etc/systemd/system/paid-api.service
/etc/systemd/system/sqs-adapter.service

# Application files
/home/ubuntu/paid-api-service/
├── api_service.py
├── sqs_adapter.py
├── face_swap.py
└── image-to-image/
    └── seedream.py
```

### Service Management

```bash
# Check status
sudo systemctl status paid-api
sudo systemctl status sqs-adapter

# Restart services
sudo systemctl restart paid-api
sudo systemctl restart sqs-adapter

# View logs
sudo journalctl -u paid-api -f
sudo journalctl -u sqs-adapter -f

# Enable on boot
sudo systemctl enable paid-api
sudo systemctl enable sqs-adapter
```

### Update Code

```bash
# Upload new code
scp -i ~/.ssh/key.pem api_service.py ubuntu@ip:~/paid-api-service/
scp -i ~/.ssh/key.pem sqs_adapter.py ubuntu@ip:~/paid-api-service/
scp -i ~/.ssh/key.pem face_swap.py ubuntu@ip:~/paid-api-service/

# Restart services
ssh -i ~/.ssh/key.pem ubuntu@ip "sudo systemctl restart paid-api"
ssh -i ~/.ssh/key.pem ubuntu@ip "sudo systemctl restart sqs-adapter"
```

## Environment Variables

### Paid API Service

Required in `paid-api.service`:

```ini
Environment="DASHSCOPE_API_KEY=sk-xxx"        # QWEN3-VL API key
Environment="ARK_API_KEY=xxx-xxx"             # SeeDream API key
Environment="AWS_ACCESS_KEY=AKIA..."          # AWS access key
Environment="AWS_ACCESS_SECRET=xxx"           # AWS secret key
Environment="S3_BUCKET_NAME=short-drama-assets"
Environment="CLOUDFRONT_DOMAIN=https://d3bg7alr1qwred.cloudfront.net"
Environment="AWS_DEFAULT_REGION=us-east-1"
```

### SQS Adapter

Required in `sqs-adapter.service`:

```ini
Environment="CPU_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/xxx/cpu_tasks_queue"
Environment="DYNAMODB_TABLE=task_store"
Environment="PAID_API_URL=http://localhost:8000"
Environment="AWS_REGION=us-east-1"
Environment="POLL_INTERVAL=20"
```

## Testing

### Health Check

```bash
curl http://localhost:8000/health
```

### Direct API Test

```bash
# Test face mask
curl -X POST "http://localhost:8000/api/v1/face-mask/jobs" \
  -H "Content-Type: application/json" \
  -d '{
    "image_url": "https://example.com/person.jpg",
    "face_index": 0
  }'

# Get status
curl http://localhost:8000/api/v1/jobs/{job_id}
```

### Via Orchestrator (End-to-End)

```bash
# Submit task via orchestrator
curl -X POST "http://orchestrator:8080/api/v1/full-face-swap/tasks" \
  -H "Content-Type: application/json" \
  -d '{
    "source_image_url": "https://example.com/person.jpg",
    "target_face_url": "https://example.com/celebrity.jpg"
  }'

# Check status
curl http://orchestrator:8080/api/v1/tasks/{task_id}
```

## Python Client Example

```python
import requests
import time

BASE_URL = "http://localhost:8000/api/v1"

# Submit full face swap job
response = requests.post(
    f"{BASE_URL}/full-face-swap/jobs",
    json={
        "source_image_url": "https://example.com/person.jpg",
        "target_face_url": "https://example.com/celebrity.jpg",
        "face_index": 0,
        "size": "auto"
    }
)
job_id = response.json()['job_id']

# Poll for completion
while True:
    status = requests.get(f"{BASE_URL}/jobs/{job_id}").json()
    print(f"Status: {status['status']}")

    if status['status'] == 'completed':
        print(f"Result: {status['result_url']}")
        break
    elif status['status'] == 'failed':
        print(f"Error: {status['error']}")
        break

    time.sleep(2)
```

## IAM Permissions Required

**CPU Instance Profile**:
- `s3:PutObject` - Upload results to S3
- `sqs:ReceiveMessage` - Receive tasks from queue
- `sqs:DeleteMessage` - Remove processed messages
- `dynamodb:UpdateItem` - Update task status
- `dynamodb:GetItem` - Read task status

## File Structure

```
backend/paid-api-service/
├── README.md                    # This file
├── api_service.py               # Main API service
├── sqs_adapter.py               # SQS adapter
├── face_swap.py                 # Face manipulation logic
├── requirements.txt             # Python dependencies
├── paid-api.service             # Systemd service file
├── sqs-adapter.service          # Systemd service file
├── setup_services.sh            # Setup script
└── image-to-image/
    ├── seedream.py              # SeeDream client
    └── README.md                # SeeDream docs
```

## Troubleshooting

### Service won't start

```bash
# Check logs
sudo journalctl -u paid-api -n 50
sudo journalctl -u sqs-adapter -n 50

# Check environment variables
sudo systemctl show paid-api | grep Environment

# Test Python environment
/home/ubuntu/paid-api-service/venv/bin/python --version
```

### Jobs failing

```bash
# Check API logs
sudo journalctl -u paid-api -f

# Test API keys
curl http://localhost:8000/health

# Test face detection
python3 -c "
from face_swap import detect_face_with_qwen
import os
result = detect_face_with_qwen('test.jpg', os.getenv('DASHSCOPE_API_KEY'))
print(result)
"
```

### SQS adapter not processing

```bash
# Check adapter logs
sudo journalctl -u sqs-adapter -f

# Verify queue URL
echo $CPU_QUEUE_URL

# Check IAM permissions
aws sts get-caller-identity
aws sqs get-queue-attributes --queue-url $CPU_QUEUE_URL
```

## Performance Notes

- **Face Mask**: ~3-5 seconds (QWEN3-VL API call)
- **Face Swap**: ~8-15 seconds (SeeDream API call)
- **Full Pipeline**: ~12-20 seconds (combined)
- **Concurrent Jobs**: Limited by API rate limits
- **SQS Polling**: 20-second intervals with long polling

## Cost Considerations

- **QWEN3-VL**: ~$0.01 per face detection
- **SeeDream**: ~$0.05 per image generation
- **S3 Storage**: ~$0.023 per GB
- **CloudFront**: ~$0.085 per GB transfer
- **EC2 Instance**: t3.medium (~$30/month)

## Known Issues

### ✅ FIXED: Ellipse mask too large
**Issue**: Initial implementation masked entire head including hair
**Fix**: Updated to mask only face (forehead to chin) with 5% expansion

### ✅ FIXED: Pre-signed URL expiration
**Issue**: SeeDream returns temporary URLs that expire
**Fix**: Auto-download and upload to S3 immediately

## Version History

- **v1.0.0** (2025-11-19): Initial release with face mask + face swap APIs

---

**Maintained By**: Short Drama Team
**Last Updated**: 2025-11-19
