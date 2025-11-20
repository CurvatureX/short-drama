#!/bin/bash
# Setup systemd services for ComfyUI and API

set -e

echo "Setting up ComfyUI and API services..."

# Check if running as root or with sudo
if [ "$EUID" -ne 0 ]; then
    echo "Please run with sudo"
    exit 1
fi

# Copy service files
echo "Copying service files..."
cp comfyui.service /etc/systemd/system/
cp comfyui-api.service /etc/systemd/system/

# Update S3_BUCKET in service file
read -p "Enter your S3 bucket name: " s3_bucket
read -p "Enter AWS region (default: us-east-1): " aws_region
aws_region=${aws_region:-us-east-1}

sed -i "s/your-bucket-name/$s3_bucket/g" /etc/systemd/system/comfyui-api.service
sed -i "s/us-east-1/$aws_region/g" /etc/systemd/system/comfyui-api.service

# Create log files
echo "Creating log files..."
touch /var/log/comfyui.log /var/log/comfyui-error.log
touch /var/log/comfyui-api.log /var/log/comfyui-api-error.log
chown ubuntu:ubuntu /var/log/comfyui*.log

# Reload systemd
echo "Reloading systemd..."
systemctl daemon-reload

# Enable services
echo "Enabling services..."
systemctl enable comfyui.service
systemctl enable comfyui-api.service

# Start services
echo "Starting services..."
systemctl start comfyui.service
sleep 10  # Wait for ComfyUI to start
systemctl start comfyui-api.service

# Check status
echo ""
echo "Service status:"
echo "==============="
systemctl status comfyui.service --no-pager
echo ""
systemctl status comfyui-api.service --no-pager

echo ""
echo "Setup complete!"
echo ""
echo "Useful commands:"
echo "  sudo systemctl status comfyui"
echo "  sudo systemctl status comfyui-api"
echo "  sudo systemctl restart comfyui"
echo "  sudo systemctl restart comfyui-api"
echo "  sudo journalctl -u comfyui -f"
echo "  sudo journalctl -u comfyui-api -f"
echo "  tail -f /var/log/comfyui.log"
echo "  tail -f /var/log/comfyui-api.log"
