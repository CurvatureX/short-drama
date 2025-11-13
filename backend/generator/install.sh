#!/bin/bash
set -e

# Image Generation CLI and API Server Installation Script
# For AWS EC2 instances
#
# Usage:
#   curl -sSL https://raw.githubusercontent.com/.../install.sh | bash
#   or
#   chmod +x install.sh && ./install.sh

echo "🚀 Image Generation CLI & API Server Installation"
echo "=================================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
INSTALL_DIR="/opt/image-generator"
SERVICE_USER="image-gen"
VENV_DIR="${INSTALL_DIR}/.venv"
REPO_URL="https://github.com/your-repo/short-drama.git"  # Update this
BRANCH="main"

# Function to print colored output
print_status() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    print_error "Please run as root (use sudo)"
    exit 1
fi

print_status "Starting installation..."

# Step 1: Install system dependencies
echo ""
echo "📦 Installing system dependencies..."
apt-get update -qq
apt-get install -y \
    python3.11 \
    python3.11-venv \
    python3-pip \
    git \
    curl \
    wget \
    build-essential \
    libssl-dev \
    libffi-dev \
    python3-dev \
    redis-tools \
    htop

print_status "System dependencies installed"

# Step 2: Install uv (fast Python package installer)
echo ""
echo "📦 Installing uv package manager..."
if ! command -v uv &> /dev/null; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$PATH"
    print_status "uv installed"
else
    print_warning "uv already installed"
fi

# Step 3: Create service user
echo ""
echo "👤 Creating service user..."
if ! id "$SERVICE_USER" &>/dev/null; then
    useradd -r -s /bin/bash -d "$INSTALL_DIR" -m "$SERVICE_USER"
    print_status "Service user '$SERVICE_USER' created"
else
    print_warning "Service user '$SERVICE_USER' already exists"
fi

# Step 4: Create installation directory
echo ""
echo "📁 Creating installation directory..."
mkdir -p "$INSTALL_DIR"
chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"
print_status "Installation directory created: $INSTALL_DIR"

# Step 5: Clone or update repository
echo ""
echo "📥 Setting up application code..."
if [ -d "$INSTALL_DIR/backend/generator" ]; then
    print_warning "Code already exists, updating..."
    cd "$INSTALL_DIR"
    sudo -u "$SERVICE_USER" git pull
else
    print_status "Cloning repository..."
    sudo -u "$SERVICE_USER" git clone -b "$BRANCH" "$REPO_URL" "$INSTALL_DIR/repo"
    sudo -u "$SERVICE_USER" cp -r "$INSTALL_DIR/repo/backend/generator/"* "$INSTALL_DIR/"
    sudo -u "$SERVICE_USER" rm -rf "$INSTALL_DIR/repo"
fi

print_status "Application code ready"

# Step 6: Create Python virtual environment
echo ""
echo "🐍 Setting up Python virtual environment..."
cd "$INSTALL_DIR"

if [ ! -d "$VENV_DIR" ]; then
    sudo -u "$SERVICE_USER" python3.11 -m venv "$VENV_DIR"
    print_status "Virtual environment created"
else
    print_warning "Virtual environment already exists"
fi

# Step 7: Install Python dependencies
echo ""
echo "📦 Installing Python dependencies..."
sudo -u "$SERVICE_USER" bash << EOF
source "$VENV_DIR/bin/activate"
pip install --upgrade pip
pip install uv
uv pip install -e "$INSTALL_DIR"
EOF

print_status "Python dependencies installed"

# Step 7.1: Install latest diffusers for Qwen support
echo ""
echo "📦 Installing latest diffusers from git (for Qwen Multi-Angle support)..."
sudo -u "$SERVICE_USER" bash << EOF
source "$VENV_DIR/bin/activate"
pip install git+https://github.com/huggingface/diffusers.git
EOF

print_status "Latest diffusers installed (QwenImageEditPlusPipeline available)"

# Step 8: Create .env file if it doesn't exist
echo ""
echo "⚙️  Setting up environment configuration..."
if [ ! -f "$INSTALL_DIR/.env" ]; then
    cat > "$INSTALL_DIR/.env" << 'ENVEOF'
# Redis Configuration
REDIS_HOST=short-drama-redis-mqc7z9.serverless.use1.cache.amazonaws.com
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=

# AWS S3 Configuration
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_REGION=us-east-1
S3_BUCKET_NAME=short-drama-assets
S3_ENDPOINT_URL=

# Task Configuration
TASK_TTL=3600

# Hugging Face Configuration
HF_TOKEN=
HF_PROVIDER=nebius
ENVEOF

    chown "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR/.env"
    chmod 600 "$INSTALL_DIR/.env"
    print_status "Environment file created: $INSTALL_DIR/.env"
    print_warning "IMPORTANT: Edit $INSTALL_DIR/.env and add your credentials!"
else
    print_warning "Environment file already exists: $INSTALL_DIR/.env"
fi

# Step 9: Create systemd service file
echo ""
echo "🔧 Creating systemd service..."
cat > /etc/systemd/system/image-generator.service << SERVICEEOF
[Unit]
Description=Image Generation API Server
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR
Environment="PATH=$VENV_DIR/bin:/usr/local/bin:/usr/bin:/bin"
EnvironmentFile=$INSTALL_DIR/.env
ExecStart=$VENV_DIR/bin/python $INSTALL_DIR/server.py
Restart=always
RestartSec=10
StandardOutput=append:/var/log/image-generator/access.log
StandardError=append:/var/log/image-generator/error.log

