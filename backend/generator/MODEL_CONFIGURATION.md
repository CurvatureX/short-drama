# Model Configuration Guide

Complete guide for configuring local models from the ComfyUI models directory.

## 📁 Directory Structure

The application expects models to be organized in the ComfyUI models directory structure:

```
/home/ubuntu/ComfyUI/models/
├── checkpoints/           # Stable Diffusion checkpoints
├── vae/                  # VAE models
├── loras/                # LoRA models
├── unet/                 # UNET models
├── text_encoders/        # Text encoder models
├── diffusion_models/     # Diffusion models
├── clip/                 # CLIP models
├── controlnet/           # ControlNet models
├── upscale_models/       # Upscaling models
├── inpaint/             # Inpainting models
├── lama/                # LAMA models
├── sams/                # SAM (Segment Anything) models
└── grounding-dino/      # Grounding DINO models
```

## 🔗 HuggingFace Repositories

The application can automatically download models from these HuggingFace repositories:

| Model | HuggingFace Repository | Local Path |
|-------|----------------------|------------|
| **Qwen Image Edit** | `Qwen/Qwen-Image-Edit-2509` | `diffusion_models/qwen-image-edit/` |
| **Qwen Multi-Angle LoRA** | `dx8152/Qwen-Edit-2509-Multiple-angles` | `loras/镜头转换.safetensors` |
| **Qwen Lightning LoRA** | `lightx2v/Qwen-Image-Edit-Lightning` | `loras/qwen-image-edit-lightning/` |
| **WanVideo MiniMaxRemover** | `WanVideo/Wan2_1-MiniMaxRemover` | `unet/Wan2_1-MiniMaxRemover_1_3B_fp16.safetensors` |
| **WanVideo VAE** | `WanVideo/Wan2_1` | `vae/Wan2_1_VAE_bf16.safetensors` |
| **FLUX.1-dev** | `black-forest-labs/FLUX.1-dev` | `checkpoints/juggernautXL_v9Rdphoto2Lightning.safetensors` |

**Note**: If you have a HuggingFace token for private models or faster downloads, add it to `.env`:

```bash
HF_TOKEN=your_hf_token_here
```

---

## 🎯 Available Models

### 1. Qwen Multi-Angle Models (Camera Angle Control)

**Location**: `/home/ubuntu/ComfyUI/models/diffusion_models/qwen-image-edit/`

| Model | File | Size | Purpose |
|-------|------|------|---------|
| **UNET** | `qwen_image_edit_2509_fp8_e4m3fn.safetensors` | ~2.6GB | Image editing model |
| **VAE** | `qwen_image_vae.safetensors` | ~164MB | Image encoding/decoding |
| **Text Encoder** | `qwen_2.5_vl_7b_fp8_scaled.safetensors` | ~7.1GB | Text understanding |

**LoRAs**:
- `镜头转换.safetensors` - Multi-Angle LoRA (camera control)
- `qwen-image-edit-lightning/Qwen-Image-Edit-Lightning-4steps-V1.0.safetensors` - Lightning LoRA (fast 8-step)

**Configuration in Code**:
```python
from config import model_paths

# Access model paths
unet_path = model_paths.qwen_image_edit_unet
vae_path = model_paths.qwen_image_vae
lora_path = model_paths.qwen_multi_angle_lora
```

---

### 2. WanVideo Models (Watermark Removal)

**Location**: `/home/ubuntu/ComfyUI/models/unet/` and `/home/ubuntu/ComfyUI/models/vae/`

| Model | File | Size | Purpose |
|-------|------|------|---------|
| **UNET** | `Wan2_1-MiniMaxRemover_1_3B_fp16.safetensors` | ~2.6GB | Watermark removal |
| **VAE** | `Wan2_1_VAE_bf16.safetensors` | ~164MB | Image encoding/decoding |
| **VAE (Alt)** | `wan_2.1_vae.safetensors` | ~164MB | Alternative VAE |
| **Text Encoder** | `umt5_xxl_fp16.safetensors` | ~11GB | Text understanding |
| **Text Encoder (FP8)** | `umt5_xxl_fp8_e4m3fn_scaled.safetensors` | ~5.5GB | Optimized text encoder |

