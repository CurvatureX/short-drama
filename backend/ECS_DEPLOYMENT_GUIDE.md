# ECS Deployment Guide

This guide explains how to deploy the Canvas Service and Orchestrator to AWS ECS Fargate.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                         ECS Cluster                          │
│  ┌────────────────────────┐  ┌─────────────────────────┐   │
│  │   Canvas Service       │  │   Orchestrator          │   │
│  │   (Port 9000)          │  │   (Port 8080)           │   │
│  │                        │  │                         │   │
│  │ - Session Management   │  │ - GPU Task Queue        │   │
│  │ - Image Upload         │  │ - CPU Task Queue        │   │
│  │ - S3 Integration       │  │ - DynamoDB Status       │   │
│  │ - Supabase DB          │  │ - EC2 Instance Mgmt     │   │
│  └────────────────────────┘  └─────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
        ┌─────────────────────────────────────────┐
        │  External Dependencies                   │
        │  - Supabase (PostgreSQL)                │
        │  - S3 (Image Storage)                   │
        │  - CloudFront (CDN)                     │
        │  - SQS (Task Queues)                    │
        │  - DynamoDB (Task Status)               │
        │  - EC2 (GPU Instance)                   │
        └─────────────────────────────────────────┘
```

## Prerequisites

### 1. AWS Resources

Before deployment, you need:

- **AWS Account** with appropriate permissions
- **VPC** with at least 2 subnets in different availability zones
- **IAM Roles**:
  - `ecsTaskExecutionRole` - for ECS to pull images and write logs
  - `ecsTaskRole` - for tasks to access AWS services
- **AWS Secrets Manager** secrets for sensitive data (recommended)

### 2. External Services

- **Supabase** project with required tables
- **S3 bucket** for image storage
- **CloudFront** distribution (optional, for CDN)
- **SQS queues** (gpu_tasks_queue, cpu_tasks_queue)
- **DynamoDB table** (task_store)
- **EC2 GPU instance** (for GPU tasks)

### 3. Tools

- AWS CLI v2
- Docker
- jq (for JSON processing)

## Quick Start

### Step 1: Set Environment Variables

Create a `.env` file in the `backend/` directory with your configuration:

```bash
# Copy from .env.docker.example
cp .env.docker.example .env

# Edit with your values
vim .env
```

### Step 2: Configure AWS

Export necessary AWS configuration:

```bash
export AWS_REGION=us-east-1
export AWS_ACCOUNT_ID=your-account-id

# Network configuration (required for setup)
export VPC_ID=vpc-xxxxx
export SUBNET_IDS=subnet-xxxxx,subnet-yyyyy  # At least 2 subnets
export SECURITY_GROUP_ID=sg-xxxxx  # Optional, will create if not provided
```

### Step 3: Initial Setup (First Time Only)

Run the setup script to create ECS cluster and service:

```bash
chmod +x setup-ecs-service.sh
./setup-ecs-service.sh
```

This creates:
- ECS cluster
- Security group (if not provided)
- ECS service with Fargate launch type

### Step 4: Deploy

Deploy or update your application:

```bash
chmod +x deploy-to-ecs.sh
./deploy-to-ecs.sh
```

This script:
1. Creates ECR repositories (if needed)
2. Builds Docker images for both services
3. Pushes images to ECR
4. Registers updated task definition
5. Updates the ECS service (forces new deployment)

## Detailed Configuration

### IAM Roles

#### ecsTaskExecutionRole

This role allows ECS to:
- Pull images from ECR
- Write logs to CloudWatch
- Fetch secrets from Secrets Manager

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ecr:GetAuthorizationToken",
        "ecr:BatchCheckLayerAvailability",
        "ecr:GetDownloadUrlForLayer",
        "ecr:BatchGetImage",
        "logs:CreateLogStream",
        "logs:PutLogEvents",
        "secretsmanager:GetSecretValue"
      ],
      "Resource": "*"
    }
  ]
}
```

#### ecsTaskRole

This role allows tasks to:
- Access S3 buckets
- Query/update DynamoDB
- Send/receive SQS messages
- Manage EC2 instances

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:PutObjectAcl"
      ],
      "Resource": "arn:aws:s3:::your-bucket/*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:UpdateItem",
        "dynamodb:Query"
      ],
      "Resource": "arn:aws:dynamodb:us-east-1:*:table/task_store"
    },
    {
      "Effect": "Allow",
      "Action": [
        "sqs:SendMessage",
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage",
        "sqs:GetQueueAttributes"
      ],
      "Resource": [
        "arn:aws:sqs:us-east-1:*:gpu_tasks_queue",
        "arn:aws:sqs:us-east-1:*:cpu_tasks_queue"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeInstances",
        "ec2:StartInstances",
        "ec2:StopInstances",
        "ec2:DescribeInstanceStatus"
      ],
      "Resource": "*"
    }
  ]
}
```

### Using AWS Secrets Manager

Instead of environment variables, use Secrets Manager for sensitive data:

1. **Create secrets**:

```bash
aws secretsmanager create-secret \
  --name backend/supabase-url \
  --secret-string "https://your-project.supabase.co"

aws secretsmanager create-secret \
  --name backend/supabase-key \
  --secret-string "your-service-role-key"

