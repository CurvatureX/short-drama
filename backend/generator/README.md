# Image/Video Generation Server

A Python FastAPI server for generating images and videos using AI models with async task processing, Redis-based progress tracking, and S3 storage.

## Features

- **Async Task Processing**: All generation tasks run in background, returning immediately with a session_id
- **Progress Tracking**: Real-time progress updates stored in Redis
- **S3 Storage**: Generated images/videos automatically uploaded to AWS S3
- **Text-to-Image (t2i)**: Generate images from text prompts
- **Image-to-Image (i2i)**: Transform images using AI models

## Supported Models

- **Flux**: Text-to-image and image-to-image generation
- **Qwen Multi-Angle**: Multi-angle image generation

## Architecture

```
┌─────────────┐      ┌──────────────┐      ┌─────────┐      ┌────────┐
│   Client    │─────▶│   FastAPI    │─────▶│  Redis  │      │   S3   │
│             │◀─────│    Server    │◀─────│ Status  │      │Storage │
└─────────────┘      └──────────────┘      └─────────┘      └────────┘
                            │                                     ▲
                            │                                     │
                            └─────────────────────────────────────┘
                                  Background Tasks
```

## Installation

This project uses [uv](https://docs.astral.sh/uv/) for Python package management.

1. Install uv if you haven't already:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

2. Install dependencies:
```bash
uv sync
```

3. Configure environment variables:
```bash
cp .env.example .env
# Edit .env with your Redis and AWS credentials
```

## Configuration

Create a `.env` file with the following variables:

```env
# Redis Configuration
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=

# AWS S3 Configuration
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_REGION=us-east-1
S3_BUCKET_NAME=image-generation-outputs

# Task Configuration
TASK_TTL=3600  # Task status TTL in seconds
```

## Running the Server

### Prerequisites
- Redis server running (default: localhost:6379)
- AWS S3 bucket configured (or S3-compatible service)

### Start Redis (if not running)
```bash
# macOS
brew services start redis

# Linux
sudo systemctl start redis

# Docker
docker run -d -p 6379:6379 redis:latest
```

### Start the Server

```bash
uv run python server.py
```

The server will start on `http://0.0.0.0:8000`

## API Usage

### Workflow

1. **Submit a generation task** → Get `session_id` immediately
2. **Poll status endpoint** → Check progress using `session_id`
3. **Get result URL** → When status is `completed`, retrieve S3 URL

### Available Endpoints

#### Health Check
```
GET /
```
Returns server status and Redis connection status.

#### Submit Generation Task

**Flux Text-to-Image:**
```
POST /api/flux/t2i
```

**Flux Image-to-Image:**
```
POST /api/flux/i2i
```

**Qwen Multi-Angle Text-to-Image:**
```
POST /api/qwen-multi-angle/t2i
```

**Qwen Multi-Angle Image-to-Image:**
```
POST /api/qwen-multi-angle/i2i
```

#### Check Task Status
```
GET /api/{session_id}/status
```

### Request/Response Examples

#### 1. Submit a Text-to-Image Task

**Request:**
```bash
curl -X POST "http://localhost:8000/api/flux/t2i" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "A serene lake with mountains at sunset",
    "width": 1024,
    "height": 768,
    "guidance_scale": 7.5,
    "num_inference_steps": 50
  }'
```

**Response:**
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "message": "Task submitted. Use /api/{session_id}/status to check progress."
}
```

#### 2. Submit an Image-to-Image Task

**Request:**
```bash
curl -X POST "http://localhost:8000/api/flux/i2i" \
  -F "image=@input.jpg" \
  -F "prompt=Transform into a watercolor painting" \
  -F "strength=0.8" \
  -F "guidance_scale=7.5"
```

**Response:**
```json
{
  "session_id": "660e8400-e29b-41d4-a716-446655440001",
  "status": "pending",
  "message": "Task submitted. Use /api/{session_id}/status to check progress."
}
```

#### 3. Check Task Status

**Request:**
```bash
curl "http://localhost:8000/api/550e8400-e29b-41d4-a716-446655440000/status"
```

**Response (Processing):**
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "processing",
  "progress": 60,
  "message": "Generation complete, uploading to S3...",
  "result_url": null,
  "error": null
}
```

