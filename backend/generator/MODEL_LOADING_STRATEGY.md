# Model Loading Strategy - Local First with HuggingFace Fallback

This document explains how the application intelligently loads AI models.

## 🎯 Overview

The application uses a **local-first with HuggingFace fallback** strategy:

1. **Try local models first** - Fast, no network required
2. **Automatically download from HuggingFace if missing** - No manual intervention needed
3. **Cache downloaded models** - Future loads are fast

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────┐
│         Model Loading Request                    │
└─────────────────┬───────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────┐
│         services/model_loader.py                 │
│                                                   │
│  1. Check local path                             │
│     /home/ubuntu/ComfyUI/models/...              │
│     ├── Found? ──────┐                           │
│     └── Not found    │                           │
│                      │                           │
│  2. Download from HF │                           │
│     HuggingFace Hub  │                           │
│     ├── Cache to     │                           │
│     │   ~/.cache/... │                           │
│     └── Return ──────┤                           │
│                      │                           │
│  3. Load & Return ◄──┘                           │
└─────────────────────────────────────────────────┘
```

## 📚 Usage Examples

### Basic Model Loading

```python
from services.model_loader import model_loader
from config import model_paths
from diffusers import DiffusionPipeline

# Automatic fallback
model = model_loader.load_safetensors_model(
    local_path=model_paths.qwen_image_edit_unet,     # Try local first
    hf_repo="Qwen/Qwen-Image-Edit-2509",             # Fallback to HF
    model_class=DiffusionPipeline,
    torch_dtype=torch.float16,
)
```

### Loading LoRA Weights

```python
# Load LoRA with fallback
model_loader.load_lora_weights(
    pipeline=pipe,
    local_path=model_paths.qwen_multi_angle_lora,    # Try local
    hf_repo="dx8152/Qwen-Edit-2509-Multiple-angles", # Fallback to HF
    adapter_name="multi_angle",
)
```

### Checking Model Source

```python
# Check which source will be used
source, path = model_loader.get_model_source(
    local_path=model_paths.qwen_image_edit_unet,
    hf_repo="Qwen/Qwen-Image-Edit-2509",
)

if source == "local":
    print(f"Will load from local: {path}")
elif source == "huggingface":
    print(f"Will download from HuggingFace: {path}")
else:
    print("Model not available")
```

## 🔧 Configuration

### Setting Up Local Models

Place models in ComfyUI directory structure:

```bash
/home/ubuntu/ComfyUI/models/
├── diffusion_models/
│   └── qwen-image-edit/
│       └── qwen_image_edit_2509_fp8_e4m3fn.safetensors
├── loras/
│   ├── 镜头转换.safetensors
│   └── qwen-image-edit-lightning/
│       └── Qwen-Image-Edit-Lightning-4steps-V1.0.safetensors
├── unet/
│   └── Wan2_1-MiniMaxRemover_1_3B_fp16.safetensors
└── vae/
    ├── qwen_image_vae.safetensors
    └── Wan2_1_VAE_bf16.safetensors
```

### Setting Base Path

In `.env`:

```bash
# Local models directory
COMFYUI_MODELS_BASE=/home/ubuntu/ComfyUI/models

# Optional: HuggingFace token for private models
HF_TOKEN=your_hf_token_here
```

## 🎯 Model Mappings

| Service | Local Path | HuggingFace Repo | Filename |
|---------|-----------|-----------------|----------|
| **Qwen i2i UNET** | `model_paths.qwen_image_edit_unet` | `Qwen/Qwen-Image-Edit-2509` | Auto |
| **Qwen Multi-Angle LoRA** | `model_paths.qwen_multi_angle_lora` | `dx8152/Qwen-Edit-2509-Multiple-angles` | Auto |
| **Qwen Lightning LoRA** | `model_paths.qwen_edit_lightning_lora` | `lightx2v/Qwen-Image-Edit-Lightning` | `Qwen-Image-Edit-Lightning-4steps-V1.0.safetensors` |
| **WanVideo UNET** | `model_paths.wan_minimax_remover_unet` | `WanVideo/Wan2_1-MiniMaxRemover` | `Wan2_1-MiniMaxRemover_1_3B_fp16.safetensors` |
| **WanVideo VAE** | `model_paths.wan_vae` | `WanVideo/Wan2_1` | `Wan2_1_VAE_bf16.safetensors` |
| **FLUX Checkpoint** | `model_paths.flux_checkpoint` | `black-forest-labs/FLUX.1-dev` | Auto |

## 📊 Loading Flow Examples

### Scenario 1: Local Model Available

```
User Request
    │
    ▼
Check /home/ubuntu/ComfyUI/models/unet/Wan2_1-MiniMaxRemover_1_3B_fp16.safetensors
    │
    ├── File exists (2.6 GB)
    │
    ▼
Load from local file (fast, ~2-3 seconds)
    │
    ▼
Model ready for use
```

### Scenario 2: Local Model Missing, Download from HF

```
User Request
    │
    ▼
