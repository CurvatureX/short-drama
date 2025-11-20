#!/usr/bin/env python3
"""
Deploy Paid API Service to a new EC2 instance.

This script:
1. Launches a t3.medium Ubuntu 22.04 instance
2. Uploads service code and dependencies
3. Configures systemd services
4. Starts the services
"""

import boto3
import time
import subprocess
import os
import sys
from pathlib import Path

# Configuration
REGION = 'us-east-1'
INSTANCE_TYPE = 't3.medium'
AMI_ID = 'ami-00b13f11600160c10'  # Ubuntu 22.04 LTS
KEY_NAME = 'zzjw'
SECURITY_GROUP_ID = 'sg-0d83316bc5613e6ff'  # launch-wizard-7
IAM_INSTANCE_PROFILE = 'gpu-instance-profile'  # Has S3, SQS, DynamoDB permissions

# Service configuration
SQS_QUEUE_URL = 'https://sqs.us-east-1.amazonaws.com/982081090398/cpu_tasks_queue'
DYNAMODB_TABLE = 'task_store'
S3_BUCKET = 'short-drama-assets'
CLOUDFRONT_DOMAIN = 'https://d3bg7alr1qwred.cloudfront.net'

# API Keys (will be loaded from environment)
DASHSCOPE_API_KEY = os.getenv('DASHSCOPE_API_KEY')
ARK_API_KEY = os.getenv('ARK_API_KEY')
AWS_ACCESS_KEY = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')

# User data script to run on instance launch
USER_DATA = '''#!/bin/bash
set -e

# Update system
apt-get update
apt-get upgrade -y

# Install Python 3.11 and dependencies
apt-get install -y python3.11 python3.11-venv python3-pip

# Install system dependencies
apt-get install -y build-essential libssl-dev libffi-dev python3-dev

# Create directory for service
mkdir -p /home/ubuntu/paid-api-service
chown ubuntu:ubuntu /home/ubuntu/paid-api-service

echo "Instance initialization complete"
'''


def launch_instance():
    """Launch EC2 instance with required configuration."""
    print("Launching EC2 instance...")

    ec2 = boto3.client('ec2', region_name=REGION)

    response = ec2.run_instances(
        ImageId=AMI_ID,
        InstanceType=INSTANCE_TYPE,
        KeyName=KEY_NAME,
        SecurityGroupIds=[SECURITY_GROUP_ID],
        IamInstanceProfile={'Name': IAM_INSTANCE_PROFILE},
        UserData=USER_DATA,
        MinCount=1,
        MaxCount=1,
        TagSpecifications=[
            {
                'ResourceType': 'instance',
                'Tags': [
                    {'Key': 'Name', 'Value': 'paid-api-service'},
                    {'Key': 'Service', 'Value': 'FaceSwap'},
                    {'Key': 'ManagedBy', 'Value': 'deploy_to_ec2.py'}
                ]
            }
        ],
        BlockDeviceMappings=[
            {
                'DeviceName': '/dev/sda1',
                'Ebs': {
                    'VolumeSize': 30,  # 30 GB storage
                    'VolumeType': 'gp3',
                    'DeleteOnTermination': True
                }
            }
        ]
    )

    instance_id = response['Instances'][0]['InstanceId']
    print(f"✓ Instance launched: {instance_id}")

    # Wait for instance to be running
    print("Waiting for instance to be running...")
    waiter = ec2.get_waiter('instance_running')
    waiter.wait(InstanceIds=[instance_id])

    # Get public IP
    instance_info = ec2.describe_instances(InstanceIds=[instance_id])
    public_ip = instance_info['Reservations'][0]['Instances'][0]['PublicIpAddress']
    print(f"✓ Instance running at {public_ip}")

    return instance_id, public_ip


def wait_for_ssh(public_ip, max_attempts=30):
    """Wait for SSH to be available."""
    print("Waiting for SSH to be available...")

    for attempt in range(max_attempts):
        try:
            result = subprocess.run(
                ['ssh', '-i', f'{Path.home()}/.ssh/zzjw.pem',
                 '-o', 'StrictHostKeyChecking=no',
                 '-o', 'ConnectTimeout=5',
                 f'ubuntu@{public_ip}', 'echo "SSH Ready"'],
                capture_output=True,
                timeout=10
            )
            if result.returncode == 0:
                print("✓ SSH is ready")
                return True
        except:
            pass

        time.sleep(10)
        print(f"  Attempt {attempt + 1}/{max_attempts}...")

    print("✗ SSH connection timeout")
    return False


def upload_code(public_ip):
    """Upload service code to EC2 instance."""
    print("Uploading service code...")

    service_dir = Path(__file__).parent

    # Files to upload
    files = [
        'api_service.py',
        'sqs_adapter.py',
        'face_swap.py',
        'requirements.txt',
        'paid-api.service',
        'sqs-adapter.service',
        'setup_services.sh'
    ]

    # Upload files
    for file in files:
        src = service_dir / file
        if src.exists():
            print(f"  Uploading {file}...")
            subprocess.run([
                'scp', '-i', f'{Path.home()}/.ssh/zzjw.pem',
                '-o', 'StrictHostKeyChecking=no',
                str(src),
                f'ubuntu@{public_ip}:~/paid-api-service/'
            ], check=True)

    # Upload image-to-image directory
    img2img_dir = service_dir / 'image-to-image'
    if img2img_dir.exists():
        print(f"  Uploading image-to-image/...")
        subprocess.run([
            'scp', '-i', f'{Path.home()}/.ssh/zzjw.pem',
            '-o', 'StrictHostKeyChecking=no',
            '-r',
            str(img2img_dir),
            f'ubuntu@{public_ip}:~/paid-api-service/'
        ], check=True)

    print("✓ Code uploaded")


