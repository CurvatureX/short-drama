# AWS Deployment Guide

Complete guide for deploying the Image Generation API and CLI on AWS EC2.

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Prerequisites](#prerequisites)
3. [Installation Options](#installation-options)
4. [Full Installation (API + CLI)](#full-installation-api--cli)
5. [CLI-Only Installation](#cli-only-installation)
6. [Configuration](#configuration)
7. [Management Commands](#management-commands)
8. [Security Setup](#security-setup)
9. [Monitoring](#monitoring)
10. [Troubleshooting](#troubleshooting)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                      AWS Infrastructure                  │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌──────────────────┐       ┌────────────────────────┐ │
│  │  EC2 Instance    │       │   Redis Serverless     │ │
│  │  (API Server)    │◄─────►│   (Task Queue)         │ │
│  │                  │       │                        │ │
│  │  - API Server    │       └────────────────────────┘ │
│  │  - Model Service │                                  │
│  │  - CLI Tool      │       ┌────────────────────────┐ │
│  └──────────────────┘       │   S3 Bucket            │ │
│           │                 │   (Asset Storage)      │ │
│           └────────────────►│                        │ │
│                             │  /images/              │ │
│                             │  /videos/              │ │
│                             └────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

**Components:**
- **EC2 Instance**: Hosts API server and models (GPU instance recommended)
- **Redis Serverless**: Task queue and status tracking
- **S3 Bucket**: Storage for input/output images and videos

---

## Prerequisites

### AWS Resources

1. **EC2 Instance**:
   - Instance Type: `g4dn.xlarge` or better (with NVIDIA GPU)
   - OS: Ubuntu 22.04 LTS
   - Storage: 100GB+ EBS volume
   - Security Group: Allow inbound on port 8000

2. **Redis Serverless**:
   - Endpoint: `short-drama-redis-mqc7z9.serverless.use1.cache.amazonaws.com:6379`
   - Security Group: Allow access from EC2

3. **S3 Bucket**:
   - Bucket Name: `short-drama-assets`
   - Folders: `images/`, `videos/`
   - IAM Permissions: Read/Write access

### AWS Credentials

- AWS Access Key ID
- AWS Secret Access Key
- Hugging Face Token (optional, for model downloads)

---

## Installation Options

### Option 1: Full Installation (API Server + CLI)

Install both the API server and CLI tool on the same instance.

**Best for:**
- Single-server deployments
- Development/testing environments
- All-in-one solutions

### Option 2: CLI-Only Installation

Install only the CLI tool that connects to a remote API server.

**Best for:**
- Multiple client machines
- Distributed setups
- When API server is running elsewhere

---

## Full Installation (API + CLI)

### 1. Launch EC2 Instance

```bash
# SSH into your EC2 instance
ssh -i your-key.pem ubuntu@your-instance-ip
```

### 2. Download and Run Installation Script

```bash
# Download installation script
curl -o install.sh https://raw.githubusercontent.com/your-repo/short-drama/main/backend/generator/install.sh

# Make executable
chmod +x install.sh

# Run as root
sudo ./install.sh
```

The script will:
- ✅ Install system dependencies (Python 3.11, Git, etc.)
- ✅ Install uv package manager
- ✅ Create service user (`image-gen`)
- ✅ Set up Python virtual environment
- ✅ Install Python dependencies
- ✅ Create systemd service
- ✅ Set up logging and log rotation
- ✅ Create helper scripts
- ✅ Install NVIDIA drivers (if GPU detected)
- ✅ Create global CLI command

### 3. Configure Environment

Edit the `.env` file with your credentials:

```bash
sudo nano /opt/image-generator/.env
```

Add your credentials:

```env
# Redis Configuration
REDIS_HOST=short-drama-redis-mqc7z9.serverless.use1.cache.amazonaws.com
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=

# AWS S3 Configuration
AWS_ACCESS_KEY_ID=your_access_key_here
AWS_SECRET_ACCESS_KEY=your_secret_key_here
AWS_REGION=us-east-1
S3_BUCKET_NAME=short-drama-assets

# Hugging Face Configuration
HF_TOKEN=your_hf_token_here
```

### 4. Start the API Server

```bash
# Start service
sudo image-generator-start

# Check status
sudo image-generator-status

# View logs
sudo image-generator-logs
```

### 5. Test Installation

```bash
# Test API server
curl http://localhost:8000/health

# Test model info endpoint
curl http://localhost:8000/api/qwen-multi-angle/info

# Test CLI
image-generate info
```

### 6. Test Image Generation

```bash
image-generate change_angle \
  -i https://short-drama-assets.s3.us-east-1.amazonaws.com/images/test.png \
  -p "将镜头向左旋转45度" \
  -o output.png
```

---

## CLI-Only Installation

For machines that only need the CLI (not the API server):

### 1. Download and Run CLI Installation Script

```bash
# Download CLI-only installation script
curl -o install-cli-only.sh https://raw.githubusercontent.com/your-repo/short-drama/main/backend/generator/install-cli-only.sh

# Make executable
chmod +x install-cli-only.sh

# Run (no sudo needed)
./install-cli-only.sh
```

### 2. Test CLI

```bash
# Point to your API server
image-generate --api-url http://your-api-server:8000 info

# Generate image
image-generate --api-url http://your-api-server:8000 change_angle \
  -i https://short-drama-assets.s3.us-east-1.amazonaws.com/images/test.png \
  -p "将镜头向左旋转45度" \
  -o output.png
```

### 3. Set Default API URL (Optional)

Create an alias:

```bash
# Add to ~/.bashrc
echo 'alias image-generate="image-generate --api-url http://your-api-server:8000"' >> ~/.bashrc
source ~/.bashrc
```

---

## Configuration

### Environment Variables

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `REDIS_HOST` | Redis server hostname | Yes | - |
| `REDIS_PORT` | Redis server port | No | 6379 |
| `REDIS_DB` | Redis database number | No | 0 |
| `REDIS_PASSWORD` | Redis password | No | - |
| `AWS_ACCESS_KEY_ID` | AWS access key | Yes | - |
| `AWS_SECRET_ACCESS_KEY` | AWS secret key | Yes | - |
| `AWS_REGION` | AWS region | No | us-east-1 |
| `S3_BUCKET_NAME` | S3 bucket name | Yes | short-drama-assets |
| `HF_TOKEN` | Hugging Face token | No | - |

### Firewall Configuration

```bash
# Allow API port
sudo ufw allow 8000/tcp

# Allow SSH
sudo ufw allow 22/tcp

# Enable firewall
sudo ufw enable
```

### Security Group (AWS)

Inbound Rules:
- Port 8000 (API): From your IP or VPC
- Port 22 (SSH): From your IP only
- Port 6379 (Redis): From EC2 security group

---

## Management Commands

### Service Management

```bash
# Start service
sudo image-generator-start

# Stop service
sudo image-generator-stop

# Restart service
sudo image-generator-restart

# Check status
sudo image-generator-status

# View logs (follow mode)
sudo image-generator-logs
```

### systemctl Commands

```bash
# Enable service (start on boot)
sudo systemctl enable image-generator

# Disable service
sudo systemctl disable image-generator

# View service status
sudo systemctl status image-generator

# View logs
sudo journalctl -u image-generator -n 100

# Follow logs
sudo journalctl -u image-generator -f
```

### Log Management

Logs are stored in:
- Access logs: `/var/log/image-generator/access.log`
- Error logs: `/var/log/image-generator/error.log`
- Journal logs: `journalctl -u image-generator`

```bash
# View recent logs
tail -f /var/log/image-generator/access.log

# View error logs
tail -f /var/log/image-generator/error.log

# Search logs
grep "error" /var/log/image-generator/error.log
```

---

## Security Setup

### 1. SSL/TLS Configuration (Production)

Install Nginx as reverse proxy:

```bash
sudo apt install nginx certbot python3-certbot-nginx

# Configure Nginx
sudo nano /etc/nginx/sites-available/image-generator
```

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
# Enable site
sudo ln -s /etc/nginx/sites-available/image-generator /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx

# Get SSL certificate
sudo certbot --nginx -d your-domain.com
```

### 2. API Key Authentication (Optional)

Add to your application for production use.

### 3. IAM Roles (Recommended)

Instead of using access keys, attach an IAM role to the EC2 instance:

```bash
# Remove access keys from .env
# Attach IAM role with S3 and Redis access
```

---

## Monitoring

### 1. System Monitoring

```bash
# CPU and memory
htop

# GPU utilization (if GPU instance)
nvidia-smi

# Disk usage
df -h

# Service status
systemctl status image-generator
```

### 2. Application Monitoring

```bash
# View recent requests
sudo image-generator-logs

# Check API health
curl http://localhost:8000/health

# Get model info
curl http://localhost:8000/api/qwen-multi-angle/info | jq
```

### 3. CloudWatch Integration (Optional)

Install CloudWatch agent for metrics:

```bash
wget https://s3.amazonaws.com/amazoncloudwatch-agent/ubuntu/amd64/latest/amazon-cloudwatch-agent.deb
sudo dpkg -i amazon-cloudwatch-agent.deb
```

---

## Troubleshooting

### Service Won't Start

```bash
# Check service status
sudo systemctl status image-generator

# View detailed logs
sudo journalctl -u image-generator -n 100 --no-pager

# Check permissions
ls -la /opt/image-generator/

# Verify .env file
sudo cat /opt/image-generator/.env
```

### Connection Errors

```bash
# Test Redis connection
redis-cli -h short-drama-redis-mqc7z9.serverless.use1.cache.amazonaws.com ping

# Test S3 access
aws s3 ls s3://short-drama-assets/

# Check firewall
sudo ufw status

# Check security group (AWS Console)
```

### GPU Not Detected

```bash
# Check GPU
lspci | grep -i nvidia

# Install drivers
sudo apt install nvidia-driver-535

# Reboot
sudo reboot

# Verify installation
nvidia-smi
```

### Out of Memory

```bash
# Check memory usage
free -h

# Check swap
swapon --show

# Add swap if needed
sudo fallocate -l 8G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

### CLI Connection Failed

```bash
# Test API server directly
curl http://your-api-server:8000/health

# Check API URL
image-generate --api-url http://your-api-server:8000 info

# Verify network connectivity
ping your-api-server
telnet your-api-server 8000
```

---

## Performance Optimization

### 1. GPU Optimization

Ensure CUDA is properly configured:

```bash
# Check CUDA version
nvcc --version

# Install CUDA toolkit if needed
sudo apt install nvidia-cuda-toolkit
```

### 2. Model Caching

Models are cached on first load. Warm up the cache:

```bash
# Pre-load models
curl -X POST http://localhost:8000/api/qwen-multi-angle/info
```

### 3. Increase Worker Processes

Edit `/opt/image-generator/server.py` to increase workers if needed.

---

## Backup and Recovery

### Backup Configuration

```bash
# Backup .env file
sudo cp /opt/image-generator/.env /opt/image-generator/.env.backup

# Backup entire installation
sudo tar -czf image-generator-backup.tar.gz /opt/image-generator/
```

### Recovery

```bash
# Restore from backup
sudo tar -xzf image-generator-backup.tar.gz -C /

# Restart service
sudo systemctl restart image-generator
```

---

## Updates

### Update Application

```bash
# Pull latest code
cd /opt/image-generator
sudo -u image-gen git pull

# Reinstall dependencies
sudo -u image-gen bash << 'EOF'
source .venv/bin/activate
uv pip install -e .
EOF

# Restart service
sudo image-generator-restart
```

---

## Uninstallation

```bash
# Stop and disable service
sudo systemctl stop image-generator
sudo systemctl disable image-generator

# Remove service file
sudo rm /etc/systemd/system/image-generator.service

# Remove installation directory
sudo rm -rf /opt/image-generator

# Remove helper scripts
sudo rm /usr/local/bin/image-generator-*
sudo rm /usr/local/bin/image-generate

# Remove service user
sudo userdel -r image-gen

# Remove logs
sudo rm -rf /var/log/image-generator
```

---

## Support

For issues and questions:
- Check logs: `sudo image-generator-logs`
- Review documentation: `/opt/image-generator/CLI_README.md`
- GitHub Issues: [Your repository link]

---

## Appendix

### A. Installation Paths

| Component | Path |
|-----------|------|
| Installation | `/opt/image-generator/` |
| Virtual Environment | `/opt/image-generator/.venv/` |
| Configuration | `/opt/image-generator/.env` |
| Logs | `/var/log/image-generator/` |
| Service File | `/etc/systemd/system/image-generator.service` |
| CLI Binary | `/usr/local/bin/image-generate` |

### B. Port Usage

| Port | Service | Protocol |
|------|---------|----------|
| 8000 | API Server | HTTP |
| 6379 | Redis | TCP |

### C. Resource Requirements

**Minimum:**
- CPU: 4 cores
- RAM: 16GB
- Storage: 50GB
- GPU: NVIDIA with 8GB VRAM

**Recommended:**
- CPU: 8 cores
- RAM: 32GB
- Storage: 100GB
- GPU: NVIDIA with 16GB+ VRAM (e.g., T4, V100, A10G)
