# Face Swap Feature Implementation

## Overview

Successfully implemented Face Swap functionality in the image-edit-canvas frontend.

## Features Implemented

### 1. **Face Swap Button**
- Located between "Change Viewpoint" and "Download" buttons
- Uses `/icons/swap.png` icon
- Appears when an image is selected
- Clicking opens the Face Swap sidebar panel
- Automatically closes other panels (Viewpoint, Edit) when opened

### 2. **Face Swap Sidebar Panel**
- Right-side sliding panel (320px wide)
- Full height, white background with shadow
- Contains the following components:

#### Components:
- **Header** with title and close button (×)
- **Model Selection** dropdown (currently only "Full Face Swap")
- **Face Reference Image** dropdown
  - Lists all images on canvas except the selected one
  - Shows truncated filename (last 30 chars) for readability
- **Preview Section** (shown when reference image selected)
  - Side-by-side preview of Source and Target images
  - Arrow (→) between them showing transformation direction
- **Generate Button**
  - Disabled until reference image selected
  - Shows "Generating..." during processing
  - Triggers face swap task

### 3. **API Integration**

#### New API Functions (`lib/api.ts`):
- `submitFaceSwap()` - Submit face swap task to CPU orchestrator
- `pollFaceSwapStatus()` - Poll for task completion
- `getCpuTaskStatus()` - Get current task status

#### API Design:
- Uses unified `JobResponse` type for consistency with GPU tasks
- Maps CPU task response to GPU job format:
  - `task_id` → `job_id`
  - `result_url` → `result_s3_uri`
  - `error_message` → `error`
- Polls every 2 seconds (CPU tasks are slower than GPU)

### 4. **Processing Flow**

1. **User clicks Face Swap button**
   - Closes all other panels
   - Opens Face Swap sidebar

2. **User selects reference image**
   - Preview shows source and target side-by-side
   - Generate button becomes enabled

3. **User clicks Generate**
   - Submits task to CPU orchestrator (port 8081)
   - Creates placeholder job in processing list
   - Closes sidebar panel
   - Shows loading state

4. **Background polling**
   - Polls task status every 2 seconds
   - Updates placeholder with progress
   - On completion:
     - Adds result image to canvas
     - Saves to session
     - Removes placeholder

## File Changes

### Modified Files:

1. **`lib/api.ts`**
   - Added Face Swap API functions
   - Unified response types with GPU tasks
   - Added CPU orchestrator URL configuration

2. **`components/InfiniteCanvas.tsx`**
   - Added Face Swap button to toolbar
   - Added Face Swap sidebar panel UI
   - Added state management for Face Swap
   - Integrated with processing job system

3. **`.env.local`** (created)
   - `NEXT_PUBLIC_CPU_ORCH_URL=http://localhost:8081`

## Configuration

### Environment Variables:

```env
# Canvas API (session management)
NEXT_PUBLIC_CANVAS_API_URL=http://localhost:9000

# GPU Orchestrator (Qwen edit, camera angle)
NEXT_PUBLIC_ORCH_URL=http://localhost:8080

# CPU Orchestrator (Face Swap)
NEXT_PUBLIC_CPU_ORCH_URL=http://localhost:8081
```

## Backend Requirements

The frontend expects the following backend endpoints:

### CPU Orchestrator (Port 8081):
- `POST /api/v1/full-face-swap/tasks` - Submit face swap
- `GET /api/v1/tasks/{task_id}` - Get task status

### Expected Response Format:
```json
{
  "task_id": "uuid",
  "status": "pending|processing|completed|failed",
  "result_url": "https://cdn.cloudfront.net/...",
  "error_message": "..."
}
```

## User Experience

### UI Flow:
1. Select an image on canvas
2. Click "Face Swap" button
3. Choose reference face from dropdown
4. See preview of source → target
5. Click "Generate"
6. See loading indicator on canvas
7. Result appears next to original

### Visual Feedback:
- Disabled state when no reference selected
- Loading state during generation
- Placeholder with pulsing animation
- Automatic cleanup after completion

## Technical Details

### State Management:
- `showFaceSwapPanel` - Controls sidebar visibility
- `faceSwapTargetUrl` - Selected reference image URL
- `sendingFaceSwap` - Loading state flag
- `processingJobs` - Shared with GPU tasks for unified job tracking

### Integration Points:
- Reuses existing job processing infrastructure
- Shares placeholder system with Camera/Qwen edits
- Integrates with session persistence
- Uses same S3/CloudFront URL handling

## Testing

### Quick Test:
1. Start CPU orchestrator: `cd backend/orchestrator && PORT=8081 python cpu_orchestrator_api.py`
2. Start paid-api-service: (should already be running on port 9000)
3. Start SQS adapter: (should be running)
4. Upload 2 images to canvas
5. Select one image
6. Click "Face Swap"
7. Select other image as reference
8. Click "Generate"
9. Wait ~15-20 seconds for result

## Future Enhancements

Potential improvements:
- Multiple model options (face-only swap, partial swap, etc.)
- Face selection within image (if multiple faces)
- Strength/blend slider
- Batch face swap (multiple targets)
- History/undo for face swaps

---

**Status**: ✅ Complete and ready for testing
**Date**: 2025-11-19