def setup_services(public_ip):
    """Configure and start services on EC2."""
    print("Setting up services...")

    if not DASHSCOPE_API_KEY or not ARK_API_KEY:
        print("✗ Error: DASHSCOPE_API_KEY and ARK_API_KEY must be set in environment")
        sys.exit(1)

    # Create environment file content
    env_content = f"""
export DASHSCOPE_API_KEY='{DASHSCOPE_API_KEY}'
export ARK_API_KEY='{ARK_API_KEY}'
export AWS_ACCESS_KEY_ID='{AWS_ACCESS_KEY}'
export AWS_SECRET_ACCESS_KEY='{AWS_SECRET_KEY}'
export S3_BUCKET_NAME='{S3_BUCKET}'
export CLOUDFRONT_DOMAIN='{CLOUDFRONT_DOMAIN}'
export AWS_DEFAULT_REGION='{REGION}'
export CPU_QUEUE_URL='{SQS_QUEUE_URL}'
export DYNAMODB_TABLE='{DYNAMODB_TABLE}'
export PAID_API_URL='http://localhost:8000'
export AWS_REGION='{REGION}'
"""

    # Commands to run on EC2
    commands = f'''
set -e

# Create .env file
cat > ~/paid-api-service/.env << 'ENVEOF'
{env_content}
ENVEOF

# Make setup script executable
chmod +x ~/paid-api-service/setup_services.sh

# Install dependencies and setup services
cd ~/paid-api-service
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Update systemd service files with environment variables
sudo cp paid-api.service /etc/systemd/system/
sudo cp sqs-adapter.service /etc/systemd/system/

# Update service files with environment variables
sudo sed -i '/\\[Service\\]/a EnvironmentFile=/home/ubuntu/paid-api-service/.env' /etc/systemd/system/paid-api.service
sudo sed -i '/\\[Service\\]/a EnvironmentFile=/home/ubuntu/paid-api-service/.env' /etc/systemd/system/sqs-adapter.service

# Reload systemd
sudo systemctl daemon-reload

# Enable and start services
sudo systemctl enable paid-api
sudo systemctl enable sqs-adapter
sudo systemctl start paid-api
sudo systemctl start sqs-adapter

# Wait for services to start
sleep 5

# Check status
sudo systemctl status paid-api --no-pager || true
sudo systemctl status sqs-adapter --no-pager || true

echo "Setup complete!"
'''

    print("  Installing dependencies and starting services...")
    result = subprocess.run([
        'ssh', '-i', f'{Path.home()}/.ssh/zzjw.pem',
        '-o', 'StrictHostKeyChecking=no',
        f'ubuntu@{public_ip}',
        commands
    ], capture_output=True, text=True)

    print(result.stdout)
    if result.returncode != 0:
        print(f"✗ Setup failed: {result.stderr}")
        return False

    print("✓ Services configured and started")
    return True


def verify_services(public_ip):
    """Verify services are running correctly."""
    print("Verifying services...")

    # Test health endpoint
    import requests
    try:
        response = requests.get(f'http://{public_ip}:8000/health', timeout=10)
        if response.status_code == 200:
            print("✓ Paid API Service is healthy")
            print(f"  Response: {response.json()}")
        else:
            print(f"✗ Health check failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"✗ Could not connect to service: {e}")
        return False

    return True


def main():
    """Main deployment flow."""
    print("=" * 60)
    print("Deploying Paid API Service to EC2")
    print("=" * 60)

    # Check required environment variables
    required_vars = ['DASHSCOPE_API_KEY', 'ARK_API_KEY']
    missing = [v for v in required_vars if not os.getenv(v)]
    if missing:
        print(f"✗ Error: Missing required environment variables: {', '.join(missing)}")
        print("\nPlease set:")
        print("  export DASHSCOPE_API_KEY=your_key")
        print("  export ARK_API_KEY=your_key")
        sys.exit(1)

    try:
        # Step 1: Launch instance
        instance_id, public_ip = launch_instance()

        # Step 2: Wait for SSH
        if not wait_for_ssh(public_ip):
            print("✗ Deployment failed: SSH not available")
            sys.exit(1)

        # Give user data script time to complete
        print("Waiting for initialization to complete...")
        time.sleep(60)

        # Step 3: Upload code
        upload_code(public_ip)

        # Step 4: Setup services
        if not setup_services(public_ip):
            print("✗ Deployment failed: Service setup error")
            sys.exit(1)

        # Step 5: Verify services
        time.sleep(10)
        verify_services(public_ip)

        # Success!
        print("\n" + "=" * 60)
        print("✓ Deployment successful!")
        print("=" * 60)
        print(f"\nInstance ID: {instance_id}")
        print(f"Public IP: {public_ip}")
        print(f"\nPaid API Service: http://{public_ip}:8000")
        print(f"Health Check: http://{public_ip}:8000/health")
        print(f"\nSSH: ssh -i ~/.ssh/zzjw.pem ubuntu@{public_ip}")
        print(f"\nView logs:")
        print(f"  sudo journalctl -u paid-api -f")
        print(f"  sudo journalctl -u sqs-adapter -f")
        print("\n" + "=" * 60)

        # Update Orchestrator configuration
        print("\n⚠️  IMPORTANT: Update orchestrator to use this instance")
        print(f"Update PAID_API_URL in orchestrator environment:")
        print(f"  export PAID_API_URL=http://{public_ip}:8000")

    except KeyboardInterrupt:
        print("\n\nDeployment cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Deployment failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
