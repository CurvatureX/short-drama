# Image Generation Service - Complete Deployment Package

Everything you need to deploy the Qwen Multi-Angle Image Generation API and CLI on AWS.

## 📦 Package Contents

This deployment package includes:

1. **Installation Scripts** - Automated setup for AWS EC2
2. **CLI Tool** - Command-line interface for image generation
3. **API Server** - FastAPI-based REST API
4. **Documentation** - Complete guides and references
5. **Service Management** - Systemd service with helpers
6. **Configuration** - Environment and security setup

---

## 🚀 Quick Deployment (3 Steps)

### For AWS EC2 Instance

```bash
# 1. Download and run installer
curl -o install.sh https://your-repo/backend/generator/install.sh
chmod +x install.sh
sudo ./install.sh

# 2. Configure credentials
sudo nano /opt/image-generator/.env
# Add: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY

# 3. Start and test
sudo image-generator-start
image-generate info
```

**Done!** Your API server is running and CLI is ready.

---

## 📚 Documentation Index

| Document | Purpose | Audience |
|----------|---------|----------|
| **[DEPLOYMENT_SUMMARY.md](DEPLOYMENT_SUMMARY.md)** | Overview and checklist | Everyone |
| **[AWS_DEPLOYMENT.md](AWS_DEPLOYMENT.md)** | Complete deployment guide | DevOps/Ops |
| **[CLI_README.md](CLI_README.md)** | CLI user manual | End Users |
| **[CLI_QUICK_START.md](CLI_QUICK_START.md)** | Quick reference | End Users |
| **[ARCHITECTURE.md](ARCHITECTURE.md)** | System architecture | Developers |

### Installation Scripts

| Script | Purpose | Usage |
|--------|---------|-------|
| **[install.sh](install.sh)** | Full installation | `sudo ./install.sh` |
| **[install-cli-only.sh](install-cli-only.sh)** | CLI only | `./install-cli-only.sh` |

---

## 🎯 Choose Your Deployment Type

### Option 1: Full Installation (API + CLI)

**Best for:**
- Production deployments
- Single-server setups
- Development environments

**What you get:**
- API server (FastAPI)
- Qwen Multi-Angle model service
- CLI tool
- Systemd service
- Helper scripts
- Logging and monitoring

**Installation:**
```bash
sudo ./install.sh
```

**Read:** [AWS_DEPLOYMENT.md](AWS_DEPLOYMENT.md)

---

### Option 2: CLI-Only Installation

**Best for:**
- Client machines
- Multiple workstations
- Distributed setups

**What you get:**
- CLI tool only
- Connects to remote API server

**Installation:**
```bash
./install-cli-only.sh
```

**Read:** [CLI_QUICK_START.md](CLI_QUICK_START.md)

---

## 💡 Usage Examples

### Basic Image Generation

```bash
image-generate change_angle \
  -i https://short-drama-assets.s3.us-east-1.amazonaws.com/images/scene.png \
  -p "将镜头向左旋转45度" \
  -o rotated.png
```

### Advanced Options

```bash
image-generate change_angle \
  -i s3://short-drama-assets/images/test.png \
  -p "将镜头转为俯视" \
  -n "blurry, low quality" \
  --num_inference_steps 8 \
  --guidance_scale 1.0 \
  --seed 42 \
  --scale_to_megapixels 1.0 \
  --scheduler_shift 3.0 \
  -o output.png \
  -v
```

### Check Status

```bash
image-generate status <session_id>
```

### Get Model Info

```bash
image-generate info
```

