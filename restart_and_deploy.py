#!/usr/bin/env python3
"""
Restart EC2 instance and deploy fast-loading version of the app.
"""

import boto3
import time
import sys
import subprocess

INSTANCE_ID = "i-0187a63e9a0755c60"
REGION = "us-east-1"
SSH_KEY = "/Users/jingweizhang/.ssh/zzjw.pem"

def reboot_instance():
    """Reboot the EC2 instance."""
    print(f"Rebooting instance {INSTANCE_ID}...")
    ec2_client = boto3.client('ec2', region_name=REGION)

    try:
        ec2_client.reboot_instances(InstanceIds=[INSTANCE_ID])
        print("✓ Reboot initiated")
        return True
    except Exception as e:
        print(f"✗ Failed to reboot: {e}")
        return False

def wait_for_instance():
    """Wait for instance to be running and SSH accessible."""
    print(f"Waiting for instance to be accessible...")
    ec2_client = boto3.client('ec2', region_name=REGION)

    # Wait for instance to be running
    waiter = ec2_client.get_waiter('instance_running')
    try:
        waiter.wait(InstanceIds=[INSTANCE_ID])
        print("✓ Instance is running")
    except Exception as e:
        print(f"✗ Failed to wait for instance: {e}")
        return None

    # Get instance IP
    response = ec2_client.describe_instances(InstanceIds=[INSTANCE_ID])
    instance = response['Reservations'][0]['Instances'][0]
    ip_address = instance.get('PublicIpAddress')

    if not ip_address:
        print("✗ No public IP address found")
        return None

    print(f"✓ Instance IP: {ip_address}")

    # Wait for SSH to be available
    print("Waiting for SSH to be available (up to 60 seconds)...")
    for i in range(12):  # 12 attempts, 5 seconds each = 60 seconds
        try:
            result = subprocess.run(
                ["ssh", "-i", SSH_KEY, "-o", "StrictHostKeyChecking=no",
                 "-o", "ConnectTimeout=5", f"ubuntu@{ip_address}", "echo 'SSH ready'"],
                capture_output=True,
                timeout=10
            )
            if result.returncode == 0:
                print("✓ SSH is accessible")
                return ip_address
        except:
            pass

        print(f"  Attempt {i+1}/12...")
        time.sleep(5)

    print("✗ SSH not accessible after 60 seconds")
    return None

def deploy_fast_version(ip_address):
    """Deploy the fast-loading version."""
    print("\nDeploying fast-loading version...")

    # Transfer the file
    print("1. Transferring app_fast_load.py...")
    result = subprocess.run([
        "rsync", "-avz", "-e", f"ssh -i {SSH_KEY} -o StrictHostKeyChecking=no",
        "/Users/jingweizhang/Workspace/short-drama/playground/Qwen-Image-Edit-Angles/app_fast_load.py",
        f"ubuntu@{ip_address}:~/Qwen-Image-Edit-Angles/"
    ], capture_output=True)

    if result.returncode != 0:
        print(f"✗ Failed to transfer file: {result.stderr.decode()}")
        return False
    print("✓ File transferred")

    # Start the application
    print("2. Starting application...")
    result = subprocess.run([
        "ssh", "-i", SSH_KEY, "-o", "StrictHostKeyChecking=no",
        f"ubuntu@{ip_address}",
        "cd ~/Qwen-Image-Edit-Angles && nohup python3 app_fast_load.py > app_fast_load.log 2>&1 & echo $!"
    ], capture_output=True, timeout=30)

    if result.returncode != 0:
        print(f"✗ Failed to start application: {result.stderr.decode()}")
        return False

    pid = result.stdout.decode().strip()
    print(f"✓ Application started with PID: {pid}")

    # Wait a bit and check logs
    print("\n3. Checking initial logs (waiting 30 seconds)...")
    time.sleep(30)

    result = subprocess.run([
        "ssh", "-i", SSH_KEY, "-o", "StrictHostKeyChecking=no",
        f"ubuntu@{ip_address}",
        "tail -100 ~/Qwen-Image-Edit-Angles/app_fast_load.log"
    ], capture_output=True, timeout=30)

    if result.returncode == 0:
        print("\n--- Application Logs ---")
        print(result.stdout.decode())
        print("--- End Logs ---\n")

    print(f"\n✓ Deployment complete!")
    print(f"\nAccess the application at: http://{ip_address}:7860")
    print(f"Monitor logs: ssh -i {SSH_KEY} ubuntu@{ip_address} 'tail -f ~/Qwen-Image-Edit-Angles/app_fast_load.log'")

    return True

def main():
    print("=" * 80)
    print("EC2 Instance Restart and Fast Deploy")
    print("=" * 80)
    print()

    # Step 1: Reboot
    if not reboot_instance():
        sys.exit(1)

    # Step 2: Wait for instance
    ip_address = wait_for_instance()
    if not ip_address:
        sys.exit(1)

    # Step 3: Deploy
    if not deploy_fast_version(ip_address):
        sys.exit(1)

    print("\n" + "=" * 80)
    print("SUCCESS!")
    print("=" * 80)

if __name__ == "__main__":
    main()