# Security settings
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$INSTALL_DIR /tmp

[Install]
WantedBy=multi-user.target
SERVICEEOF

print_status "Systemd service created"

# Step 10: Create log directory
echo ""
echo "📝 Setting up logging..."
mkdir -p /var/log/image-generator
chown -R "$SERVICE_USER:$SERVICE_USER" /var/log/image-generator
chmod 755 /var/log/image-generator
print_status "Log directory created: /var/log/image-generator"

# Step 11: Set up logrotate
echo ""
echo "🔄 Setting up log rotation..."
cat > /etc/logrotate.d/image-generator << 'LOGROTATEEOF'
/var/log/image-generator/*.log {
    daily
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 image-gen image-gen
    sharedscripts
    postrotate
        systemctl reload image-generator > /dev/null 2>&1 || true
    endscript
}
LOGROTATEEOF

print_status "Log rotation configured"

# Step 12: Create CLI symlink for all users
echo ""
echo "🔗 Creating global CLI command..."
ln -sf "$VENV_DIR/bin/image-generate" /usr/local/bin/image-generate
print_status "CLI command available: image-generate"

# Step 13: Reload systemd and enable service
echo ""
echo "🔧 Configuring service..."
systemctl daemon-reload
systemctl enable image-generator.service
print_status "Service enabled (will start on boot)"

# Step 14: Create admin helper scripts
echo ""
echo "🛠️  Creating helper scripts..."

# Start script
cat > /usr/local/bin/image-generator-start << 'STARTEOF'
#!/bin/bash
systemctl start image-generator
systemctl status image-generator --no-pager
EOF
chmod +x /usr/local/bin/image-generator-start

# Stop script
cat > /usr/local/bin/image-generator-stop << 'STOPEOF'
#!/bin/bash
systemctl stop image-generator
EOF
chmod +x /usr/local/bin/image-generator-stop

# Restart script
cat > /usr/local/bin/image-generator-restart << 'RESTARTEOF'
#!/bin/bash
systemctl restart image-generator
sleep 2
systemctl status image-generator --no-pager
EOF
chmod +x /usr/local/bin/image-generator-restart

# Status script
cat > /usr/local/bin/image-generator-status << 'STATUSEOF'
#!/bin/bash
systemctl status image-generator --no-pager
echo ""
echo "Recent logs:"
journalctl -u image-generator -n 50 --no-pager
EOF
chmod +x /usr/local/bin/image-generator-status

# Logs script
cat > /usr/local/bin/image-generator-logs << 'LOGSEOF'
#!/bin/bash
journalctl -u image-generator -f
EOF
chmod +x /usr/local/bin/image-generator-logs

print_status "Helper scripts created:"
echo "  - image-generator-start"
echo "  - image-generator-stop"
echo "  - image-generator-restart"
echo "  - image-generator-status"
echo "  - image-generator-logs"

# Step 15: Install NVIDIA drivers if GPU detected
echo ""
echo "🎮 Checking for GPU..."
if lspci | grep -i nvidia > /dev/null; then
    print_warning "NVIDIA GPU detected. Installing drivers..."
    apt-get install -y nvidia-driver-535 nvidia-cuda-toolkit
    print_status "NVIDIA drivers installed (reboot required)"
else
    print_warning "No NVIDIA GPU detected, skipping GPU driver installation"
fi

# Installation complete
echo ""
echo "=============================================="
echo -e "${GREEN}✅ Installation Complete!${NC}"
echo "=============================================="
echo ""
echo "📋 Next Steps:"
echo ""
echo "1. Configure credentials:"
echo "   sudo nano $INSTALL_DIR/.env"
echo "   (Add AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, etc.)"
echo ""
echo "2. Start the API server:"
echo "   sudo image-generator-start"
echo ""
echo "3. Check server status:"
echo "   sudo image-generator-status"
echo ""
echo "4. View logs:"
echo "   sudo image-generator-logs"
echo ""
echo "5. Test CLI tool:"
echo "   image-generate info"
echo ""
echo "6. Test image generation:"
echo "   image-generate change_angle \\"
echo "     -i https://short-drama-assets.s3.us-east-1.amazonaws.com/images/test.png \\"
echo "     -p \"将镜头向左旋转45度\" \\"
echo "     -o output.png"
echo ""
echo "📚 Documentation:"
echo "   - CLI Guide: $INSTALL_DIR/CLI_README.md"
echo "   - Quick Start: $INSTALL_DIR/CLI_QUICK_START.md"
echo "   - Architecture: $INSTALL_DIR/ARCHITECTURE.md"
echo ""
echo "🔗 Endpoints:"
echo "   - API: http://localhost:8000"
echo "   - Docs: http://localhost:8000/docs"
echo "   - Health: http://localhost:8000/health"
echo ""
echo "⚠️  Important:"
if lspci | grep -i nvidia > /dev/null; then
    echo "   - GPU detected: Reboot required for driver installation"
fi
echo "   - Configure firewall to allow port 8000"
echo "   - Set up SSL/TLS for production use"
echo ""
