# Architecture Overview

## ComfyUI-Style Resource Management

This server implements advanced resource management capabilities similar to ComfyUI for efficient model inference.

## Core Components

### 1. Model Manager (`services/model_manager.py`)

**Features:**
- **LRU Cache**: Keeps frequently used models in memory with configurable cache size
- **Memory-Mapped Loading**: Efficient model loading with minimal RAM overhead
- **Dynamic Loading**: Models loaded on-demand and cached for reuse
- **Automatic Eviction**: Least recently used models evicted when cache is full

**Configuration:**
```python
model_manager = ModelManager(
    max_models_in_memory=2,      # Max models to cache
    max_cache_size_gb=20.0,      # Max cache size
    enable_memory_efficient_loading=True
)
```

**Key Methods:**
- `load_model()` - Load or retrieve model from cache
- `get_cache_stats()` - Get cache statistics
- `clear_cache()` - Clear all cached models
- `preload_model()` - Preload model in background

### 2. VRAM Manager (`services/vram_manager.py`)

**Features:**
- **Real-time Monitoring**: Track GPU memory usage via NVIDIA ML or PyTorch
- **Automatic Cleanup**: Clear cache when memory usage is high
- **Memory Profiling**: Track memory usage per model
- **Smart Offloading**: Automatic CPU offloading decisions

**VRAM States:**
- `LOW` - < 50% used
- `MODERATE` - 50-75% used
- `HIGH` - 75-90% used
- `CRITICAL` - > 90% used

**Key Methods:**
- `get_vram_stats()` - Get current VRAM statistics
- `clear_cache()` - Clear CUDA cache
- `should_offload_to_cpu()` - Check if offloading is needed
- `cleanup_if_needed()` - Automatic cleanup when memory is high

### 3. Queue Manager (`services/queue_manager.py`)

**Features:**
- **Priority Queue**: Tasks processed by priority (URGENT > HIGH > NORMAL > LOW)
- **Fair Scheduling**: Timestamp-based ordering within same priority
- **Concurrent Processing**: Configurable number of concurrent tasks
- **Queue Statistics**: Real-time queue metrics

**Task Priorities:**
```python
class TaskPriority(Enum):
    LOW = 3
    NORMAL = 2
    HIGH = 1
    URGENT = 0
```

**Key Methods:**
- `submit_task()` - Add task to queue
- `get_next_task()` - Get next task to process
- `get_queue_stats()` - Get queue statistics
- `cancel_task()` - Cancel queued task

### 4. Optimization Manager (`services/optimization.py`)

**Features:**
- **Mixed Precision**: Automatic mixed precision (AMP) with bfloat16/float16
- **Attention Optimization**: xformers or Flash Attention support
- **VAE Optimization**: VAE slicing and tiling for memory efficiency
- **TF32 Acceleration**: TF32 enabled for Ampere GPUs

**Key Methods:**
- `autocast()` - Context manager for mixed precision
- `enable_attention_optimization()` - Enable attention optimizations
- `optimize_model()` - Apply all optimizations to model
- `get_optimal_dtype()` - Get best dtype for current hardware

## Memory Management Strategy

### Loading Strategy

1. **Check VRAM**: Assess current memory state
2. **Cleanup**: Clear cache if memory is high
3. **Load Model**: Use memory-efficient loading
4. **Apply Optimizations**: Enable attention optimizations, mixed precision
5. **CPU Offloading**: Offload to CPU if VRAM is critical

### Inference Strategy

1. **Get Cached Model**: Retrieve from cache or load
2. **Mixed Precision**: Use bfloat16 for inference
3. **Monitor VRAM**: Track memory usage before/after
4. **Cleanup**: Clear cache after generation if needed

### Eviction Strategy

- **LRU**: Least recently used models evicted first
- **Size-Based**: Respect max cache size limits
- **On-Demand**: Models evicted only when necessary

## Optimization Techniques

