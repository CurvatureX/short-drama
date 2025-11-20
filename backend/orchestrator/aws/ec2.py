"""
EC2 helper functions for managing AWS instances.
"""

import boto3
from typing import List, Dict, Optional, Any
from botocore.exceptions import ClientError


def list_ec2_instances(region: str, filters: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    """
    List all EC2 instances in a given region.

    Args:
        region: AWS region name (e.g., 'us-east-1')
        filters: Optional list of filters in boto3 format
                Example: [{'Name': 'instance-state-name', 'Values': ['running']}]

    Returns:
        List of instance dictionaries containing instance information

    Raises:
        ClientError: If AWS API call fails
    """
    ec2_client = boto3.client('ec2', region_name=region)

    try:
        if filters:
            response = ec2_client.describe_instances(Filters=filters)
        else:
            response = ec2_client.describe_instances()

        instances = []
        for reservation in response['Reservations']:
            for instance in reservation['Instances']:
                instance_info = {
                    'InstanceId': instance['InstanceId'],
                    'InstanceType': instance['InstanceType'],
                    'State': instance['State']['Name'],
                    'LaunchTime': instance['LaunchTime'],
                    'PrivateIpAddress': instance.get('PrivateIpAddress'),
                    'PublicIpAddress': instance.get('PublicIpAddress'),
                    'Tags': instance.get('Tags', []),
                    'AvailabilityZone': instance['Placement']['AvailabilityZone'],
                    'SpotInstanceRequestId': instance.get('SpotInstanceRequestId')
                }
                instances.append(instance_info)

        return instances

    except ClientError as e:
        print(f"Error listing EC2 instances: {e}")
        raise


def get_instance_ip(instance_id: str, region: str) -> Optional[str]:
    """
    Get the current public IP address of an EC2 instance.

    Args:
        instance_id: The ID of the instance
        region: AWS region name

    Returns:
        Public IP address string, or None if instance doesn't have one

    Raises:
        ClientError: If AWS API call fails
    """
    ec2_client = boto3.client('ec2', region_name=region)

    try:
        response = ec2_client.describe_instances(InstanceIds=[instance_id])

        if not response['Reservations']:
            return None

        instance = response['Reservations'][0]['Instances'][0]
        return instance.get('PublicIpAddress')

    except ClientError as e:
        print(f"Error getting instance IP for {instance_id}: {e}")
        raise


def start_instance(instance_id: str, region: str) -> Dict[str, Any]:
    """
    Start a stopped EC2 instance.

    Args:
        instance_id: The ID of the instance to start
        region: AWS region name

    Returns:
        Dictionary containing the starting state change information

    Raises:
        ClientError: If AWS API call fails
    """
    ec2_client = boto3.client('ec2', region_name=region)

    try:
        response = ec2_client.start_instances(InstanceIds=[instance_id])

        state_change = response['StartingInstances'][0]
        result = {
            'InstanceId': state_change['InstanceId'],
            'PreviousState': state_change['PreviousState']['Name'],
            'CurrentState': state_change['CurrentState']['Name']
        }

        print(f"Instance {instance_id} is starting. Previous state: {result['PreviousState']}, Current state: {result['CurrentState']}")
        return result

    except ClientError as e:
        print(f"Error starting instance {instance_id}: {e}")
        raise


def stop_instance(instance_id: str, region: str, force: bool = False) -> Dict[str, Any]:
    """
    Stop a running EC2 instance.

    Args:
        instance_id: The ID of the instance to stop
        region: AWS region name
        force: If True, forces the instance to stop (equivalent to power off)

    Returns:
        Dictionary containing the stopping state change information

    Raises:
        ClientError: If AWS API call fails
    """
    ec2_client = boto3.client('ec2', region_name=region)

    try:
        response = ec2_client.stop_instances(
            InstanceIds=[instance_id],
            Force=force
        )

        state_change = response['StoppingInstances'][0]
        result = {
            'InstanceId': state_change['InstanceId'],
            'PreviousState': state_change['PreviousState']['Name'],
            'CurrentState': state_change['CurrentState']['Name']
        }

        print(f"Instance {instance_id} is stopping. Previous state: {result['PreviousState']}, Current state: {result['CurrentState']}")
        return result

    except ClientError as e:
        print(f"Error stopping instance {instance_id}: {e}")
        raise


def request_spot_instance(
    region: str,
    instance_type: str,
    ami_id: str,
    spot_price: str,
    key_name: Optional[str] = None,
    security_group_ids: Optional[List[str]] = None,
    subnet_id: Optional[str] = None,
    user_data: Optional[str] = None,
    tags: Optional[List[Dict[str, str]]] = None,
    iam_instance_profile: Optional[str] = None
) -> Dict[str, Any]:
    """
    Request a spot instance.

    Args:
        region: AWS region name
        instance_type: EC2 instance type (e.g., 't3.micro')
        ami_id: AMI ID to launch
        spot_price: Maximum price you're willing to pay per hour
        key_name: Name of the key pair for SSH access
        security_group_ids: List of security group IDs
        subnet_id: Subnet ID for VPC
        user_data: User data script to run on instance launch
        tags: List of tags to apply to the instance
        iam_instance_profile: IAM instance profile ARN or name

    Returns:
        Dictionary containing spot instance request information

    Raises:
        ClientError: If AWS API call fails
    """
    ec2_client = boto3.client('ec2', region_name=region)

    # Build launch specification
    launch_spec = {
        'ImageId': ami_id,
        'InstanceType': instance_type,
    }

    if key_name:
        launch_spec['KeyName'] = key_name

    if security_group_ids:
        launch_spec['SecurityGroupIds'] = security_group_ids

    if subnet_id:
        launch_spec['SubnetId'] = subnet_id

    if user_data:
        launch_spec['UserData'] = user_data

    if iam_instance_profile:
        launch_spec['IamInstanceProfile'] = {
            'Arn': iam_instance_profile if iam_instance_profile.startswith('arn:') else None,
            'Name': iam_instance_profile if not iam_instance_profile.startswith('arn:') else None
        }
        # Remove None values
        launch_spec['IamInstanceProfile'] = {k: v for k, v in launch_spec['IamInstanceProfile'].items() if v is not None}

    try:
        response = ec2_client.request_spot_instances(
            SpotPrice=spot_price,
            InstanceCount=1,
            Type='one-time',
            LaunchSpecification=launch_spec
        )

        spot_request = response['SpotInstanceRequests'][0]
        result = {
            'SpotInstanceRequestId': spot_request['SpotInstanceRequestId'],
            'SpotPrice': spot_request['SpotPrice'],
            'State': spot_request['State'],
            'Status': spot_request['Status']['Code'],
            'InstanceType': spot_request['LaunchSpecification']['InstanceType']
        }

        print(f"Spot instance request created: {result['SpotInstanceRequestId']}")

        # Apply tags if provided
        if tags and result['SpotInstanceRequestId']:
            try:
                ec2_client.create_tags(
                    Resources=[result['SpotInstanceRequestId']],
                    Tags=tags
                )
                print(f"Tags applied to spot request {result['SpotInstanceRequestId']}")
            except ClientError as tag_error:
                print(f"Warning: Could not apply tags: {tag_error}")

        return result

    except ClientError as e:
        print(f"Error requesting spot instance: {e}")
        raise


def launch_on_demand_instance(
    region: str,
    instance_type: str,
    ami_id: str,
    key_name: Optional[str] = None,
    security_group_ids: Optional[List[str]] = None,
    subnet_id: Optional[str] = None,
    user_data: Optional[str] = None,
    tags: Optional[List[Dict[str, str]]] = None,
    iam_instance_profile: Optional[str] = None,
    min_count: int = 1,
    max_count: int = 1
) -> Dict[str, Any]:
    """
    Launch an on-demand EC2 instance.

    Args:
        region: AWS region name
        instance_type: EC2 instance type (e.g., 't3.micro')
        ami_id: AMI ID to launch
        key_name: Name of the key pair for SSH access
        security_group_ids: List of security group IDs
        subnet_id: Subnet ID for VPC
        user_data: User data script to run on instance launch
        tags: List of tags to apply to the instance
        iam_instance_profile: IAM instance profile ARN or name
        min_count: Minimum number of instances to launch
        max_count: Maximum number of instances to launch

    Returns:
        Dictionary containing launched instance information

    Raises:
        ClientError: If AWS API call fails
    """
    ec2_client = boto3.client('ec2', region_name=region)

    # Build launch parameters
    launch_params = {
        'ImageId': ami_id,
        'InstanceType': instance_type,
        'MinCount': min_count,
        'MaxCount': max_count,
    }

    if key_name:
        launch_params['KeyName'] = key_name

    if security_group_ids:
        launch_params['SecurityGroupIds'] = security_group_ids

    if subnet_id:
        launch_params['SubnetId'] = subnet_id

    if user_data:
        launch_params['UserData'] = user_data

    if iam_instance_profile:
        launch_params['IamInstanceProfile'] = {
            'Arn': iam_instance_profile if iam_instance_profile.startswith('arn:') else None,
            'Name': iam_instance_profile if not iam_instance_profile.startswith('arn:') else None
        }
        # Remove None values
        launch_params['IamInstanceProfile'] = {k: v for k, v in launch_params['IamInstanceProfile'].items() if v is not None}

    if tags:
        launch_params['TagSpecifications'] = [
            {
                'ResourceType': 'instance',
                'Tags': tags
            }
        ]

    try:
        response = ec2_client.run_instances(**launch_params)

        instances = []
        for instance in response['Instances']:
            instance_info = {
                'InstanceId': instance['InstanceId'],
                'InstanceType': instance['InstanceType'],
                'State': instance['State']['Name'],
                'PrivateIpAddress': instance.get('PrivateIpAddress'),
                'AvailabilityZone': instance['Placement']['AvailabilityZone']
            }
            instances.append(instance_info)

        result = {
            'Instances': instances,
            'ReservationId': response['ReservationId']
        }

        print(f"Launched {len(instances)} instance(s). Instance IDs: {[i['InstanceId'] for i in instances]}")
        return result

    except ClientError as e:
        print(f"Error launching instance: {e}")
        raise
