# ComfyUI Unified API Service

Production-ready REST API for ComfyUI image processing workflows with SQS orchestration support.

## Overview

A unified API service that wraps multiple ComfyUI workflows into clean, versioned REST endpoints. Deployed on GPU instances and integrated with AWS SQS for distributed task processing.

**Current Endpoint**: `http://34.203.11.145:8000`

## Features

- ✅ **Single Port**: All APIs on port 8000
- ✅ **Versioned**: `/api/v1/` for future compatibility
- ✅ **RESTful**: Standard REST patterns with job-based architecture
- ✅ **Multi-workflow**: Camera angle transformation & Image editing
- ✅ **Multi-image Support**: 1-3 images per job
- ✅ **S3 Integration**: S3 input + CloudFront CDN output
- ✅ **SQS Orchestration**: Distributed processing via SQS adapter
- ✅ **Auto-restart**: Systemd managed services

## Quick Start

### Health Check
```bash
curl http://34.203.11.145:8000/health
```

### Camera Angle Transformation
```bash
curl -X POST "http://34.203.11.145:8000/api/v1/camera-angle/jobs" \
  -H "Content-Type: application/json" \
  -d '{
    "image_url": "https://short-drama-assets.s3.amazonaws.com/images/input.jpg",
    "prompt": "将镜头转为俯视"
  }'
```

### Image Editing (Qwen-Rapid-AIO)
```bash
# Single image
curl -X POST "http://34.203.11.145:8000/api/v1/qwen-image-edit/jobs" \
  -H "Content-Type: application/json" \
  -d '{
    "image_url": "https://short-drama-assets.s3.amazonaws.com/images/input.jpg",
    "prompt": "black and white sketch",
    "steps": 4
  }'

# Multiple images (2-3 images)
curl -X POST "http://34.203.11.145:8000/api/v1/qwen-image-edit/jobs" \
  -H "Content-Type: application/json" \
  -d '{
    "image_url": "https://short-drama-assets.s3.amazonaws.com/images/input.jpg",
    "image2_url": "https://short-drama-assets.s3.amazonaws.com/images/ref1.jpg",
    "image3_url": "https://short-drama-assets.s3.amazonaws.com/images/ref2.jpg",
    "prompt": "merge images into artistic sketch",
    "steps": 4
  }'
```

### Get Job Status
```bash
# Unified endpoint (works for all job types)
curl http://34.203.11.145:8000/api/v1/jobs/{job_id}

# Workflow-specific endpoints
curl http://34.203.11.145:8000/api/v1/camera-angle/jobs/{job_id}
curl http://34.203.11.145:8000/api/v1/qwen-image-edit/jobs/{job_id}
```

## API Structure

```
/                                          → Service info
/health                                    → Health check

/api/v1/camera-angle/jobs                  → Camera angle transformation
  ├── POST                                 → Create job
  └── /{job_id}
      └── GET                              → Get job status

/api/v1/qwen-image-edit/jobs               → Image editing (Qwen-Rapid-AIO)
  ├── POST                                 → Create job
  └── /{job_id}
      └── GET                              → Get job status

/api/v1/jobs/{job_id}                      → Unified job status
  └── GET                                  → Get any job status
```

## Available Workflows

### 1. Camera Angle Transformation
**Endpoint**: `/api/v1/camera-angle/jobs`
**Workflow**: `camera-angle-api.json`
**Model**: Qwen-Image-Edit with camera angle LoRA

**Features:**
- Single image input
- Camera perspective transformation
- 8 sampling steps (optimized)

**Request:**
```json
{
  "image_url": "https://short-drama-assets.s3.amazonaws.com/images/input.jpg",
  "prompt": "将镜头转为俯视",
  "seed": 12345,        // optional
  "steps": 8            // optional
}
```

### 2. Image Editing (Qwen-Rapid-AIO)
**Endpoint**: `/api/v1/qwen-image-edit/jobs`
**Workflow**: `qwen-image-edit-api.json`
**Model**: Qwen-Rapid-AIO-NSFW-v11

**Features:**
- 1-3 image inputs (multi-image support)
- Advanced style transfer
- Line art extraction
- 4 sampling steps (ultra-fast)