---

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────┐
│           AWS Infrastructure                 │
├─────────────────────────────────────────────┤
│                                              │
│  EC2 Instance (g4dn.xlarge)                 │
│  ┌──────────────────────────────┐           │
│  │  API Server (Port 8000)      │           │
│  │  - FastAPI                   │           │
│  │  - Qwen Model Service        │           │
│  │  - Image Processing          │           │
│  └────────────┬─────────────────┘           │
│               │                              │
│  ┌────────────▼─────────────┐               │
│  │  Redis Serverless        │               │
│  │  (Task Queue)            │               │
│  └──────────────────────────┘               │
│                                              │
│  ┌──────────────────────────┐               │
│  │  S3 Bucket               │               │
│  │  - images/               │               │
│  │  - videos/               │               │
│  └──────────────────────────┘               │
│                                              │
└─────────────────────────────────────────────┘

Client Machines
┌──────────────────────┐
│  CLI Tool            │
│  image-generate      │
└──────────────────────┘
```

---

## 🔑 Prerequisites

### AWS Resources Needed

1. **EC2 Instance**
   - Type: g4dn.xlarge or better (GPU recommended)
   - OS: Ubuntu 22.04 LTS
   - Storage: 100GB+ EBS
   - Security Group: Allow port 8000

2. **Redis Serverless**
   - Endpoint: `short-drama-redis-mqc7z9.serverless.use1.cache.amazonaws.com`
   - Port: 6379

3. **S3 Bucket**
   - Name: `short-drama-assets`
   - Folders: `images/`, `videos/`

4. **IAM Credentials**
   - AWS_ACCESS_KEY_ID
   - AWS_SECRET_ACCESS_KEY
   - S3 Read/Write permissions

---

## ⚙️ Features

### API Capabilities

- ✅ Image-to-image transformation
- ✅ Camera angle changes (9+ angles)
- ✅ Multi-Angle LoRA support
- ✅ Lightning LoRA (8-step fast generation)
- ✅ Full ComfyUI workflow replication
- ✅ Async task processing
- ✅ Redis-based status tracking
- ✅ S3 storage integration
- ✅ RESTful API with Swagger docs

### CLI Features

- ✅ Easy-to-use command-line interface
- ✅ Progress tracking with visual indicators
- ✅ Automatic result download
- ✅ Status checking
- ✅ Model information retrieval
- ✅ Async mode support
- ✅ Verbose logging option
- ✅ Remote API connection

### Supported Camera Angles (Chinese)

- 将镜头向前移动 - Move camera forward
- 将镜头向左/右移动 - Move camera left/right
- 将镜头向下移动 - Move camera down
- 将镜头向左/右旋转45度 - Rotate 45 degrees
- 将镜头转为俯视 - Top-down view
- 将镜头转为广角镜头 - Wide-angle lens
- 将镜头转为特写镜头 - Close-up shot

---

## 🛠️ Management

### Service Control

```bash
# Start service
sudo image-generator-start

# Stop service
sudo image-generator-stop

# Restart service
sudo image-generator-restart

# Check status
sudo image-generator-status

# View logs
sudo image-generator-logs
```

### Monitoring

```bash
# System resources
htop
nvidia-smi
df -h

# Application logs
tail -f /var/log/image-generator/access.log
tail -f /var/log/image-generator/error.log

# Service status
systemctl status image-generator
```

---

## 🔒 Security

### Configuration

1. **Firewall Setup**
   ```bash
   sudo ufw allow 8000/tcp
   sudo ufw allow 22/tcp
   sudo ufw enable
   ```

2. **Environment Variables**
   - Stored in `/opt/image-generator/.env`
   - Permissions: 600 (owner only)
   - Never commit to version control

3. **SSL/TLS** (Production)
   - Use Nginx reverse proxy
   - Get certificate with Let's Encrypt
   - See [AWS_DEPLOYMENT.md](AWS_DEPLOYMENT.md) for details

---

## 📊 Performance

### Resource Requirements

**Minimum:**
- CPU: 4 cores
- RAM: 16GB
- Storage: 50GB
- GPU: 8GB VRAM

**Recommended:**
- CPU: 8+ cores
- RAM: 32GB
- Storage: 100GB
- GPU: 16GB+ VRAM (T4, V100, A10G)

### Optimization Tips

- Use GPU instances for best performance
- Enable model caching (automatic)
- Use Lightning LoRA (8 steps vs 40)
- Scale images to 1MP for faster processing
- Monitor VRAM usage with `nvidia-smi`

---

## 🧪 Testing

### Automated Tests

```bash
# Health check
curl http://localhost:8000/health

