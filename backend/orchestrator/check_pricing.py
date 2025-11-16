"""
Check AWS GPU instance pricing for cost comparison.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import boto3
from datetime import datetime, timedelta

# Load environment variables
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path)

os.environ['AWS_ACCESS_KEY_ID'] = os.getenv('AWS_ACCESS_KEY')
os.environ['AWS_SECRET_ACCESS_KEY'] = os.getenv('AWS_ACCESS_SECRET')

region = 'us-east-1'
ec2_client = boto3.client('ec2', region_name=region)

# Instance types to compare with their VRAM
instances = [
    ('g4dn.xlarge', '16GB T4'),
    ('g4dn.2xlarge', '16GB T4'),
    ('g5.xlarge', '24GB A10G'),
    ('g5.2xlarge', '24GB A10G'),
    ('g6.xlarge', '24GB L4'),
    ('g6.2xlarge', '24GB L4'),
]

print('AWS GPU Instance Pricing Comparison (us-east-1)')
print('=' * 90)
print(f'{"Instance Type":<20} {"GPU":<15} {"Spot Price":<15} {"Availability Zone":<20}')
print('-' * 90)

for instance_type, gpu_info in instances:
    try:
        response = ec2_client.describe_spot_price_history(
            InstanceTypes=[instance_type],
            ProductDescriptions=['Linux/UNIX'],
            MaxResults=1,
            StartTime=datetime.now() - timedelta(hours=1)
        )

        if response['SpotPriceHistory']:
            spot_price = float(response['SpotPriceHistory'][0]['SpotPrice'])
            az = response['SpotPriceHistory'][0]['AvailabilityZone']
            print(f'{instance_type:<20} {gpu_info:<15} ${spot_price:<14.4f} {az:<20}')
        else:
            print(f'{instance_type:<20} {gpu_info:<15} {"Not available":<15}')
    except Exception as e:
        print(f'{instance_type:<20} {gpu_info:<15} Error: {str(e)[:30]}')

print()
print('Recommendation for Qwen-Image-Edit-Angles:')
print('- Minimum VRAM needed: 16-24GB')
print('- Best value: g5.xlarge (24GB A10G) or g6.xlarge (24GB L4) spot instances')
print('- Budget option: g4dn.xlarge (16GB T4) - may work but tighter on memory')