**Request:**
```json
{
  "image_url": "https://short-drama-assets.s3.amazonaws.com/images/main.jpg",
  "image2_url": "https://short-drama-assets.s3.amazonaws.com/images/ref1.jpg",  // optional
  "image3_url": "https://short-drama-assets.s3.amazonaws.com/images/ref2.jpg",  // optional
  "prompt": "black and white sketch",
  "steps": 4,                    // optional
  "cfg": 1.0,                    // optional
  "sampler_name": "sa_solver",   // optional
  "scheduler": "beta",           // optional
  "denoise": 1.0                 // optional
}
```

**Response:**
```json
{
  "job_id": "uuid-string",
  "status": "completed",
  "result_s3_uri": "https://d3bg7alr1qwred.cloudfront.net/images/comfyui-results/qwen-image-edit/job-id.png",
  "error": null
}
```

## Architecture

### Components

```
┌─────────────────┐      ┌──────────────┐      ┌─────────────────┐
│   Orchestrator  │─────→│  SQS Queue   │─────→│  SQS Adapter    │
│  (ECS/Local)    │      │              │      │  (GPU Instance) │
└─────────────────┘      └──────────────┘      └─────────────────┘
                                                        │
                                                        ↓
                                                ┌─────────────────┐
                                                │  ComfyUI API    │
                                                │  (Port 8000)    │
                                                └─────────────────┘
                                                        │
                                                        ↓
                                                ┌─────────────────┐
                                                │   S3 + CDN      │
                                                │   (Results)     │
                                                └─────────────────┘
```

### Services on GPU Instance

| Service | Port | Purpose |
|---------|------|---------|
| ComfyUI | 8188 | Core workflow engine |
| Unified API | 8000 | REST API service |
| SQS Adapter | N/A | Polls SQS and forwards to API |

## Deployment

### Prerequisites
- Ubuntu EC2 instance with GPU (T4/A10G)
- ComfyUI installed at `/home/ubuntu/ComfyUI`
- Python 3.10+ with venv
- AWS credentials configured (IAM instance profile)

### Service Files

All services are managed by systemd:

```bash
# Service files
/etc/systemd/system/comfyui.service
/etc/systemd/system/comfyui-unified-api.service
/etc/systemd/system/sqs-adapter.service

# Application files
~/comfyui_api_service/unified_api.py
~/sqs_to_comfy_adapter.py
~/ComfyUI/user/default/workflows/camera-angle-api.json
~/ComfyUI/user/default/workflows/qwen-image-edit-api.json
```

### Service Management

```bash
# Check status
sudo systemctl status comfyui
sudo systemctl status comfyui-unified-api
sudo systemctl status sqs-adapter

# Restart services
sudo systemctl restart comfyui
sudo systemctl restart comfyui-unified-api
sudo systemctl restart sqs-adapter

# View logs
sudo journalctl -u comfyui-unified-api -f
sudo journalctl -u sqs-adapter -f
```

### Update Code

```bash
# Update unified API
scp -i ~/.ssh/zzjw.pem unified_api.py ubuntu@34.203.11.145:~/comfyui_api_service/
ssh -i ~/.ssh/zzjw.pem ubuntu@34.203.11.145 "sudo systemctl restart comfyui-unified-api"

# Update SQS adapter
scp -i ~/.ssh/zzjw.pem sqs_to_comfy_adapter.py ubuntu@34.203.11.145:~/
ssh -i ~/.ssh/zzjw.pem ubuntu@34.203.11.145 "sudo systemctl restart sqs-adapter"

# Update workflows
scp -i ~/.ssh/zzjw.pem workflows/*.json ubuntu@34.203.11.145:~/ComfyUI/user/default/workflows/
ssh -i ~/.ssh/zzjw.pem ubuntu@34.203.11.145 "sudo systemctl restart comfyui-unified-api"
```

## Environment Variables

Set in systemd service files:

**comfyui-unified-api.service:**
```ini
Environment="S3_BUCKET=short-drama-assets"
Environment="AWS_REGION=us-east-1"
Environment="CLOUDFRONT_DOMAIN=d3bg7alr1qwred.cloudfront.net"
```

**sqs-adapter.service:**
```ini
Environment="AWS_REGION=us-east-1"
Environment="SQS_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/982081090398/gpu_tasks_queue"
Environment="DYNAMODB_TABLE=task_store"
```

## Python Client Example