# API documentation
curl http://localhost:8000/docs

# Model info
image-generate info
```

### Manual Testing

```bash
# End-to-end test
image-generate change_angle \
  -i https://short-drama-assets.s3.us-east-1.amazonaws.com/images/test.png \
  -p "将镜头向左旋转45度" \
  -o test_output.png
```

---

## 🐛 Troubleshooting

### Quick Checks

```bash
# Is service running?
sudo systemctl status image-generator

# Check logs
sudo journalctl -u image-generator -n 50

# Test connectivity
curl http://localhost:8000/health

# GPU available?
nvidia-smi
```

### Common Issues

See [AWS_DEPLOYMENT.md](AWS_DEPLOYMENT.md) § Troubleshooting for detailed solutions.

---

## 📈 Monitoring & Alerts

### CloudWatch Integration (Optional)

```bash
# Install CloudWatch agent
wget https://s3.amazonaws.com/amazoncloudwatch-agent/ubuntu/amd64/latest/amazon-cloudwatch-agent.deb
sudo dpkg -i amazon-cloudwatch-agent.deb
```

### Metrics to Monitor

- API response times
- GPU utilization
- Memory usage
- Task success/failure rates
- S3 upload/download times

---

## 🔄 Updates

### Update Application

```bash
cd /opt/image-generator
sudo -u image-gen git pull
sudo -u image-gen .venv/bin/pip install -e .
sudo image-generator-restart
```

### Update System

```bash
sudo apt update
sudo apt upgrade -y
sudo reboot  # If kernel updated
```

---

## 💰 Cost Estimation

**Monthly costs (24/7 operation):**

| Resource | Cost |
|----------|------|
| EC2 g4dn.xlarge | ~$400-500 |
| Redis Serverless | ~$3-5 |
| S3 Storage (100GB) | ~$2-3 |
| S3 Requests | ~$5-10 |
| Data Transfer | ~$45 |
| **Total** | **~$455-563** |

**Cost Optimization:**
- Use Spot Instances (60-70% savings)
- Stop when not in use
- Use S3 lifecycle policies

---

## 📞 Support

### Documentation

- **Deployment:** [AWS_DEPLOYMENT.md](AWS_DEPLOYMENT.md)
- **CLI Usage:** [CLI_README.md](CLI_README.md)
- **Quick Start:** [CLI_QUICK_START.md](CLI_QUICK_START.md)
- **Architecture:** [ARCHITECTURE.md](ARCHITECTURE.md)
- **Summary:** [DEPLOYMENT_SUMMARY.md](DEPLOYMENT_SUMMARY.md)

### Getting Help

1. Check logs: `sudo image-generator-logs`
2. Review documentation
3. Check GitHub issues
4. Contact support team

---

## 📝 License

Part of the Short Drama project.

---

## 🎉 Getting Started

Ready to deploy? Start here:

1. **For Production Deployment:**
   - Read [DEPLOYMENT_SUMMARY.md](DEPLOYMENT_SUMMARY.md)
   - Follow [AWS_DEPLOYMENT.md](AWS_DEPLOYMENT.md)
   - Run `install.sh`

2. **For CLI Users:**
   - Read [CLI_QUICK_START.md](CLI_QUICK_START.md)
   - Run `install-cli-only.sh`
   - Start using `image-generate`

3. **For Developers:**
   - Review [ARCHITECTURE.md](ARCHITECTURE.md)
   - Check API docs at `/docs` endpoint
   - Explore source code

---

**Happy Deploying! 🚀**
