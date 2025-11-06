# Deployment Summary - Image Generation Service

Complete AWS deployment package for the Qwen Multi-Angle Image Generation API and CLI.

## 🎯 What's Included

### 1. Installation Scripts

| Script | Purpose | Usage |
|--------|---------|-------|
| **`install.sh`** | Full installation (API + CLI) | `sudo ./install.sh` |
| **`install-cli-only.sh`** | CLI only | `./install-cli-only.sh` |

### 2. Documentation

| Document | Description |
|----------|-------------|
| **`AWS_DEPLOYMENT.md`** | Complete deployment guide |
| **`CLI_README.md`** | CLI user manual |
| **`CLI_QUICK_START.md`** | Quick reference guide |
| **`ARCHITECTURE.md`** | System architecture |

### 3. Service Management

Automated systemd service with helper scripts:
- `image-generator-start`
- `image-generator-stop`
- `image-generator-restart`
- `image-generator-status`
- `image-generator-logs`

---

## 🚀 Quick Start

### For Full Deployment (API Server + CLI)

```bash
# 1. SSH to EC2 instance
ssh -i key.pem ubuntu@your-instance

# 2. Download and run installer
curl -o install.sh https://your-repo/install.sh
chmod +x install.sh
sudo ./install.sh

# 3. Configure credentials
sudo nano /opt/image-generator/.env
# Add: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, etc.

# 4. Start service
sudo image-generator-start

# 5. Test
image-generate info
```

### For CLI-Only Installation

```bash
# 1. Download and run CLI installer
curl -o install-cli-only.sh https://your-repo/install-cli-only.sh
chmod +x install-cli-only.sh
./install-cli-only.sh

# 2. Test
image-generate --api-url http://api-server:8000 info
```

---

## 📦 What Gets Installed

### Full Installation

```
/opt/image-generator/          # Installation directory
├── .venv/                     # Python virtual environment
├── .env                       # Configuration file
├── cli.py                     # CLI tool
├── server.py                  # API server
├── config.py                  # Configuration module
├── models/                    # Model endpoints
└── services/                  # Backend services

/etc/systemd/system/
└── image-generator.service    # Systemd service

/usr/local/bin/
├── image-generate             # CLI command
├── image-generator-start      # Helper scripts
├── image-generator-stop
├── image-generator-restart
├── image-generator-status
└── image-generator-logs

/var/log/image-generator/      # Log directory
├── access.log                 # Access logs
└── error.log                  # Error logs
```

### CLI-Only Installation

```
/usr/local/bin/
└── image-generate             # CLI command only
```

---

## 🔑 Required AWS Resources

### 1. EC2 Instance

**Specifications:**
- Instance Type: `g4dn.xlarge` or better (GPU recommended)
- OS: Ubuntu 22.04 LTS
- Storage: 100GB+ EBS
- Security Group: Allow port 8000

**Estimated Cost:** ~$0.50-1.00/hour

### 2. Redis Serverless

**Configuration:**
- Endpoint: `short-drama-redis-mqc7z9.serverless.use1.cache.amazonaws.com:6379`
- Purpose: Task queue and status tracking
- Access: From EC2 security group

**Estimated Cost:** ~$0.125/GB-hour

### 3. S3 Bucket

**Configuration:**
- Bucket: `short-drama-assets`
- Folders: `images/`, `videos/`
- Access: Read/Write from EC2

**Estimated Cost:** ~$0.023/GB/month

### 4. IAM Permissions

Required permissions:
- S3: `s3:PutObject`, `s3:GetObject`, `s3:ListBucket`
- Redis: VPC access if needed

---

## 🎨 Features Deployed

### API Endpoints

```
POST /api/qwen-multi-angle/i2i
  - Image-to-image transformation
  - Camera angle changes
  - Full ComfyUI workflow support

GET /api/qwen-multi-angle/info
  - Model information
  - System status

GET /api/{session_id}/status
  - Task status tracking

GET /health
  - Health check

GET /docs
  - API documentation (Swagger UI)
```

### CLI Commands

```bash
# Change camera angle
image-generate change_angle -i <url> -p <prompt>

# Check task status
image-generate status <session_id>

# Get model info
image-generate info
```

### Supported Operations

