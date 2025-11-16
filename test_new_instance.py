"""
Get details for new instance i-0187a63e9a0755c60
"""

import sys
sys.path.append('/Users/jingweizhang/Workspace/short-drama/backend')

from orchestrator.aws.ec2 import list_ec2_instances

# Get instance details
instance_id = "i-0187a63e9a0755c60"
region = "us-east-1"

print(f"Fetching details for instance {instance_id}...")
instances = list_ec2_instances(
    region=region,
    filters=[{'Name': 'instance-id', 'Values': [instance_id]}]
)

if instances:
    instance = instances[0]
    print("\n=== Instance Details ===")
    print(f"Instance ID: {instance['InstanceId']}")
    print(f"Instance Type: {instance['InstanceType']}")
    print(f"State: {instance['State']}")
    print(f"Public IP: {instance.get('PublicIpAddress', 'N/A')}")
    print(f"Private IP: {instance.get('PrivateIpAddress', 'N/A')}")
    print(f"Availability Zone: {instance['AvailabilityZone']}")

    tags = instance.get('Tags', [])
    if tags:
        print("\nTags:")
        for tag in tags:
            print(f"  {tag['Key']}: {tag['Value']}")
else:
    print(f"Instance {instance_id} not found in region {region}")