**Configuration in Code**:
```python
from config import model_paths

# Access model paths
unet_path = model_paths.wan_minimax_remover_unet
vae_path = model_paths.wan_vae
text_encoder_path = model_paths.wan_text_encoder_fp8
```

---

### 3. WanVideo I2V Models (Image-to-Video)

**Location**: `/home/ubuntu/ComfyUI/models/diffusion_models/`

| Model | File | Size | Purpose |
|-------|------|------|---------|
| **High Noise** | `wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors` | ~14GB | High motion I2V |
| **Low Noise** | `wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors` | ~14GB | Low motion I2V |

**LoRAs**:
- `wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors` - Lightning LoRA (high noise)
- `wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors` - Lightning LoRA (low noise)

**Configuration in Code**:
```python
from config import model_paths

# Access model paths
high_noise_path = model_paths.wan_i2v_high_noise
low_noise_path = model_paths.wan_i2v_low_noise
lightning_lora = model_paths.wan_i2v_lightning_high
```

---

### 4. FLUX Models

**Location**: `/home/ubuntu/ComfyUI/models/checkpoints/`

| Model | File | Size | Purpose |
|-------|------|------|---------|
| **Checkpoint** | `juggernautXL_v9Rdphoto2Lightning.safetensors` | ~6.5GB | Photorealistic generation |

**Configuration in Code**:
```python
from config import model_paths

checkpoint_path = model_paths.flux_checkpoint
```

---

### 5. Inpainting Models

**Location**: `/home/ubuntu/ComfyUI/models/inpaint/` and `/home/ubuntu/ComfyUI/models/lama/`

| Model | File | Size | Purpose |
|-------|------|------|---------|
| **Fooocus Head** | `fooocus_inpaint_head.pth` | ~50MB | Inpainting head |
| **Fooocus Patch** | `inpaint.fooocus.patch` | ~5MB | Inpainting patch |
| **LAMA** | `big-lama.pt` | ~250MB | Advanced inpainting |

**Configuration in Code**:
```python
from config import model_paths

lama_path = model_paths.lama_model
fooocus_head = model_paths.fooocus_inpaint_head
```

---

### 6. Segmentation Models (SAM)

**Location**: `/home/ubuntu/ComfyUI/models/sams/`

| Model | File | Size | Purpose |
|-------|------|------|---------|
| **SAM ViT-B** | `sam_vit_b_01ec64.pth` | ~375MB | Fast segmentation |
| **SAM ViT-H** | `sam_vit_h_4b8939.pth` | ~2.4GB | High-quality segmentation |

**Configuration in Code**:
```python
from config import model_paths

sam_b = model_paths.sam_vit_b  # Faster
sam_h = model_paths.sam_vit_h  # Better quality
```

---

### 7. Object Detection (GroundingDINO)

**Location**: `/home/ubuntu/ComfyUI/models/grounding-dino/`

| Model | File | Size | Purpose |
|-------|------|------|---------|
| **Config** | `GroundingDINO_SwinT_OGC.cfg.py` | ~5KB | Model configuration |
| **Weights** | `groundingdino_swint_ogc.pth` | ~660MB | Object detection |

**Configuration in Code**:
```python
from config import model_paths

config = model_paths.grounding_dino_config
weights = model_paths.grounding_dino_weights
```

---

## ⚙️ Configuration Methods

### Method 1: Environment Variable

Set the base models directory in `.env`:

```bash
COMFYUI_MODELS_BASE=/home/ubuntu/ComfyUI/models
```

### Method 2: Direct Configuration

Modify `config.py`:

```python
class Settings(BaseSettings):
    comfyui_models_base: str = "/path/to/your/ComfyUI/models"
```

### Method 3: Runtime Override

