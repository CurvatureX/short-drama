#!/bin/bash
set -e

# Installation script for existing cloned repository
# Run this from the generator directory: sudo ./install-local.sh

echo "🚀 Image Generation Installation (from local directory)"
echo "========================================================"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

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

# Get current directory (where script is run from)
CURRENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "Current directory: $CURRENT_DIR"

# Configuration
INSTALL_DIR="/opt/image-generator"
SERVICE_USER="image-gen"
VENV_DIR="${INSTALL_DIR}/venv"

print_status "Starting installation from: $CURRENT_DIR"

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
    ffmpeg \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    redis-tools \
    htop \
    > /dev/null 2>&1

print_status "System dependencies installed"

# Step 2: Check for GPU and drivers
echo ""
echo "🎮 Checking for GPU..."
if command -v nvidia-smi &> /dev/null; then
    GPU_INFO=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -n 1)
    print_status "NVIDIA GPU detected: $GPU_INFO"
    print_status "NVIDIA drivers already installed (nvidia-smi found)"
elif lspci | grep -i nvidia > /dev/null; then
    print_warning "NVIDIA GPU detected but drivers not installed"
    read -p "Install NVIDIA drivers? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Installing NVIDIA drivers..."
        apt-get install -y nvidia-driver-535 nvidia-cuda-toolkit > /dev/null 2>&1
        print_status "NVIDIA drivers installed"
        print_warning "Reboot required for drivers to take effect"
    fi
else
    print_warning "No NVIDIA GPU detected (CPU mode only)"
fi

# Step 3: Create service user
echo ""
echo "👤 Setting up service user..."
if ! id "$SERVICE_USER" &>/dev/null; then
    useradd -r -s /bin/bash -d "$INSTALL_DIR" -m "$SERVICE_USER"
    print_status "Service user '$SERVICE_USER' created"
else
    print_warning "Service user '$SERVICE_USER' already exists"
fi

# Step 4: Create installation directory and copy files
echo ""
echo "📁 Setting up installation directory..."
mkdir -p "$INSTALL_DIR"

# Copy files from current directory to installation directory
print_status "Copying files from $CURRENT_DIR to $INSTALL_DIR..."
rsync -av --exclude='venv' --exclude='__pycache__' --exclude='.git' \
    "$CURRENT_DIR/" "$INSTALL_DIR/" > /dev/null 2>&1

chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"
print_status "Files copied to: $INSTALL_DIR"

# Step 5: Create Python virtual environment
echo ""
echo "🐍 Setting up Python virtual environment..."
cd "$INSTALL_DIR"

if [ ! -d "$VENV_DIR" ]; then
    sudo -u "$SERVICE_USER" python3.11 -m venv "$VENV_DIR"
    print_status "Virtual environment created"
else
    print_warning "Virtual environment already exists"
fi

# Step 6: Install Python dependencies
echo ""
echo "📦 Installing Python dependencies (this may take a few minutes)..."
sudo -u "$SERVICE_USER" bash -c "
cd '$INSTALL_DIR'
source '$VENV_DIR/bin/activate'
pip install --upgrade pip > /dev/null 2>&1
pip install uv > /dev/null 2>&1
uv pip install -e '$INSTALL_DIR' > /dev/null 2>&1
"

print_status "Python dependencies installed"

# Step 7: Set up .env file
echo ""
echo "⚙️  Setting up environment configuration..."
if [ ! -f "$INSTALL_DIR/.env" ]; then
    if [ -f "$CURRENT_DIR/.env" ]; then
        cp "$CURRENT_DIR/.env" "$INSTALL_DIR/.env"
        print_status "Copied existing .env file"
    else
        cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
        print_status "Created .env from .env.example"
        print_warning "IMPORTANT: Edit $INSTALL_DIR/.env and add your HF_TOKEN!"
    fi
    chown "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR/.env"
    chmod 600 "$INSTALL_DIR/.env"
else
    print_warning "Environment file already exists: $INSTALL_DIR/.env"
fi