All ComfyUI workflow features:
- ✅ Image scaling to megapixels
- ✅ Multi-Angle LoRA (camera control)
- ✅ Lightning LoRA (fast 8-step generation)
- ✅ ModelSamplingAuraFlow (shift=3.0)
- ✅ CFG normalization
- ✅ Euler scheduler
- ✅ Async task processing
- ✅ S3 storage integration
- ✅ Redis status tracking

### Camera Angle Instructions (Chinese)

- 将镜头向前移动 (Move forward)
- 将镜头向左/右移动 (Move left/right)
- 将镜头向下移动 (Move down)
- 将镜头向左/右旋转45度 (Rotate 45°)
- 将镜头转为俯视 (Top-down view)
- 将镜头转为广角镜头 (Wide-angle)
- 将镜头转为特写镜头 (Close-up)

---

## 🔧 Configuration

### Environment Variables

Create `/opt/image-generator/.env`:

```env
# Redis Configuration
REDIS_HOST=short-drama-redis-mqc7z9.serverless.use1.cache.amazonaws.com
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=

# AWS S3 Configuration
AWS_ACCESS_KEY_ID=AKIAXXXXXXXXXXXXXXXX
AWS_SECRET_ACCESS_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
AWS_REGION=us-east-1
S3_BUCKET_NAME=short-drama-assets

# Task Configuration
TASK_TTL=3600

# Hugging Face Configuration (optional)
HF_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### Security Group Rules

**Inbound:**
- Port 8000: From your IP or VPC
- Port 22: From your IP only
- Port 6379 (Redis): From EC2 security group

**Outbound:**
- All traffic (for model downloads and S3 access)

---

## 📊 Service Management

### Start/Stop Service

```bash
# Using helper scripts (recommended)
sudo image-generator-start
sudo image-generator-stop
sudo image-generator-restart
sudo image-generator-status
sudo image-generator-logs

# Using systemctl directly
sudo systemctl start image-generator
sudo systemctl stop image-generator
sudo systemctl restart image-generator
sudo systemctl status image-generator
```

### View Logs

```bash
# Follow live logs
sudo image-generator-logs

# View access logs
tail -f /var/log/image-generator/access.log

# View error logs
tail -f /var/log/image-generator/error.log

# Search logs
grep "error" /var/log/image-generator/error.log
```

### Auto-Start on Boot

```bash
# Enable (already done by installer)
sudo systemctl enable image-generator

# Disable
sudo systemctl disable image-generator
```

---

## 🧪 Testing

### 1. Test API Server

```bash
# Health check
curl http://localhost:8000/health

# Model info
curl http://localhost:8000/api/qwen-multi-angle/info | jq

# API docs
curl http://localhost:8000/docs
```

### 2. Test CLI

```bash
# Info command
image-generate info

# Change angle (end-to-end test)
image-generate change_angle \
  -i https://short-drama-assets.s3.us-east-1.amazonaws.com/images/test.png \
  -p "将镜头向左旋转45度" \
  --num_inference_steps 8 \
  -o output.png

# Check status
image-generate status <session_id>
```

### 3. Test from Remote Machine

```bash
# Install CLI only on remote machine
./install-cli-only.sh

# Test connection
image-generate --api-url http://ec2-instance:8000 info

# Generate image
image-generate --api-url http://ec2-instance:8000 change_angle \
  -i https://short-drama-assets.s3.us-east-1.amazonaws.com/images/test.png \
  -p "将镜头转为俯视"
```

---

## 📈 Monitoring

### System Resources

```bash
# CPU and Memory
htop

# GPU utilization
nvidia-smi

# Disk usage
df -h

# Network
netstat -tulpn | grep 8000
```

### Application Metrics

```bash
# Service status
sudo systemctl status image-generator

# Recent requests
sudo journalctl -u image-generator -n 50

# Error count
grep -c "error" /var/log/image-generator/error.log
```

### Performance Testing

```bash
# Load test with Apache Bench
ab -n 100 -c 10 http://localhost:8000/health

# Monitor during generation
watch -n 1 nvidia-smi
```

---

## 🔒 Security Checklist

- [ ] Configure firewall (`ufw`)
- [ ] Restrict port 8000 to known IPs
- [ ] Use IAM roles instead of access keys
- [ ] Enable SSL/TLS with Nginx reverse proxy
- [ ] Set up log rotation (already done)
- [ ] Restrict `.env` file permissions (already done)
- [ ] Regular security updates (`apt update && apt upgrade`)
- [ ] Monitor access logs for suspicious activity
- [ ] Use VPC for Redis and S3 access
- [ ] Enable CloudTrail for audit logs

---

## 🐛 Troubleshooting

### Common Issues

**Service won't start:**
```bash
sudo journalctl -u image-generator -n 100
# Check: .env file, permissions, dependencies
```

**Connection refused:**
```bash
# Check service is running
sudo systemctl status image-generator