### 1. Memory Mapping
```python
low_cpu_mem_usage=True  # Memory-mapped loading
```

### 2. Mixed Precision
```python
torch_dtype=torch.bfloat16  # Use bfloat16 for better performance
```

### 3. Attention Optimization
```python
# xformers or Flash Attention
model.enable_xformers_memory_efficient_attention()
model.enable_attention_slicing(slice_size="auto")
```

### 4. CPU Offloading
```python
model.enable_model_cpu_offload()  # Offload to CPU when needed
```

### 5. VAE Optimization
```python
model.vae.enable_slicing()  # Reduce VAE memory
model.vae.enable_tiling()   # Tile-based VAE decoding
```

### 6. TF32
```python
torch.backends.cuda.matmul.allow_tf32 = True
torch.backends.cudnn.allow_tf32 = True
```

## Performance Characteristics

### Memory Usage

| Component | Memory (bfloat16) | Notes |
|-----------|-------------------|-------|
| Flux.1-dev | ~12GB VRAM | With CPU offloading |
| Flux.1-dev | ~20GB VRAM | Full GPU loading |
| Cache Overhead | ~100MB | Per cached model |

### Speed Optimizations

- **First Generation**: 30-60s (model loading)
- **Cached Generations**: 15-30s (no loading)
- **With xformers**: 20-30% faster
- **With TF32**: 10-15% faster on Ampere GPUs

## Monitoring

### System Stats Endpoint

```bash
GET /api/system/stats
```

Returns:
```json
{
  "vram": {
    "device": "cuda",
    "total_vram_mb": 16384,
    "used_vram_mb": 12288,
    "free_vram_mb": 4096,
    "utilization_percent": 75.0,
    "state": "high"
  },
  "models": {
    "cached_models": 1,
    "max_models": 2,
    "models": [...]
  },
  "queue": {
    "queued": 2,
    "active": 1,
    "completed": 15,
    "failed": 0
  },
  "optimizations": {
    "amp_enabled": true,
    "xformers_available": false,
    "flash_attention_available": true,
    "optimal_dtype": "torch.bfloat16"
  }
}
```

### Manual Cleanup

```bash
POST /api/system/cleanup
```

Manually trigger VRAM cleanup and cache clearing.

## Configuration

### Environment Variables

```env
# Maximum models in cache
MAX_MODELS_IN_MEMORY=2

# Maximum cache size in GB
MAX_CACHE_SIZE_GB=20.0

# Enable memory-efficient loading
MEMORY_EFFICIENT_LOADING=true

# Maximum concurrent tasks
MAX_CONCURRENT_TASKS=2
```

## Best Practices

1. **Monitor VRAM**: Use `/api/system/stats` to monitor memory usage
2. **Adjust Cache Size**: Based on available VRAM
3. **Use Priorities**: Important tasks should use HIGH or URGENT priority
4. **Manual Cleanup**: Trigger cleanup before large batches
5. **Preload Models**: Use `preload_model()` for better responsiveness

## Comparison with ComfyUI

| Feature | This Implementation | ComfyUI |
|---------|---------------------|---------|
| Model Caching | ✅ LRU Cache | ✅ LRU Cache |
| VRAM Management | ✅ Automatic | ✅ Automatic |
| Queue System | ✅ Priority-based | ✅ FIFO |
| Mixed Precision | ✅ AMP | ✅ AMP |
| Attention Opts | ✅ xformers/Flash | ✅ xformers |
| CPU Offloading | ✅ Dynamic | ✅ Manual |
| Batch Processing | 🚧 Planned | ✅ Full Support |
| Model Preloading | ✅ Background | ✅ Background |

## Future Enhancements

- [ ] Batch processing for multiple similar requests
- [ ] Dynamic batch size based on VRAM
- [ ] Model quantization (4-bit, 8-bit)
- [ ] Multi-GPU support
- [ ] Distributed inference
- [ ] Webhook notifications
- [ ] Advanced scheduling algorithms
