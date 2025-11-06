# Image Generation CLI - Quick Start Guide

## Installation

```bash
cd /Users/jingweizhang/Workspace/short-drama/backend/generator
uv pip install -e .
```

## Usage

### Basic Command

```bash
image-generate change_angle \
  -i https://short-drama-assets.s3.us-east-1.amazonaws.com/images/input.png \
  -p "将镜头向左旋转45度" \
  --num_inference_steps 8 \
  --scale_to_megapixels 1.0 \
  -o output.png
```

### Short Version (Minimal Arguments)

```bash
image-generate change_angle \
  -i <image_url> \
  -p "将镜头向左旋转45度"
```

### Common Camera Angle Prompts

```bash
# Rotate left 45 degrees
-p "将镜头向左旋转45度"

# Rotate right 45 degrees
-p "将镜头向右旋转45度"

# Top-down view
-p "将镜头转为俯视"

# Close-up
-p "将镜头转为特写镜头"

# Wide-angle
-p "将镜头转为广角镜头"

# Move forward
-p "将镜头向前移动"

# Move left
-p "将镜头向左移动"

# Move right
-p "将镜头向右移动"
```

### Check Status

```bash
image-generate status <session_id>
```

### Get Model Info

```bash
image-generate info
```

## Complete Example

```bash
# Start API server first (in another terminal)
cd /Users/jingweizhang/Workspace/short-drama/backend/generator
python server.py

# Use CLI to generate image
image-generate change_angle \
  -i https://short-drama-assets.s3.us-east-1.amazonaws.com/images/test.png \
  -p "将镜头向左旋转45度" \
  -n "blurry, distorted" \
  --num_inference_steps 8 \
  --guidance_scale 1.0 \
  --seed 42 \
  --scale_to_megapixels 1.0 \
  -o rotated_output.png \
  -v
```

## Expected Output

```
🚀 Submitting request to: http://localhost:8000/api/qwen-multi-angle/i2i
✅ Task submitted successfully!
📝 Session ID: 550e8400-e29b-41d4-a716-446655440000
⏳ Waiting for completion (timeout: 300s)...
📈 Progress: 10% - Starting generation...
📈 Progress: 60% - Generation complete, uploading to S3 (images)...
📈 Progress: 100% - Generation completed successfully
✅ Task completed!
🔗 Result URL: https://short-drama-assets.s3.us-east-1.amazonaws.com/images/20251106_152030_550e8400.png
📥 Downloading: 100.0%
💾 Saved to: /path/to/rotated_output.png
```

## Troubleshooting

### Command not found
```bash
# Reinstall
cd /Users/jingweizhang/Workspace/short-drama/backend/generator
uv pip install -e .
```

### API server not running
```bash
# Start server
python server.py
```

### Connection refused
Make sure the server is running at http://localhost:8000
