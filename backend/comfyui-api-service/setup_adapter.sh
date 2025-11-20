#!/bin/bash
# Setup script for SQS Adapter on GPU EC2 instance
# Run this script on the GPU instance to deploy the adapter service

set -e

echo "=========================================="
echo "SQS Adapter Setup Script"
echo "=========================================="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Please run as root (use sudo)"
    exit 1
fi

# Configuration
SERVICE_DIR="/home/ubuntu/comfyui_api_service"
SERVICE_FILE="/etc/systemd/system/sqs-adapter.service"
LOG_DIR="/var/log"

# Step 1: Create service directory if it doesn't exist
echo "1. Creating service directory..."
mkdir -p "$SERVICE_DIR"
chown ubuntu:ubuntu "$SERVICE_DIR"

# Step 2: Copy adapter script
echo "2. Copying adapter script..."
if [ ! -f "$SERVICE_DIR/sqs_to_comfy_adapter.py" ]; then
    echo "   ERROR: sqs_to_comfy_adapter.py not found in $SERVICE_DIR"
    echo "   Please copy the script to $SERVICE_DIR first"
    exit 1
fi
chmod +x "$SERVICE_DIR/sqs_to_comfy_adapter.py"

# Step 3: Install Python dependencies
echo "3. Installing Python dependencies..."
/home/ubuntu/ComfyUI/venv/bin/pip install boto3 requests python-dotenv

# Step 4: Create log files
echo "4. Creating log files..."
touch "$LOG_DIR/sqs-adapter.log"
touch "$LOG_DIR/sqs-adapter-error.log"
chown ubuntu:ubuntu "$LOG_DIR/sqs-adapter.log"
chown ubuntu:ubuntu "$LOG_DIR/sqs-adapter-error.log"

# Step 5: Copy systemd service file
echo "5. Installing systemd service..."
if [ ! -f "$SERVICE_DIR/sqs-adapter.service" ]; then
    echo "   ERROR: sqs-adapter.service not found in $SERVICE_DIR"
    echo "   Please copy the service file to $SERVICE_DIR first"
    exit 1
fi
cp "$SERVICE_DIR/sqs-adapter.service" "$SERVICE_FILE"

# Step 6: Prompt for SQS Queue URL
echo ""
echo "6. Configuration required:"
read -p "   Enter SQS Queue URL: " SQS_QUEUE_URL
if [ -z "$SQS_QUEUE_URL" ]; then
    echo "   ERROR: SQS Queue URL is required"
    exit 1
fi

# Update service file with SQS Queue URL
sed -i "s|Environment=\"SQS_QUEUE_URL=.*\"|Environment=\"SQS_QUEUE_URL=$SQS_QUEUE_URL\"|" "$SERVICE_FILE"

# Step 7: Reload systemd
echo ""
echo "7. Reloading systemd..."
systemctl daemon-reload

# Step 8: Enable service
echo "8. Enabling service to start on boot..."
systemctl enable sqs-adapter.service

# Step 9: Start service
echo "9. Starting service..."
systemctl start sqs-adapter.service

# Step 10: Check status
echo ""
echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo ""
echo "Service Status:"
systemctl status sqs-adapter.service --no-pager
echo ""
echo "Useful commands:"
echo "  - View logs:        sudo journalctl -u sqs-adapter -f"
echo "  - View error logs:  sudo tail -f /var/log/sqs-adapter-error.log"
echo "  - Restart service:  sudo systemctl restart sqs-adapter"
echo "  - Stop service:     sudo systemctl stop sqs-adapter"
echo "  - Check status:     sudo systemctl status sqs-adapter"
echo ""
