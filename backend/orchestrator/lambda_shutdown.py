"""
AWS Lambda Function: GPU Auto-Shutdown

This Lambda function is triggered by CloudWatch Alarm when the SQS queue
has been empty for 30 minutes. It safely shuts down the GPU instance.

Trigger: CloudWatch Alarm (QueueEmptyFor30Min)
Runtime: Python 3.11
Memory: 128 MB
Timeout: 60 seconds

Required IAM Permissions:
- ec2:DescribeInstances
- ec2:StopInstances (with condition on resource tag)
- logs:CreateLogGroup
- logs:CreateLogStream
- logs:PutLogEvents
"""

import json
import os
import boto3
from datetime import datetime

# Configuration
GPU_INSTANCE_ID = os.environ.get('GPU_INSTANCE_ID', 'i-0f0f6fd680921de5f')
# AWS_REGION is automatically set by Lambda runtime
AWS_REGION = os.environ.get('AWS_REGION', os.environ.get('AWS_DEFAULT_REGION', 'us-east-1'))

# Initialize EC2 client
ec2_client = boto3.client('ec2', region_name=AWS_REGION)


def lambda_handler(event, context):
    """
    Lambda handler function.

    This function is called when CloudWatch Alarm enters ALARM state
    (i.e., SQS queue has been empty for 30 minutes).

    Args:
        event: CloudWatch Alarm event
        context: Lambda context

    Returns:
        Response dictionary with status code and body
    """
    print(f"Lambda invoked at {datetime.utcnow().isoformat()}")
    print(f"Event: {json.dumps(event)}")

    try:
        # Step 1: Check if this is an SNS event (CloudWatch Alarm via SNS)
        if 'Records' in event and len(event['Records']) > 0:
            # This is an SNS message from CloudWatch Alarm
            sns_message = event['Records'][0]['Sns']
            message_body = json.loads(sns_message['Message'])

            print(f"SNS Subject: {sns_message.get('Subject', 'N/A')}")
            print(f"Alarm Name: {message_body.get('AlarmName', 'Unknown')}")
            print(f"New State: {message_body.get('NewStateValue', 'UNKNOWN')}")

            # Only proceed if alarm is in ALARM state
            if message_body.get('NewStateValue') != 'ALARM':
                print(f"Alarm not in ALARM state, skipping shutdown")
                return {
                    'statusCode': 200,
                    'body': json.dumps({
                        'message': 'Alarm not in ALARM state',
                        'state': message_body.get('NewStateValue')
                    })
                }
        # Step 2: Fallback for direct CloudWatch Events (if used)
        elif 'source' in event and event['source'] == 'aws.cloudwatch':
            alarm_data = event.get('detail', {})
            alarm_name = alarm_data.get('alarmName', 'Unknown')
            state = alarm_data.get('state', {}).get('value', 'UNKNOWN')

            print(f"CloudWatch Alarm: {alarm_name}")
            print(f"New State: {state}")

            # Only proceed if alarm is in ALARM state
            if state != 'ALARM':
                print(f"Alarm not in ALARM state, skipping shutdown")
                return {
                    'statusCode': 200,
                    'body': json.dumps({
                        'message': 'Alarm not in ALARM state',
                        'state': state
                    })
                }

        # Step 2: Check GPU instance state
        print(f"Checking instance {GPU_INSTANCE_ID}...")
        response = ec2_client.describe_instances(
            InstanceIds=[GPU_INSTANCE_ID]
        )

        if not response['Reservations']:
            print(f"ERROR: Instance {GPU_INSTANCE_ID} not found")
            return {
                'statusCode': 404,
                'body': json.dumps({
                    'error': f'Instance {GPU_INSTANCE_ID} not found'
                })
            }

        instance = response['Reservations'][0]['Instances'][0]
        current_state = instance['State']['Name']
        instance_type = instance['InstanceType']
        launch_time = instance.get('LaunchTime')

        print(f"Instance State: {current_state}")
        print(f"Instance Type: {instance_type}")
        print(f"Launch Time: {launch_time}")

        # Step 3: Stop instance if it's running
        if current_state == 'running':
            print(f"Stopping instance {GPU_INSTANCE_ID}...")

            stop_response = ec2_client.stop_instances(
                InstanceIds=[GPU_INSTANCE_ID]
            )

            state_change = stop_response['StoppingInstances'][0]
            previous_state = state_change['PreviousState']['Name']
            new_state = state_change['CurrentState']['Name']

            print(f"✓ Stop command sent successfully")
            print(f"  Previous State: {previous_state}")
            print(f"  Current State: {new_state}")

            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'GPU instance shutdown initiated',
                    'instance_id': GPU_INSTANCE_ID,
                    'previous_state': previous_state,
                    'current_state': new_state,
                    'instance_type': instance_type,
                    'timestamp': datetime.utcnow().isoformat()
                })
            }

        elif current_state in ('stopped', 'stopping'):
            print(f"Instance already {current_state}, no action needed")
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': f'Instance already {current_state}',
                    'instance_id': GPU_INSTANCE_ID,
                    'state': current_state
                })
            }

        else:
            print(f"Instance in unexpected state: {current_state}")
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'message': f'Instance in unexpected state: {current_state}',
                    'instance_id': GPU_INSTANCE_ID,
                    'state': current_state
                })
            }

    except Exception as e:
        error_msg = str(e)
        print(f"ERROR: {error_msg}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': error_msg,
                'instance_id': GPU_INSTANCE_ID
            })
        }


# For local testing
if __name__ == "__main__":
    # Simulate CloudWatch Alarm event
    test_event = {
        'source': 'aws.cloudwatch',
        'detail': {
            'alarmName': 'QueueEmptyFor30Min',
            'state': {
                'value': 'ALARM'
            }
        }
    }

    class MockContext:
        def __init__(self):
            self.function_name = 'shutdown-gpu-lambda'
            self.memory_limit_in_mb = 128
            self.invoked_function_arn = 'arn:aws:lambda:us-east-1:123456789012:function:shutdown-gpu-lambda'
            self.aws_request_id = 'test-request-id'

    result = lambda_handler(test_event, MockContext())
    print("\nResult:")
    print(json.dumps(result, indent=2))