Check /home/ubuntu/ComfyUI/models/unet/Wan2_1-MiniMaxRemover_1_3B_fp16.safetensors
    │
    ├── File not found
    │
    ▼
Download from HuggingFace: WanVideo/Wan2_1-MiniMaxRemover
    │
    ├── Download to ~/.cache/huggingface/hub/
    │   (Progress: [████████████████████] 2.6 GB)
    │
    ▼
Load from cached file
    │
    ▼
Model ready for use
```

### Scenario 3: Subsequent Loads (After Download)

```
User Request
    │
    ▼
Check local path (not found)
    │
    ▼
Check HuggingFace cache (~/.cache/huggingface/)
    │
    ├── Found in cache!
    │
    ▼
Load from cache (fast, ~2-3 seconds)
    │
    ▼
Model ready for use
```

## 🚀 Performance Characteristics

| Source | First Load | Subsequent Loads | Network Required |
|--------|-----------|-----------------|-----------------|
| **Local files** | 2-3 seconds | 2-3 seconds | ❌ No |
| **HF download** | 5-30 minutes* | 2-3 seconds | ✅ Yes (first time) |
| **HF cache** | 2-3 seconds | 2-3 seconds | ❌ No |

*Download time depends on model size and network speed

## 🛡️ Error Handling

The loader handles various error scenarios:

### Local File Not Found
```
[WARNING] Failed to load from local path: FileNotFoundError
[INFO] Downloading from HuggingFace: Qwen/Qwen-Image-Edit-2509
```

### Network Error During Download
```
[ERROR] Failed to download from HuggingFace: ConnectionError
[ERROR] Model not found at local path and HuggingFace download failed
```

### Invalid Model File
```
[ERROR] Failed to load model: safetensors.SafetensorError
[INFO] Attempting to re-download from HuggingFace...
```

## 💡 Best Practices

### 1. Pre-download Models on Production Servers

```bash
# Download all models to local directory
python -c "
from services.model_loader import model_loader
from config import model_paths

# Download Qwen models
model_loader.load_safetensors_model(
    local_path=model_paths.qwen_image_edit_unet,
    hf_repo='Qwen/Qwen-Image-Edit-2509',
)
"
```

### 2. Use Local Models for Development

```bash
# Copy models from production to dev
rsync -avz \
  ubuntu@prod:/home/ubuntu/ComfyUI/models/ \
  /home/ubuntu/ComfyUI/models/
```

### 3. Set HuggingFace Token for Private Models

```bash
# In .env
HF_TOKEN=hf_your_token_here
```

### 4. Monitor Download Progress

The loader logs download progress:

```
[INFO] Downloading from HuggingFace: WanVideo/Wan2_1-MiniMaxRemover
[INFO] Downloading file: Wan2_1-MiniMaxRemover_1_3B_fp16.safetensors
[INFO] Downloaded to cache: /home/ubuntu/.cache/huggingface/hub/models--WanVideo--Wan2_1-MiniMaxRemover/...
```

## 🔍 Troubleshooting

### Issue: Models downloading every time

**Cause**: HuggingFace cache cleared or `local_files_only=True` set

**Solution**:
```python
# Don't use local_files_only with the new loader
# It handles fallback automatically
model = model_loader.load_safetensors_model(
    local_path=model_paths.qwen_image_edit_unet,
    hf_repo="Qwen/Qwen-Image-Edit-2509",
    # Don't set local_files_only
)
```

### Issue: Download fails with authentication error

**Cause**: Private model requires HuggingFace token

**Solution**: Add token to `.env`:
```bash
HF_TOKEN=hf_your_token_here
```

### Issue: Out of disk space during download

**Cause**: Not enough space in `~/.cache/huggingface/`

**Solution**:
```bash
# Clear HuggingFace cache
rm -rf ~/.cache/huggingface/hub/

# Or move cache to larger drive
export HF_HOME=/mnt/large-drive/huggingface
```

## 📈 Cache Management

### Check Cache Size

```bash
du -sh ~/.cache/huggingface/
# Output: 45G    /home/ubuntu/.cache/huggingface/
```

### Clear Old Models

```python
from huggingface_hub import scan_cache_dir

# List cached models
cache_info = scan_cache_dir()
for repo in cache_info.repos:
    print(f"{repo.repo_id}: {repo.size_on_disk / (1024**3):.2f} GB")

# Delete specific model
from huggingface_hub import delete_cache
delete_cache(repos=["old-model/name"])
```

## 🔗 Related Documentation

- [Model Configuration Guide](MODEL_CONFIGURATION.md)
- [Deployment Guide](AWS_DEPLOYMENT.md)
- [CLI Documentation](CLI_README.md)

## 📝 Implementation Details

The `ModelLoader` class in `services/model_loader.py` provides:

- `load_safetensors_model()` - Load models with fallback
- `load_lora_weights()` - Load LoRA weights with fallback
- `get_model_source()` - Check which source will be used
- `_load_from_local()` - Internal method for local loading
- `_load_from_huggingface()` - Internal method for HF download

All services (`qwen_service.py`, `watermark_service.py`, `flux_service.py`) use this unified loader.
