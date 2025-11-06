# Quick Setup Guide - AWS Instance

You've cloned the project to your AWS instance. Here's how to set it up.

## 🎯 Choose Your Setup

### Option 1: Full Installation (API Server + CLI)
Run the full server with API endpoints and background processing.

### Option 2: CLI Only
Just install the CLI tool to connect to a remote API server.

---

## 🚀 Option 1: Full Installation (Recommended)

This installs everything: API server, background workers, models, and CLI.

### Step 1: Navigate to Project Directory

```bash
cd /path/to/short-drama/backend/generator
```

### Step 2: Copy and Configure .env

```bash
# Copy the example
cp .env.example .env

# Edit .env and set your HF token
nano .env
```

Add your HuggingFace token:
```bash
HF_TOKEN=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
```

**Note**: AWS credentials (S3) are NOT needed. The EC2 IAM role provides them automatically.

### Step 3: Run Installation Script

```bash
# Make script executable
chmod +x install.sh

# Run installation (requires sudo)
sudo ./install.sh
```

This will:
- ✅ Install Python 3.11 and dependencies
- ✅ Install system packages (ffmpeg, opencv, etc.)
- ✅ Set up virtual environment at `/opt/image-generator/`
- ✅ Install GPU drivers (if NVIDIA GPU detected)
- ✅ Create systemd service
- ✅ Install CLI tool globally (`image-generate` command)
- ✅ Start the service automatically

### Step 4: Verify Installation

```bash
# Check service status
sudo systemctl status image-generator

# Check logs
sudo journalctl -u image-generator -f

# Test CLI
image-generate info
```

### Step 5: Test API

```bash
# Health check
curl http://localhost:8000/

# Test with CLI
image-generate change_angle \
  -i https://short-drama-assets.s3.us-east-1.amazonaws.com/images/test.png \
  -p "将镜头向左旋转45度" \
  -o output.png
```

---

## 🔧 Option 2: CLI Only

Install just the CLI tool to connect to a remote API server.

### Step 1: Run CLI Installation Script

```bash
cd /path/to/short-drama/backend/generator

# Make script executable
chmod +x install-cli-only.sh

# Run installation
sudo ./install-cli-only.sh
```

### Step 2: Set API URL

```bash
# Test with custom API URL
image-generate --api-url http://your-api-server:8000 info
```

Or create an alias:
```bash
# Add to ~/.bashrc or ~/.zshrc
echo 'alias image-generate="image-generate --api-url http://your-api-server:8000"' >> ~/.bashrc
source ~/.bashrc
```

---

## 📦 Manual Installation (Alternative)

If you prefer to install manually without the installation script:

### 1. Install Dependencies

```bash
# Update system
sudo apt-get update

# Install Python 3.11
sudo apt-get install -y python3.11 python3.11-venv python3-pip

# Install system dependencies
sudo apt-get install -y \
  ffmpeg \
  libsm6 \
  libxext6 \
  libxrender-dev \
  libgomp1 \
  git

# Install GPU drivers (if you have NVIDIA GPU)
# Check for GPU
lspci | grep -i nvidia

# If GPU detected, install NVIDIA drivers
sudo apt-get install -y nvidia-driver-535 nvidia-cuda-toolkit
```

### 2. Set Up Virtual Environment

```bash
# Create directory
sudo mkdir -p /opt/image-generator
sudo chown $USER:$USER /opt/image-generator
cd /opt/image-generator

# Clone or copy your project
cp -r /path/to/generator/* .

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Upgrade pip and install uv
pip install --upgrade pip
pip install uv

# Install dependencies
uv pip install -r requirements.txt
```

### 3. Configure Environment

```bash
# Copy .env file
cp .env.example .env

# Edit and add HF token
nano .env
```

Add:
```bash
HF_TOKEN=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
COMFYUI_MODELS_BASE=/home/ubuntu/ComfyUI/models
```

### 4. Install as Editable Package

```bash
# Make sure you're in the venv
source /opt/image-generator/venv/bin/activate

# Install in editable mode
uv pip install -e .
```

This makes the `image-generate` CLI available in the virtual environment.

### 5. Create Systemd Service (Optional)

```bash
# Create service file
sudo nano /etc/systemd/system/image-generator.service
```

