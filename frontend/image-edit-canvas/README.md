# image-edit-canvas (Next.js)

An infinite pan/zoom canvas where users upload images that stick to the canvas and zoom with it. Backed by a FastAPI service that stores uploads in S3 and issues sessions per canvas.

## Quick Start

Backend (FastAPI):
1. Configure AWS and S3: see `backend/canvas_service/README.md`.
2. Run backend on `http://localhost:9000`.

Frontend (Next.js) with Yarn:
```bash
cd frontend/image-edit-canvas
nvm use || nvm use 20   # ensure Node 20
yarn install
export NEXT_PUBLIC_CANVAS_API_URL=http://localhost:9000
yarn dev
```

Open `http://localhost:3000`.
The app writes the `session_id` into the URL (e.g., `?session_id=...`) so refreshes keep your session and uploaded images.

If you previously used npm, clean first:
```bash
rm -rf node_modules .next package-lock.json
yarn install
yarn dev
```

## How it works
- On load, the app requests a new session from the backend and remembers the `session_id`.
- Click the left-side “+” button to upload an image; it is sent with the session id and stored under the `session_id/` prefix in S3.
- The backend returns a presigned URL which is rendered on the canvas.
- The canvas uses CSS transforms (translate + scale) so content moves and scales together.
- Zoom controls are at the top-right, and a zoom percentage indicator is shown at the bottom-left.

## Configuration
- `NEXT_PUBLIC_CANVAS_API_URL`: Base URL for the canvas backend (default: `http://localhost:9000`)
- `NEXT_PUBLIC_ORCH_URL`: Base URL for the GPU orchestrator (default: `http://localhost:8080`)

## GPU Processing Features

The canvas now integrates with the GPU orchestrator backend to provide two AI-powered image processing capabilities:

### 1. Qwen Image Edit
- Select any image on the canvas
- Click "Qwen Edit" in the toolbar
- Enter a text prompt describing the desired edit (e.g., "black and white sketch", "watercolor painting style")
- Click "Send" to submit the job
- A placeholder appears immediately to the right of the source image
- The placeholder polls the orchestrator every 1 second for status updates
- When processing completes (~5-10 seconds), the placeholder is replaced with the final result

### 2. Camera Angle Adjustment
- Select any image on the canvas
- Click "Change Viewpoint" in the toolbar
- Adjust parameters:
  - **Camera Rotation**: -90° (left) to +90° (right) in 45° increments
  - **Vertical Angle**: -2 (extreme low) to +2 (bird's eye)
  - **Movement**: -1 (zoom out) to +1 (zoom in)
- Click "Generate" to submit the job
- A placeholder appears immediately to the right of the source image
- The placeholder polls the orchestrator every 1 second for status updates
- When processing completes (~10-15 seconds), the placeholder is replaced with the final result

### How It Works

**Job Submission Flow:**
1. User triggers Qwen Edit or Camera Angle action
2. Frontend calls orchestrator API (POST `/api/v1/qwen-image-edit/jobs` or `/api/v1/camera-angle/jobs`)
3. Orchestrator returns immediately with `job_id` and status `pending`
4. Frontend renders a placeholder with loading indicator
5. Frontend starts polling GET `/api/v1/jobs/{job_id}` every 1 second
6. When status changes to `completed`, placeholder is replaced with `result_s3_uri` image
7. If status is `failed`, placeholder shows error state

**Architecture:**
```
Frontend Canvas → Orchestrator API → SQS Queue → GPU Worker → ComfyUI → S3 + CDN
     ↓                                                                      ↑
     └──────────────── Poll job status every 1s ─────────────────────────┘
```

## API Integration Details

### Qwen Edit API
```typescript
// Submit job
const response = await fetch('http://localhost:8080/api/v1/qwen-image-edit/jobs', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    image_url: 'https://short-drama-assets.s3.amazonaws.com/images/input.jpg',
    prompt: 'black and white sketch',
    steps: 4
  })
})
// Returns: { job_id: "uuid", status: "pending" }

// Poll status
const status = await fetch(`http://localhost:8080/api/v1/jobs/${job_id}`)
// Returns: { job_id, status: "completed", result_s3_uri: "https://cdn.../result.png" }
```

### Camera Angle API
```typescript
// Submit job
const response = await fetch('http://localhost:8080/api/v1/camera-angle/jobs', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    image_url: 'https://short-drama-assets.s3.amazonaws.com/images/input.jpg',
    vertical: 1,    // -2 to 2
    horizontal: 2,  // -2 to 2
    zoom: 0,        // -1 to 1
    steps: 8
  })
})
// Returns: { job_id: "uuid", status: "pending" }
```

## Development

### Running with GPU Orchestrator

1. **Start Canvas Backend** (manages sessions and image uploads):
```bash
cd backend/canvas_service
python main.py  # Runs on :9000
```

2. **Start GPU Orchestrator** (manages GPU tasks):
```bash
cd backend/orchestrator
export AWS_DEFAULT_REGION=us-east-1
export SQS_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/982081090398/gpu_tasks_queue
export DYNAMODB_TABLE=task_store
export GPU_INSTANCE_ID=i-0f0f6fd680921de5f
python orchestrator_api.py  # Runs on :8080
```

3. **Start Frontend**:
```bash
cd frontend/image-edit-canvas
export NEXT_PUBLIC_CANVAS_API_URL=http://localhost:9000
export NEXT_PUBLIC_ORCH_URL=http://localhost:8080
yarn dev  # Runs on :3000
```

### Testing GPU Features

1. Upload an image using the "+" button
2. Select the image to see the toolbar
3. Try Qwen Edit: Click "Qwen Edit", enter "watercolor painting", click "Send"
4. Try Camera Angle: Click "Change Viewpoint", adjust sliders, click "Generate"
5. Watch placeholders appear and update every second
6. Final images appear when processing completes
