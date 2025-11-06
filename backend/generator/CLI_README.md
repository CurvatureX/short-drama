# Image Generation CLI Tool

Command-line interface for the Qwen Multi-Angle image generation API.

## Installation

```bash
cd /Users/jingweizhang/Workspace/short-drama/backend/generator

# Install with uv (recommended)
uv pip install -e .

# Or with pip
pip install -e .
```

After installation, the `image-generate` command will be available globally.

## Quick Start

### 1. Start the API Server

```bash
# In one terminal
cd /Users/jingweizhang/Workspace/short-drama/backend/generator
python server.py
```

The server will start at `http://localhost:8000`

### 2. Use the CLI

```bash
# Change camera angle of an image
image-generate change_angle \
  -i https://short-drama-assets.s3.us-east-1.amazonaws.com/images/input.png \
  -p "将镜头向左旋转45度" \
  --num_inference_steps 8 \
  --scale_to_megapixels 1.0 \
  -o output.png
```

## Commands

### `change_angle` - Change Camera Angle

Transform the camera perspective of an image using AI.

**Basic Usage:**
```bash
image-generate change_angle -i <image_url> -p <prompt>
```

**Full Example:**
```bash
image-generate change_angle \
  -i https://short-drama-assets.s3.us-east-1.amazonaws.com/images/input.png \
  -p "将镜头向左旋转45度" \
  -n "blurry, distorted" \
  --num_inference_steps 8 \
  --guidance_scale 1.0 \
  --true_cfg_scale 1.0 \
  --seed 42 \
  --scale_to_megapixels 1.0 \
  --scheduler_shift 3.0 \
  -o rotated_output.png \
  -v
```

**Arguments:**

| Argument | Short | Required | Default | Description |
|----------|-------|----------|---------|-------------|
| `--image-url` | `-i` | Yes | - | S3 URL or HTTP(S) URL of input image |
| `--prompt` | `-p` | Yes | - | Camera angle instruction (Chinese) |
| `--negative-prompt` | `-n` | No | `""` | Negative prompt |
| `--num_inference_steps` | - | No | `8` | Number of inference steps |
| `--guidance_scale` | - | No | `1.0` | CFG scale |
| `--true_cfg_scale` | - | No | `1.0` | True CFG scale |
| `--seed` | - | No | `None` | Random seed for reproducibility |
| `--scale_to_megapixels` | - | No | `1.0` | Scale image to megapixels |
| `--scheduler_shift` | - | No | `3.0` | ModelSamplingAuraFlow shift |
| `--no-cfg-norm` | - | No | `False` | Disable CFG normalization |
| `--output` | `-o` | No | `None` | Output file path (downloads if set) |
| `--no-wait` | - | No | `False` | Don't wait, return session_id |

**Supported Camera Angle Instructions (Chinese):**

- `"将镜头向前移动"` - Move the camera forward
- `"将镜头向左移动"` - Move the camera left
- `"将镜头向右移动"` - Move the camera right
- `"将镜头向下移动"` - Move the camera down
- `"将镜头向左旋转45度"` - Rotate the camera 45 degrees to the left
- `"将镜头向右旋转45度"` - Rotate the camera 45 degrees to the right
- `"将镜头转为俯视"` - Turn the camera to a top-down view
- `"将镜头转为广角镜头"` - Turn the camera to a wide-angle lens
- `"将镜头转为特写镜头"` - Turn the camera to a close-up

### `status` - Check Task Status

Check the status of a generation task.

**Usage:**
```bash
image-generate status <session_id>
```

**Example:**
```bash
image-generate status 550e8400-e29b-41d4-a716-446655440000
```

**Output:**
```
📊 Task Status:
  Status: completed
  Progress: 100%
  Message: Generation completed successfully
  Result URL: https://short-drama-assets.s3.us-east-1.amazonaws.com/images/20251106_152030_550e8400.png
```

### `info` - Get Model Information

Get information about loaded models and system status.

**Usage:**
```bash
image-generate info
```

**Example Output:**
```
🤖 Qwen Multi-Angle Model Info:
============================================================

📦 Models:
  - t2i: Qwen/Qwen-Image
  - i2i: Qwen/Qwen-Image-Edit-2509

🎨 LoRAs:
  - t2i_lightning: lightx2v/Qwen-Image-Lightning/Qwen-Image-Lightning-8steps-V1.0.safetensors
  - i2i_multi_angle: dx8152/Qwen-Edit-2509-Multiple-angles
  - i2i_lightning: lightx2v/Qwen-Image-Edit-Lightning/Qwen-Image-Edit-Lightning-4steps-V1.0.safetensors

⚙️  Workflow Features:
  - image_scaling: 1.0 megapixels default
  - scheduler: FlowMatchEulerDiscreteScheduler with shift=3.0
  - cfg_norm: Enabled by default
  - default_steps: 8 (with Lightning LoRA)

💾 VRAM Stats:
  - State: normal
  - Utilization: 45.2%
```