```python
import requests
import time

BASE_URL = "http://34.203.11.145:8000/api/v1"

# Submit job
response = requests.post(
    f"{BASE_URL}/qwen-image-edit/jobs",
    json={
        "image_url": "https://short-drama-assets.s3.amazonaws.com/images/input.jpg",
        "prompt": "black and white sketch",
        "steps": 4
    }
)
job_id = response.json()['job_id']

# Poll status (using unified endpoint)
while True:
    status = requests.get(f"{BASE_URL}/jobs/{job_id}").json()
    if status['status'] in ['completed', 'failed']:
        if status['status'] == 'completed':
            print(f"Result: {status['result_s3_uri']}")
        else:
            print(f"Error: {status['error']}")
        break
    time.sleep(2)
```

## Troubleshooting

### Service won't start
```bash
# Check logs
sudo journalctl -u comfyui-unified-api -n 50

# Verify ComfyUI is running
curl http://localhost:8188/system_stats

# Check Python environment
/home/ubuntu/ComfyUI/venv/bin/python --version
```

### Jobs failing
```bash
# Check ComfyUI logs
sudo journalctl -u comfyui -f

# Check GPU
nvidia-smi

# Verify workflow files
ls -la ~/ComfyUI/user/default/workflows/
```

### SQS adapter not processing
```bash
# Check adapter logs
sudo journalctl -u sqs-adapter -f

# Verify IAM permissions
aws sts get-caller-identity
aws sqs get-queue-attributes --queue-url $SQS_QUEUE_URL

# Check DynamoDB
aws dynamodb describe-table --table-name task_store
```

## Testing

### Direct API Test
```bash
# Test camera angle
python test_unified_api.py

# Or manually
curl http://34.203.11.145:8000/health
```

### End-to-End Test (via Orchestrator)
```bash
# Submit via orchestrator (runs locally or in ECS)
curl -X POST "http://localhost:8080/api/v1/qwen-image-edit/jobs" \
  -H "Content-Type: application/json" \
  -d '{
    "image_url": "https://short-drama-assets.s3.amazonaws.com/images/input.jpg",
    "prompt": "artistic sketch",
    "steps": 4
  }'

# Check status via orchestrator
curl http://localhost:8080/api/v1/jobs/{job_id}
```

## File Structure

```
backend/comfyui-api-service/
├── README.md                          # This file
├── unified_api.py                     # Main API service
├── sqs_to_comfy_adapter.py            # SQS adapter
├── workflows/
│   ├── camera-angle-api.json          # Camera angle workflow
│   └── qwen-image-edit-api.json       # Image editing workflow
├── *.service                          # Systemd service files
├── test_unified_api.py                # Test script
└── setup_adapter.sh                   # Adapter setup script
```

## Configuration

### IAM Permissions Required

**GPU Instance Profile:**
- `s3:GetObject` - Download input images
- `s3:PutObject` - Upload results
- `sqs:ReceiveMessage` - Receive tasks from queue
- `sqs:DeleteMessage` - Remove processed messages
- `dynamodb:UpdateItem` - Update task status

### S3 Structure

```
short-drama-assets/
├── images/
│   ├── input.jpg                      # Input images
│   └── comfyui-results/
│       ├── camera-angle/
│       │   └── {job-id}.png           # Camera angle results
│       └── qwen-image-edit/
│           └── {job-id}.png           # Image edit results
```

### CDN URLs

Results are returned as CloudFront CDN URLs:
```
https://d3bg7alr1qwred.cloudfront.net/images/comfyui-results/{workflow}/{job-id}.png
```

## Known Issues & Fixes

### ✅ FIXED: Placeholder image validation errors
**Issue**: Jobs failed with "Invalid image file: placeholder2.png"
**Fix**: Conditional workflow handling removes unused image nodes when optional images not provided

### ✅ FIXED: Wrong checkpoint name
**Issue**: Used Qwen-Image-Edit-2509 instead of Qwen-Rapid-AIO
**Fix**: Updated workflow to use correct checkpoint

### ✅ FIXED: Deep S3 paths
**Issue**: S3 paths were too nested
**Fix**: Flattened to `images/comfyui-results/{workflow}/{job-id}.png`

## Performance Notes

- **Camera Angle**: ~10-15 seconds per job (8 steps)
- **Qwen Image Edit**: ~5-10 seconds per job (4 steps)
- **Concurrent Jobs**: Limited by GPU memory (1 job at a time recommended)
- **SQS Polling**: 20-second intervals with long polling

## Version History

- **v1.2.0** (2025-11-18): Multi-image support for Qwen workflow
- **v1.1.0** (2025-11-18): Added SQS adapter integration
- **v1.0.0** (2025-11-17): Initial unified API release

---

**Maintained By**: Short Drama Team
**Last Updated**: 2025-11-18
