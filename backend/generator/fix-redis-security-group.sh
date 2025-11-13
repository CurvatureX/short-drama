#!/bin/bash

# Script to fix Redis security group to allow EC2 connection
# Run this on your local machine with AWS CLI configured

set -e

echo "🔍 Checking Redis and EC2 Security Groups..."

# Get EC2 instance security group
EC2_INSTANCE_ID="i-YOUR_INSTANCE_ID"  # Replace with your instance ID
EC2_SG=$(aws ec2 describe-instances \
    --instance-ids $EC2_INSTANCE_ID \
    --query 'Reservations[0].Instances[0].SecurityGroups[0].GroupId' \
    --output text)

echo "✓ EC2 Security Group: $EC2_SG"

# Get Redis cluster security group
REDIS_CLUSTER="short-drama-redis-mqc7z9"
REDIS_SG=$(aws elasticache describe-cache-clusters \
    --cache-cluster-id $REDIS_CLUSTER \
    --query 'CacheClusters[0].SecurityGroups[0].SecurityGroupId' \
    --output text 2>/dev/null || \
    aws elasticache describe-serverless-caches \
    --serverless-cache-name $REDIS_CLUSTER \
    --query 'ServerlessCaches[0].SecurityGroupIds[0]' \
    --output text)

echo "✓ Redis Security Group: $REDIS_SG"

# Add inbound rule to Redis security group
echo ""
echo "📝 Adding inbound rule to Redis security group..."

aws ec2 authorize-security-group-ingress \
    --group-id $REDIS_SG \
    --protocol tcp \
    --port 6379 \
    --source-group $EC2_SG \
    --group-owner-id $(aws sts get-caller-identity --query Account --output text) 2>&1 || echo "Rule may already exist"

echo ""
echo "✅ Done! Redis security group updated."
echo ""
echo "📋 Testing connection from EC2..."
ssh -i "/Users/jingweizhang/Downloads/zzjw.pem" ubuntu@ec2-52-72-101-72.compute-1.amazonaws.com \
    "timeout 5 redis-cli -h short-drama-redis-mqc7z9.serverless.use1.cache.amazonaws.com ping"

if [ $? -eq 0 ]; then
    echo "✅ Connection successful!"
else
    echo "❌ Connection still failing. Check:"
    echo "   1. VPC configuration"
    echo "   2. Network ACLs"
    echo "   3. Redis is in the same VPC as EC2"
fi