## Global Options

| Option | Short | Description |
|--------|-------|-------------|
| `--api-url` | - | API base URL (default: `http://localhost:8000`) |
| `--verbose` | `-v` | Enable verbose output |

## Examples

### Example 1: Rotate Camera Left 45 Degrees

```bash
image-generate change_angle \
  -i https://short-drama-assets.s3.us-east-1.amazonaws.com/images/scene1.png \
  -p "将镜头向左旋转45度" \
  -o scene1_rotated_left.png
```

### Example 2: Change to Top-Down View

```bash
image-generate change_angle \
  -i s3://short-drama-assets/images/character.png \
  -p "将镜头转为俯视" \
  --num_inference_steps 8 \
  --seed 12345 \
  -o character_topdown.png \
  -v
```

### Example 3: Close-Up Shot

```bash
image-generate change_angle \
  -i https://example.com/scene.jpg \
  -p "将镜头转为特写镜头" \
  -n "blurry, low quality" \
  --scale_to_megapixels 1.5 \
  -o closeup.png
```

### Example 4: Submit Without Waiting

```bash
# Submit task and get session_id immediately
image-generate change_angle \
  -i https://short-drama-assets.s3.us-east-1.amazonaws.com/images/input.png \
  -p "将镜头向前移动" \
  --no-wait

# Output:
# ✅ Task submitted successfully!
# 📝 Session ID: 550e8400-e29b-41d4-a716-446655440000
# ℹ️  Use 'image-generate status 550e8400-e29b-41d4-a716-446655440000' to check progress

# Check status later
image-generate status 550e8400-e29b-41d4-a716-446655440000
```

### Example 5: Use Remote API Server

```bash
# Connect to remote API
image-generate --api-url https://api.example.com change_angle \
  -i https://short-drama-assets.s3.us-east-1.amazonaws.com/images/input.png \
  -p "将镜头转为广角镜头" \
  -o wide_angle.png
```

## Workflow Details

The CLI tool interacts with the API that implements the full ComfyUI workflow:

1. **Image Input**: Downloads from S3 or HTTP(S) URL
2. **Image Scaling**: Scales to target megapixels using LANCZOS resampling
3. **Model Loading**:
   - UNETLoader: `qwen-image-edit-2509` (fp8_e4m3fn quantized)
   - CLIPLoader: `qwen-2.5-vl-7b` (fp8 scaled)
   - VAELoader: `qwen_image_vae`
4. **LoRA Loading**:
   - Multi-Angle LoRA for camera control
   - Lightning LoRA for fast 8-step editing
5. **Scheduler Config**: FlowMatchEulerDiscreteScheduler with shift=3.0
6. **Inference**: 8-step sampling with CFG normalization
7. **Output**: Upload to `s3://short-drama-assets/images/`

## Progress Tracking

The CLI automatically tracks progress with visual indicators:

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
💾 Saved to: /path/to/output.png
```

## Error Handling

The CLI provides clear error messages:

```bash
# Invalid image URL
❌ Request failed: HTTPError: 404 Client Error: Not Found

# API server not running
❌ Request failed: ConnectionError: Failed to establish a new connection

# Task failed
❌ Task failed: Out of memory error

# Timeout
⏰ Timeout reached after 300s
```

## Tips

1. **Reproducible Results**: Use `--seed` to get consistent outputs
2. **Quality vs Speed**: Default 8 steps with Lightning LoRA is optimal
3. **Image Size**: Use `--scale_to_megapixels 1.0` for 1MP (e.g., 1024x1024)
4. **Verbose Mode**: Add `-v` to see detailed request/response data
5. **Background Tasks**: Use `--no-wait` for async processing

## Troubleshooting

### CLI Command Not Found

```bash
# Reinstall the package
cd /Users/jingweizhang/Workspace/short-drama/backend/generator
uv pip install -e .

# Or use directly
python cli.py change_angle -i <url> -p <prompt>
```

### Connection Refused

Make sure the API server is running:
```bash
python server.py
```

### Import Errors

Install dependencies:
```bash
uv pip install requests
```

## Development

### Running Tests

```bash
# Test basic functionality
image-generate info

# Test with verbose output
image-generate -v info
```

### Adding New Commands

Edit `cli.py` and add new subparsers in the `main()` function.

## License

Part of the Short Drama project.