aws secretsmanager create-secret \
  --name backend/aws-access-key \
  --secret-string "your-access-key"

aws secretsmanager create-secret \
  --name backend/aws-secret-key \
  --secret-string "your-secret-key"
```

2. **Update task definition** - the `ecs-task-definition.json` already includes secret references.

### Security Group Configuration

The security group needs these ingress rules:

| Port | Protocol | Source      | Purpose           |
|------|----------|-------------|-------------------|
| 9000 | TCP      | 0.0.0.0/0   | Canvas Service    |
| 8080 | TCP      | 0.0.0.0/0   | Orchestrator      |

For production, restrict source IPs to:
- Your ALB security group
- Your VPN/office IP ranges
- Your frontend application IP ranges

## Local Testing with Docker Compose

Before deploying to ECS, test locally:

```bash
# Load environment variables
set -a
source .env
set +a

# Start services
docker-compose up --build

# Test canvas service
curl http://localhost:9000/health

# Test orchestrator
curl http://localhost:8080/health

# Stop services
docker-compose down
```

## Monitoring and Logs

### View Logs

```bash
# Stream all logs
aws logs tail /ecs/short-drama-backend --follow

# Canvas service only
aws logs tail /ecs/short-drama-backend --follow --filter-pattern canvas-service

# Orchestrator only
aws logs tail /ecs/short-drama-backend --follow --filter-pattern orchestrator
```

### Check Service Status

```bash
aws ecs describe-services \
  --cluster short-drama-cluster \
  --services short-drama-backend \
  --query 'services[0].{Status:status,Running:runningCount,Desired:desiredCount,Pending:pendingCount}'
```

### Get Task Public IP

```bash
TASK_ARN=$(aws ecs list-tasks --cluster short-drama-cluster --service-name short-drama-backend --query 'taskArns[0]' --output text)

aws ecs describe-tasks --cluster short-drama-cluster --tasks $TASK_ARN \
  --query 'tasks[0].attachments[0].details[?name==`networkInterfaceId`].value' --output text | \
  xargs -I {} aws ec2 describe-network-interfaces --network-interface-ids {} \
  --query 'NetworkInterfaces[0].Association.PublicIp' --output text
```

## Scaling

### Manual Scaling

```bash
aws ecs update-service \
  --cluster short-drama-cluster \
  --service short-drama-backend \
  --desired-count 2
```

### Auto Scaling

Create auto-scaling configuration:

```bash
# Register scalable target
aws application-autoscaling register-scalable-target \
  --service-namespace ecs \
  --scalable-dimension ecs:service:DesiredCount \
  --resource-id service/short-drama-cluster/short-drama-backend \
  --min-capacity 1 \
  --max-capacity 10

# Create scaling policy
aws application-autoscaling put-scaling-policy \
  --service-namespace ecs \
  --scalable-dimension ecs:service:DesiredCount \
  --resource-id service/short-drama-cluster/short-drama-backend \
  --policy-name cpu-scaling-policy \
  --policy-type TargetTrackingScaling \
  --target-tracking-scaling-policy-configuration '{
    "TargetValue": 75.0,
    "PredefinedMetricSpecification": {
      "PredefinedMetricType": "ECSServiceAverageCPUUtilization"
    }
  }'
```

## Troubleshooting

### Task Fails to Start

1. **Check logs**:
   ```bash
   aws logs tail /ecs/short-drama-backend --follow
   ```

2. **Check task stopped reason**:
   ```bash
   aws ecs describe-tasks --cluster short-drama-cluster --tasks TASK_ID
   ```

3. **Common issues**:
   - Missing IAM permissions
   - Invalid secrets ARNs
   - Insufficient CPU/memory
   - Missing environment variables

### Health Check Failures

1. **Verify endpoints locally**:
   ```bash
   docker-compose up
   curl http://localhost:9000/health
   curl http://localhost:8080/health
   ```

2. **Check security group**: Ensure health check ports are accessible

3. **Increase grace period** in `ecs-task-definition.json`

### Can't Pull Docker Images

1. **Check ECR permissions**: Ensure `ecsTaskExecutionRole` has ECR permissions
2. **Verify repository exists**: `aws ecr describe-repositories`
3. **Re-login to ECR**: `aws ecr get-login-password | docker login ...`

## Cost Optimization

### Fargate Pricing

Based on vCPU and memory per hour:
- **Current config**: 1 vCPU, 2GB RAM = ~$0.04/hour = ~$30/month
- **Per service**: 0.25 vCPU, 512MB RAM = ~$7.50/month each

### Recommendations

1. **Use Fargate Spot** for non-critical workloads (70% savings)
2. **Scale down** during off-hours
3. **Use CloudWatch alarms** to stop idle tasks
4. **Enable Container Insights** only when debugging

## Next Steps

1. **Set up Application Load Balancer** for production traffic
2. **Configure HTTPS** with ACM certificates
3. **Set up CloudWatch alarms** for monitoring
4. **Enable AWS X-Ray** for distributed tracing
5. **Implement CI/CD** with GitHub Actions or AWS CodePipeline

## Support

For issues or questions:
- Check CloudWatch logs
- Review IAM permissions
- Verify security group rules
- Test locally with docker-compose first