**Response (Completed):**
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "progress": 100,
  "message": "Generation completed successfully",
  "result_url": "https://image-generation-outputs.s3.us-east-1.amazonaws.com/generations/20250104_120530_550e8400-e29b-41d4-a716-446655440000.png",
  "error": null
}
```

**Response (Failed):**
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "failed",
  "progress": 0,
  "message": "Generation failed",
  "result_url": null,
  "error": "Model inference error: GPU out of memory"
}
```

### Status Values

- `pending`: Task is queued
- `processing`: Task is being executed
- `completed`: Task completed successfully, result_url available
- `failed`: Task failed, error message available

### Request Parameters

#### Text-to-Image (t2i)
```json
{
  "prompt": "string (required)",
  "negative_prompt": "string (optional)",
  "width": "int (default: 512)",
  "height": "int (default: 512)",
  "num_inference_steps": "int (default: 50)",
  "guidance_scale": "float (default: 7.5)",
  "seed": "int (optional)"
}
```

#### Image-to-Image (i2i)
- `image`: File (required)
- `prompt`: string (optional)
- `strength`: float (default: 0.8)
- `guidance_scale`: float (default: 7.5)
- `num_inference_steps`: int (default: 50)
- `seed`: int (optional)

## API Documentation

Once the server is running, visit:
- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

## Project Structure

```
backend/generator/
├── server.py                       # Main FastAPI application
├── config.py                       # Configuration settings
├── models/                         # Model implementations
│   ├── __init__.py
│   ├── base.py                     # Shared schemas
│   ├── flux.py                     # Flux model
│   └── qwen_multi_angle.py         # Qwen Multi-Angle model
├── services/                       # Backend services
│   ├── __init__.py
│   ├── redis_service.py            # Redis status tracking
│   ├── s3_service.py               # S3 upload service
│   └── task_service.py             # Background task processing
├── pyproject.toml                  # Project dependencies
├── .env.example                    # Environment variables template
└── README.md
```

## Adding New Dependencies

To add new packages (e.g., for AI model integration):

```bash
uv add torch diffusers transformers
```

## Model Integration

The current implementation includes placeholder responses. To integrate actual AI models:

1. Add model libraries using uv:
```bash
uv add torch diffusers transformers
```

2. Update the model implementation files in `models/`:
   - Replace `generate_image()` function with actual model inference
   - Replace `transform_image()` function with actual img2img inference

3. Example for Flux with diffusers:
```python
from diffusers import FluxPipeline
import torch

pipe = FluxPipeline.from_pretrained("black-forest-labs/FLUX.1-dev", torch_dtype=torch.float16)
pipe = pipe.to("cuda")

def generate_image(request: TextToImageRequest) -> bytes:
    image = pipe(
        prompt=request.prompt,
        height=request.height,
        width=request.width,
        guidance_scale=request.guidance_scale,
        num_inference_steps=request.num_inference_steps,
    ).images[0]
    return image_to_bytes(image)
```

## Troubleshooting

### Redis Connection Error
```bash
# Check if Redis is running
redis-cli ping
# Should return: PONG

# Start Redis if not running
brew services start redis  # macOS
sudo systemctl start redis # Linux
```

### S3 Upload Error
- Verify AWS credentials in `.env`
- Ensure S3 bucket exists and is accessible
- Check bucket permissions (PutObject required)

### Task Stuck in Processing
- Check server logs for errors
- Verify background task executor is not blocked
- Check Redis TTL (default: 1 hour)

## Future Enhancements

- `/api/{model_name}/t2v` - Text-to-Video generation
- `/api/{model_name}/i2v` - Image-to-Video generation
- Webhook notifications on task completion
- Batch processing support
- Priority queue for tasks
- Result caching