```python
import os
os.environ['COMFYUI_MODELS_BASE'] = '/custom/path/to/models'

from config import settings, model_paths
```

---

## 🔍 Checking Model Availability

### Via API

```bash
# Get model information
curl http://localhost:8000/api/system/models

# Or for specific models
curl http://localhost:8000/api/qwen-multi-angle/info
curl http://localhost:8000/api/watermark-removal/info
```

### Via Python

```python
from config import model_paths

# Get all model info
model_info = model_paths.get_model_info()

for model_name, info in model_info.items():
    print(f"{model_name}:")
    print(f"  Path: {info['path']}")
    print(f"  Exists: {info['exists']}")
    print(f"  Size: {info['size_mb']} MB")
```

### Via CLI

```bash
# Check model info
image-generate info

# Verbose output
image-generate -v info
```

---

## 📊 Model Loading Priority

The application uses an intelligent fallback strategy for loading models:

### Automatic Fallback Strategy

1. **Check local path first** (`/home/ubuntu/ComfyUI/models/`)
   - If model exists locally, load from local file
   - Fast loading, no network required

2. **Fallback to HuggingFace download** (if local not found)
   - Automatically downloads from HuggingFace Hub
   - Cached in `~/.cache/huggingface/` for future use
   - Requires internet connection

### How It Works

The `model_loader` service automatically handles fallback:

```python
from services.model_loader import model_loader
from config import model_paths

# Load with automatic fallback
model = model_loader.load_safetensors_model(
    local_path=model_paths.qwen_image_edit_unet,  # Try local first
    hf_repo="Qwen/Qwen-Image-Edit-2509",          # Fallback to HF
    model_class=DiffusionPipeline,
    torch_dtype=torch.float16,
)
```

### Benefits

- **No manual intervention**: Models download automatically if missing
- **Local-first**: Uses local models when available (faster)
- **Network fallback**: Downloads if local models not found
- **Automatic caching**: Downloaded models cached for future use

### Checking Model Source

You can check which source will be used:

```python
from services.model_loader import model_loader
from config import model_paths

source, path = model_loader.get_model_source(
    local_path=model_paths.qwen_image_edit_unet,
    hf_repo="Qwen/Qwen-Image-Edit-2509",
)

print(f"Will load from: {source}")  # "local" or "huggingface"
print(f"Path: {path}")
```

---

## 🎯 Model Usage Examples

### Example 1: Load Qwen Model

```python
from config import model_paths
from diffusers import DiffusionPipeline

# Load from local path
pipe = DiffusionPipeline.from_single_file(
    str(model_paths.qwen_image_edit_unet),
    torch_dtype=torch.float16,
)

# Load VAE
vae = AutoencoderKL.from_single_file(
    str(model_paths.qwen_image_vae),
    torch_dtype=torch.bfloat16,
)

pipe.vae = vae
```

### Example 2: Load with LoRA

```python
from config import model_paths

# Load base model
pipe = load_base_model()

# Load LoRAs
pipe.load_lora_weights(
    str(model_paths.qwen_multi_angle_lora.parent),
    weight_name=model_paths.qwen_multi_angle_lora.name,
    adapter_name="multi_angle"
)

pipe.load_lora_weights(
    str(model_paths.qwen_edit_lightning_lora.parent),
    weight_name=model_paths.qwen_edit_lightning_lora.name,
    adapter_name="lightning"
)

# Activate both LoRAs
pipe.set_adapters(["multi_angle", "lightning"], adapter_weights=[1.0, 1.0])
```

### Example 3: Check Model Before Loading

```python
from config import model_paths

def safe_load_model():
    if not model_paths.qwen_image_edit_unet.exists():
        raise FileNotFoundError(
            f"Model not found: {model_paths.qwen_image_edit_unet}\n"
            f"Please download the model first."
        )

    # Load model
    model = load_from_path(model_paths.qwen_image_edit_unet)
    return model
```

---

## 🔧 Troubleshooting

### Issue: Model Not Found

