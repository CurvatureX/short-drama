#!/bin/bash
# Setup script for Paid API Service and SQS Adapter on EC2 instance

set -e

echo "================================"
echo "Paid API Service Setup"
echo "================================"

# Check if running as root
if [ "$EUID" -eq 0 ]; then
   echo "Please run as ubuntu user, not root"
   exit 1
fi

# Install system dependencies
echo "Installing system dependencies..."
sudo apt-get update
sudo apt-get install -y python3 python3-pip python3-venv

# Create service directory
SERVICE_DIR="/home/ubuntu/paid-api-service"
mkdir -p $SERVICE_DIR
cd $SERVICE_DIR

# Create Python virtual environment
echo "Creating Python virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
echo "Installing Python dependencies..."
pip install --upgrade pip
pip install fastapi uvicorn pydantic requests boto3 pillow dashscope

# Copy service files (assumes you've already uploaded them)
echo "Service files should be in: $SERVICE_DIR"
echo "  - api_service.py"
echo "  - sqs_adapter.py"
echo "  - face_swap.py"
echo "  - image-to-image/seedream.py"
echo ""

# Create systemd service files
echo "Installing systemd services..."
sudo cp paid-api.service /etc/systemd/system/
sudo cp sqs-adapter.service /etc/systemd/system/

# Update service files with actual values
echo ""
echo "⚠️  IMPORTANT: Update the following in service files:"
echo "  /etc/systemd/system/paid-api.service"
echo "  /etc/systemd/system/sqs-adapter.service"
echo ""
echo "Required environment variables:"
echo "  - DASHSCOPE_API_KEY"
echo "  - ARK_API_KEY"
echo "  - AWS_ACCESS_KEY"
echo "  - AWS_ACCESS_SECRET"
echo "  - CPU_QUEUE_URL"
echo ""
read -p "Press enter after updating the service files..."

# Reload systemd
sudo systemctl daemon-reload

# Enable services (start on boot)
echo "Enabling services..."
sudo systemctl enable paid-api.service
sudo systemctl enable sqs-adapter.service

# Start services
echo "Starting services..."
sudo systemctl start paid-api.service
sudo systemctl start sqs-adapter.service

# Check status
echo ""
echo "================================"
echo "Service Status"
echo "================================"
sudo systemctl status paid-api.service --no-pager
echo ""
sudo systemctl status sqs-adapter.service --no-pager

echo ""
echo "================================"
echo "Setup Complete!"
echo "================================"
echo ""
echo "Useful commands:"
echo "  sudo systemctl status paid-api"
echo "  sudo systemctl status sqs-adapter"
echo "  sudo systemctl restart paid-api"
echo "  sudo systemctl restart sqs-adapter"
echo "  sudo journalctl -u paid-api -f"
echo "  sudo journalctl -u sqs-adapter -f"
echo ""
echo "Health check:"
echo "  curl http://localhost:8000/health"
