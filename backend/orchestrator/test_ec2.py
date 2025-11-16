"""
Test script for EC2 helper functions.
"""

import os
import sys
from pathlib import Path

# Add parent directory to path to import ec2 module
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
from aws.ec2 import list_ec2_instances

# Load environment variables from backend/.env
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path)

# Set AWS credentials from environment
os.environ['AWS_ACCESS_KEY_ID'] = os.getenv('AWS_ACCESS_KEY')
os.environ['AWS_SECRET_ACCESS_KEY'] = os.getenv('AWS_ACCESS_SECRET')

def main():
    region = os.getenv('AWS_DEFAULT_REGION', 'us-east-1')

    print(f"Listing EC2 instances in region: {region}")
    print("-" * 80)

    try:
        instances = list_ec2_instances(region)

        if not instances:
            print("No EC2 instances found in this region.")
        else:
            print(f"Found {len(instances)} instance(s):\n")

            for idx, instance in enumerate(instances, 1):
                print(f"Instance {idx}:")
                print(f"  Instance ID: {instance['InstanceId']}")
                print(f"  Instance Type: {instance['InstanceType']}")
                print(f"  State: {instance['State']}")
                print(f"  Availability Zone: {instance['AvailabilityZone']}")
                print(f"  Private IP: {instance.get('PrivateIpAddress', 'N/A')}")
                print(f"  Public IP: {instance.get('PublicIpAddress', 'N/A')}")

                if instance.get('SpotInstanceRequestId'):
                    print(f"  Spot Instance Request ID: {instance['SpotInstanceRequestId']}")

                if instance.get('Tags'):
                    print("  Tags:")
                    for tag in instance['Tags']:
                        print(f"    {tag['Key']}: {tag['Value']}")

                print(f"  Launch Time: {instance['LaunchTime']}")
                print()

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