**Check if path exists:**
```bash
ls -lh /home/ubuntu/ComfyUI/models/unet/Wan2_1-MiniMaxRemover_1_3B_fp16.safetensors
```

**Verify in Python:**
```python
from config import model_paths

path = model_paths.wan_minimax_remover_unet
print(f"Path: {path}")
print(f"Exists: {path.exists()}")
```

### Issue: Wrong Path

**Check environment variable:**
```bash
echo $COMFYUI_MODELS_BASE
```

**Update if needed:**
```bash
export COMFYUI_MODELS_BASE=/home/ubuntu/ComfyUI/models
```

### Issue: Permission Denied

**Fix permissions:**
```bash
sudo chown -R ubuntu:ubuntu /home/ubuntu/ComfyUI/models
chmod -R 755 /home/ubuntu/ComfyUI/models
```

### Issue: Out of VRAM

**Use quantized models:**
- FP8 models instead of FP16
- Example: `umt5_xxl_fp8_e4m3fn_scaled.safetensors` vs `umt5_xxl_fp16.safetensors`

**Enable model offloading:**
```python
pipe.enable_model_cpu_offload()
pipe.enable_sequential_cpu_offload()
```

---

## 📈 Model Size Reference

| Model Type | FP32 | FP16 | FP8 | INT8 |
|------------|------|------|-----|------|
| **Small (< 1B)** | 4GB | 2GB | 1GB | 0.5GB |
| **Medium (1-3B)** | 12GB | 6GB | 3GB | 1.5GB |
| **Large (7-13B)** | 52GB | 26GB | 13GB | 6.5GB |
| **XL (13B+)** | 100GB+ | 50GB+ | 25GB+ | 12GB+ |

**VRAM Requirements (Inference)**:
- Add 20-30% overhead for activations
- Example: 7B FP16 model needs ~8-10GB VRAM

---

## 🚀 Performance Optimization

### 1. Use Quantized Models

```python
# FP8 (fastest, good quality)
model_paths.wan_text_encoder_fp8  # 5.5GB vs 11GB FP16

# FP16 (balanced)
model_paths.wan_text_encoder  # 11GB

# BF16 (best quality)
model_paths.wan_vae  # 164MB
```

### 2. Enable Optimizations

```python
from services.optimization import optimization_manager

# Apply optimizations
pipe = optimization_manager.optimize_model(pipe)

# Or manually
pipe.enable_xformers_memory_efficient_attention()
pipe.enable_vae_slicing()
pipe.enable_vae_tiling()
```

### 3. Use Model Caching

Models are automatically cached after first load:
```python
from services.model_manager import model_manager

# First load: downloads/reads from disk
model = model_manager.load_model("model_name", ...)

# Subsequent loads: instant (from memory)
model = model_manager.load_model("model_name", ...)
```

---

## 📝 Adding New Models

### Step 1: Add to ComfyUI Directory

```bash
# Download model
cd /home/ubuntu/ComfyUI/models/unet
wget https://example.com/new_model.safetensors

# Or copy
cp /path/to/new_model.safetensors /home/ubuntu/ComfyUI/models/unet/
```

### Step 2: Update Configuration

Edit `config.py`:

```python
class ModelPaths:
    @property
    def new_model(self) -> Path:
        """New Model Description"""
        return self.settings.models_unet / "new_model.safetensors"
```

### Step 3: Use in Code

```python
from config import model_paths

model = load_model(model_paths.new_model)
```

---

## 🔗 Related Documentation

- [Deployment Guide](AWS_DEPLOYMENT.md)
- [CLI Usage](CLI_README.md)
- [Watermark Removal](WATERMARK_REMOVAL_README.md)
- [Architecture](ARCHITECTURE.md)

---

## 📞 Support

For model-related issues:
- Check model exists: `ls -lh /path/to/model`
- Verify permissions: `ls -la /home/ubuntu/ComfyUI/models`
- Check VRAM: `nvidia-smi`
- Review logs: `sudo image-generator-logs`
