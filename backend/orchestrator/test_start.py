"""
Test script for starting an EC2 instance.
"""

import os
import sys
from pathlib import Path

# Add parent directory to path to import ec2 module
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
from aws.ec2 import start_instance

# Load environment variables from backend/.env
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path)

# Set AWS credentials from environment
os.environ['AWS_ACCESS_KEY_ID'] = os.getenv('AWS_ACCESS_KEY')
os.environ['AWS_SECRET_ACCESS_KEY'] = os.getenv('AWS_ACCESS_SECRET')

def main():
    region = os.getenv('AWS_DEFAULT_REGION', 'us-east-1')
    instance_id = 'i-09253df615c2c2f37'  # WireGuard-VPN-Server

    print(f"Starting instance {instance_id} in region {region}...")
    print("-" * 80)

    try:
        result = start_instance(instance_id, region)

        print("\nResult:")
        print(f"  Instance ID: {result['InstanceId']}")
        print(f"  Previous State: {result['PreviousState']}")
        print(f"  Current State: {result['CurrentState']}")
        print("\nInstance is starting successfully!")

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