Paste:
```ini
[Unit]
Description=Image Generation API Server
After=network.target

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=/opt/image-generator
Environment="PATH=/opt/image-generator/venv/bin"
ExecStart=/opt/image-generator/venv/bin/python -m uvicorn server:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable image-generator
sudo systemctl start image-generator
sudo systemctl status image-generator
```

---

## 🔍 Verification

### Check Service is Running

```bash
# Via systemd
sudo systemctl status image-generator

# Via curl
curl http://localhost:8000/
```

Expected output:
```json
{
  "status": "online",
  "service": "Image/Video Generation API",
  "version": "1.0.0",
  "models": ["flux", "qwen-multi-angle", "watermark-removal"],
  "redis_connected": true
}
```

### Check CLI

```bash
# Get model info
image-generate info

# Test image generation (requires API to be running)
image-generate change_angle \
  -i https://example.com/test.png \
  -p "将镜头向左旋转45度" \
  -o output.png
```

### Check Logs

```bash
# Live logs
sudo journalctl -u image-generator -f

# Last 100 lines
sudo journalctl -u image-generator -n 100

# Logs with timestamps
sudo journalctl -u image-generator --since "10 minutes ago"
```

---

## 🐛 Troubleshooting

### Issue: ModuleNotFoundError

**Cause**: Dependencies not installed correctly

**Solution**:
```bash
cd /opt/image-generator
source venv/bin/activate
uv pip install -r requirements.txt
```

### Issue: Permission Denied

**Cause**: Wrong file permissions

**Solution**:
```bash
sudo chown -R ubuntu:ubuntu /opt/image-generator
chmod +x /opt/image-generator/venv/bin/*
```

### Issue: Service Won't Start

**Check logs**:
```bash
sudo journalctl -u image-generator -n 50 --no-pager
```

**Common causes**:
- Port 8000 already in use
- Missing dependencies
- Wrong Python path in service file

**Solution**:
```bash
# Check what's using port 8000
sudo lsof -i :8000

# Kill if needed
sudo kill -9 $(sudo lsof -t -i:8000)

# Restart service
sudo systemctl restart image-generator
```

### Issue: S3 Access Denied

**Cause**: EC2 instance doesn't have IAM role

**Solution**: See [AWS_IAM_SETUP.md](AWS_IAM_SETUP.md) for detailed instructions.

Quick check:
```bash
# Check if instance has IAM role
curl http://169.254.169.254/latest/meta-data/iam/security-credentials/

# Test S3 access
aws s3 ls s3://short-drama-assets/
```

### Issue: Models Not Found

**Cause**: Models haven't been downloaded yet

**Solution**: Models will download automatically on first use. Check logs:
```bash
sudo journalctl -u image-generator -f
```

You'll see:
```
[INFO] Loading Qwen i2i model...
[INFO] Model not found at local path
[INFO] Downloading from HuggingFace: Qwen/Qwen-Image-Edit-2509
```

**Pre-download models** (optional):
```bash
cd /opt/image-generator
source venv/bin/activate
python -c "
from services.model_loader import model_loader
from config import model_paths

# This will download all models
model_loader.load_safetensors_model(
    local_path=model_paths.qwen_image_edit_unet,
    hf_repo='Qwen/Qwen-Image-Edit-2509',
)
"
```

---

## 📊 System Requirements

### Minimum

- **CPU**: 4 cores
- **RAM**: 16 GB
- **GPU**: NVIDIA GPU with 8GB VRAM (optional but recommended)
- **Storage**: 50 GB free space
- **OS**: Ubuntu 20.04 or 22.04

### Recommended

- **CPU**: 8+ cores
- **RAM**: 32 GB
- **GPU**: NVIDIA GPU with 24GB VRAM (A10G, A100, etc.)
- **Storage**: 100 GB SSD
- **Instance Type**: AWS g4dn.xlarge or better

---

## 🔗 Next Steps

1. **Configure Models**: See [MODEL_CONFIGURATION.md](MODEL_CONFIGURATION.md)
2. **Set Up IAM Role**: See [AWS_IAM_SETUP.md](AWS_IAM_SETUP.md)
3. **Learn CLI Commands**: See [CLI_README.md](CLI_README.md)
4. **API Documentation**: Visit http://localhost:8000/docs

---

## 📞 Need Help?

- Check logs: `sudo journalctl -u image-generator -f`
- Review documentation in the project directory
- Check system stats: `curl http://localhost:8000/api/system/stats`