# Step 8: Create log directory
echo ""
echo "📝 Setting up logging..."
mkdir -p /var/log/image-generator
chown "$SERVICE_USER:$SERVICE_USER" /var/log/image-generator
print_status "Log directory created: /var/log/image-generator"

# Step 9: Create systemd service
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
ExecStart=$VENV_DIR/bin/python -m uvicorn server:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10
StandardOutput=append:/var/log/image-generator/access.log
StandardError=append:/var/log/image-generator/error.log

# Security settings
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
SERVICEEOF

print_status "Systemd service created"

# Step 10: Install CLI globally
echo ""
echo "🔗 Installing CLI command..."
ln -sf "$VENV_DIR/bin/image-generate" /usr/local/bin/image-generate
print_status "CLI installed: image-generate"

# Step 11: Create helper commands
echo ""
echo "🛠️  Creating helper commands..."

# Start command
cat > /usr/local/bin/image-generator-start << 'STARTEOF'
#!/bin/bash
sudo systemctl start image-generator
sudo systemctl status image-generator
STARTEOF
chmod +x /usr/local/bin/image-generator-start

# Stop command
cat > /usr/local/bin/image-generator-stop << 'STOPEOF'
#!/bin/bash
sudo systemctl stop image-generator
STOPEOF
chmod +x /usr/local/bin/image-generator-stop

# Restart command
cat > /usr/local/bin/image-generator-restart << 'RESTARTEOF'
#!/bin/bash
sudo systemctl restart image-generator
sudo systemctl status image-generator
RESTARTEOF
chmod +x /usr/local/bin/image-generator-restart

# Status command
cat > /usr/local/bin/image-generator-status << 'STATUSEOF'
#!/bin/bash
sudo systemctl status image-generator
STATUSEOF
chmod +x /usr/local/bin/image-generator-status

# Logs command
cat > /usr/local/bin/image-generator-logs << 'LOGSEOF'
#!/bin/bash
sudo journalctl -u image-generator -f
LOGSEOF
chmod +x /usr/local/bin/image-generator-logs

print_status "Helper commands created"

# Step 12: Enable and start service
echo ""
echo "🚀 Starting service..."
systemctl daemon-reload
systemctl enable image-generator

read -p "Start the service now? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    systemctl start image-generator
    sleep 2
    systemctl status image-generator --no-pager
    print_status "Service started"
else
    print_warning "Service not started. Start manually with: sudo systemctl start image-generator"
fi

# Installation complete
echo ""
echo "=============================================="
echo -e "${GREEN}✅ Installation Complete!${NC}"
echo "=============================================="
echo ""
echo "📋 Service Management:"
echo "  Start:   sudo systemctl start image-generator"
echo "           or: sudo image-generator-start"
echo ""
echo "  Stop:    sudo systemctl stop image-generator"
echo "           or: sudo image-generator-stop"
echo ""
echo "  Restart: sudo systemctl restart image-generator"
echo "           or: sudo image-generator-restart"
echo ""
echo "  Status:  sudo systemctl status image-generator"
echo "           or: sudo image-generator-status"
echo ""
echo "  Logs:    sudo journalctl -u image-generator -f"
echo "           or: sudo image-generator-logs"
echo ""
echo "📋 CLI Commands:"
echo "  image-generate info"
echo "  image-generate change_angle -i <url> -p \"prompt\" -o output.png"
echo "  image-generate remove_watermark_image -i <url> -o clean.png"
echo "  image-generate --help"
echo ""
echo "🌐 API Documentation:"
echo "  http://localhost:8000/docs"
echo ""
echo "⚠️  Important Notes:"
echo "  1. Make sure your .env file has HF_TOKEN set"
echo "     Edit: sudo nano $INSTALL_DIR/.env"
echo ""
echo "  2. Ensure EC2 instance has IAM role for S3 access"
echo "     See: AWS_IAM_SETUP.md"
echo ""
echo "  3. Models will download automatically on first use"
echo "     This may take time - check logs with: sudo image-generator-logs"
echo ""
echo "  4. If you have NVIDIA GPU, reboot after driver installation"
echo ""