# Check port
netstat -tulpn | grep 8000
```

**GPU not detected:**
```bash
# Check GPU
nvidia-smi

# Reinstall drivers
sudo apt install nvidia-driver-535
sudo reboot
```

**Out of memory:**
```bash
# Check memory
free -h

# Add swap
sudo fallocate -l 8G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

**Redis connection failed:**
```bash
# Test connection
redis-cli -h short-drama-redis-mqc7z9.serverless.use1.cache.amazonaws.com ping

# Check security group
```

---

## 📚 Documentation Files

| File | Description | For |
|------|-------------|-----|
| `AWS_DEPLOYMENT.md` | Complete deployment guide | Ops/DevOps |
| `CLI_README.md` | CLI user manual | End users |
| `CLI_QUICK_START.md` | Quick reference | End users |
| `ARCHITECTURE.md` | System architecture | Developers |
| `install.sh` | Full installation script | Ops |
| `install-cli-only.sh` | CLI installation script | End users |

---

## 🔄 Updates

### Update Application

```bash
# Pull latest changes
cd /opt/image-generator
sudo -u image-gen git pull

# Update dependencies
sudo -u image-gen bash << 'EOF'
source .venv/bin/activate
uv pip install -e .
EOF

# Restart service
sudo image-generator-restart
```

### Update Models

Models are downloaded automatically on first use and cached.

To clear cache:
```bash
rm -rf ~/.cache/huggingface/
```

---

## 💰 Cost Estimation

**Monthly costs for moderate usage:**

| Resource | Specification | Estimated Cost |
|----------|--------------|----------------|
| EC2 (g4dn.xlarge) | GPU instance, 24/7 | ~$400-500/mo |
| Redis Serverless | 1GB storage | ~$3-5/mo |
| S3 Storage | 100GB | ~$2-3/mo |
| S3 Requests | 1M requests | ~$5-10/mo |
| Data Transfer | 500GB out | ~$45/mo |
| **Total** | | **~$455-563/mo** |

**Cost optimization tips:**
- Use EC2 Spot Instances (60-70% savings)
- Stop instance when not in use
- Use S3 Lifecycle policies
- Enable S3 Intelligent-Tiering

---

## 📞 Support

For issues and questions:

1. Check logs: `sudo image-generator-logs`
2. Review documentation in `/opt/image-generator/`
3. Check GitHub issues
4. Contact support team

---

## ✅ Deployment Checklist

### Pre-Deployment

- [ ] EC2 instance launched
- [ ] Security groups configured
- [ ] Redis endpoint available
- [ ] S3 bucket created
- [ ] IAM permissions configured
- [ ] SSH key pair created

### During Deployment

- [ ] Run installation script
- [ ] Configure `.env` file
- [ ] Start service
- [ ] Verify service status
- [ ] Test API endpoints
- [ ] Test CLI commands

### Post-Deployment

- [ ] Configure firewall
- [ ] Set up SSL/TLS (production)
- [ ] Configure monitoring
- [ ] Set up backups
- [ ] Document instance details
- [ ] Test failover/recovery

### Production Readiness

- [ ] Load testing completed
- [ ] Security audit passed
- [ ] Monitoring dashboards created
- [ ] Alerts configured
- [ ] Documentation updated
- [ ] Team trained
- [ ] Runbook created

---

## 🎓 Training Materials

### For Developers

- System architecture: `ARCHITECTURE.md`
- API documentation: http://your-instance:8000/docs
- Model service: `services/qwen_service.py`

### For Operators

- Deployment guide: `AWS_DEPLOYMENT.md`
- Service management: Helper scripts
- Troubleshooting: Section in deployment guide

### For End Users

- CLI guide: `CLI_README.md`
- Quick start: `CLI_QUICK_START.md`
- Examples: In documentation files

---

**Deployment Package Version:** 1.0.0
**Last Updated:** 2025-01-06
**Maintained By:** Short Drama Project Team
