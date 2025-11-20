# Complete Deployment Guide - Canvas Service + Orchestrator

This guide explains how to deploy both Canvas Service and Orchestrator to AWS ECS using AWS CDK.

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Application Load Balancer                 │
│                  (short-drama-backend-alb)                   │
│                                                               │
│  Path-based routing:                                         │
│  - /session*, /upload*, /images* → Canvas Service           │
│  - /api/v1/* → Orchestrator                                 │
└─────────────────────────────────────────────────────────────┘
                         │
         ┌───────────────┴───────────────┐
         ▼                               ▼
┌──────────────────┐           ┌──────────────────┐
│ Canvas Service   │           │  Orchestrator    │
│ (Fargate)        │◄─────────►│  (Fargate)       │
│                  │           │                  │
│ Port: 9000       │           │  Port: 8080      │
│ CPU: 0.25 vCPU   │           │  CPU: 0.5 vCPU   │
│ RAM: 512 MB      │           │  RAM: 1 GB       │
└──────────────────┘           └──────────────────┘
         │                               │
         ▼                               ▼
┌──────────────────┐           ┌──────────────────┐
│ Supabase + S3    │           │ SQS + DynamoDB   │
│ CloudFront       │           │ EC2 GPU Instance │
└──────────────────┘           └──────────────────┘
```

## 📋 Prerequisites

### Required Tools

- **AWS CLI** v2 - [Install](https://aws.amazon.com/cli/)
- **AWS CDK** v2 - `npm install -g aws-cdk`
- **Docker** - [Install](https://www.docker.com/get-started)
- **Python 3.11+** - [Install](https://www.python.org/)
- **Node.js 18+** - Required for CDK CLI

### AWS Setup

1. **Configure AWS credentials**:
   ```bash
   aws configure
   # Enter your AWS Access Key ID and Secret Access Key
   ```

2. **Bootstrap CDK** (one-time per account/region):
   ```bash
   export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
   cdk bootstrap aws://${AWS_ACCOUNT_ID}/us-east-1
   ```

## 🚀 Quick Start Deployment

### Option 1: Full Automated Deployment

```bash
cd backend/infra

# 1. Build and push Docker images to ECR
./build-and-push.sh

# 2. Deploy all infrastructure (or use interactive deploy.sh)
cdk deploy --all --require-approval never
```

### Option 2: Step-by-Step Deployment

#### Step 1: Setup Python Environment

```bash
cd backend/infra

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

#### Step 2: Build and Push Docker Images

```bash
# Build and push both services to ECR
./build-and-push.sh
```

This script:
- Creates ECR repositories if they don't exist
- Builds Docker images for both services
- Pushes images to ECR with `latest` tag

#### Step 3: Deploy Infrastructure

```bash
# Option A: Deploy all stacks at once
cdk deploy --all

# Option B: Deploy individual stacks in order
cdk deploy gpu-orchestrator-sqs
cdk deploy gpu-orchestrator-dynamodb
cdk deploy gpu-orchestrator-iam
cdk deploy gpu-orchestrator-lambda
cdk deploy gpu-orchestrator-alarm
cdk deploy gpu-orchestrator-ecs  # This deploys both services
```

#### Step 4: Get Deployment Outputs

```bash
# Get ALB DNS name
aws cloudformation describe-stacks \
  --stack-name gpu-orchestrator-ecs \
  --query 'Stacks[0].Outputs[?OutputKey==`LoadBalancerDNS`].OutputValue' \
  --output text

# Get ECR repository URIs
aws cloudformation describe-stacks \
  --stack-name gpu-orchestrator-ecs \
  --query 'Stacks[0].Outputs' \
  --output table
```

## 🔄 Updating Services

### Update Application Code

When you make changes to Canvas Service or Orchestrator:

```bash
cd backend/infra

# 1. Rebuild and push updated images
./build-and-push.sh

# 2. Force new deployment (no CDK changes needed)
aws ecs update-service \
  --cluster short-drama-backend-cluster \
  --service canvas-service \
  --force-new-deployment

aws ecs update-service \
  --cluster short-drama-backend-cluster \
  --service orchestrator-service \
  --force-new-deployment
```

### Update Infrastructure (CDK Stack)

When you modify CDK code:

```bash
# Preview changes
cdk diff

# Deploy changes
cdk deploy gpu-orchestrator-ecs
```

## 📊 Stack Details

### Created Resources

| Resource | Name | Purpose |
|----------|------|---------|
| **VPC** | BackendVPC | Network isolation with public/private subnets |
| **ALB** | short-drama-backend-alb | Load balancer with path-based routing |
| **ECS Cluster** | short-drama-backend-cluster | Container orchestration |
| **ECR Repos** | orchestrator, canvas-service | Docker image storage |
| **Fargate Services** | orchestrator-service, canvas-service | Running containers |
| **Target Groups** | 2 groups (ports 8080, 9000) | Health checks and routing |
| **Security Groups** | ALB SG, ECS SG | Network access control |
| **CloudWatch Logs** | /ecs/orchestrator, /ecs/canvas-service | Application logs |
| **Service Discovery** | backend.local namespace | Inter-service communication |

### Resource Costs (Estimated)

| Resource | Cost (Monthly) |
|----------|----------------|
| **Fargate** (Canvas: 0.25 vCPU, 512MB) | ~$10 |
| **Fargate** (Orchestrator: 0.5 vCPU, 1GB) | ~$20 |
| **ALB** | ~$20 |
| **NAT Gateway** | ~$35 |
| **Data Transfer** | Variable |
| **CloudWatch Logs** | ~$1 |
| **ECR Storage** | <$1 |
| **Total** | **~$86/month** |

*Note: Actual costs depend on usage and data transfer*

## 🔐 Environment Variables & Secrets

### Canvas Service Environment Variables

Canvas Service needs these environment variables (should be in AWS Secrets Manager for production):

- `SUPABASE_URL` - Supabase project URL
- `SUPABASE_SERVICE_ROLE_KEY` - Supabase service role key
- `S3_BUCKET` - S3 bucket name
- `AWS_DEFAULT_REGION` - AWS region
- `CLOUDFRONT_DOMAIN` - CloudFront distribution URL
- `CORS_ORIGINS` - Allowed CORS origins

### Setting Up Secrets Manager (Recommended)

```bash
# Create secrets for Canvas Service
aws secretsmanager create-secret \
  --name canvas-service/supabase-url \
  --secret-string "https://your-project.supabase.co"

aws secretsmanager create-secret \
  --name canvas-service/supabase-key \
  --secret-string "your-service-role-key"

aws secretsmanager create-secret \
  --name canvas-service/s3-bucket \
  --secret-string "your-bucket-name"
```

Then update `ecs_stack.py` to use secrets instead of environment variables.

## 🔍 Monitoring & Debugging

### View Logs

```bash
# Canvas Service logs
aws logs tail /ecs/canvas-service --follow

# Orchestrator logs
aws logs tail /ecs/orchestrator --follow

# Both services
aws logs tail /ecs/canvas-service /ecs/orchestrator --follow
```

### Check Service Health

```bash
# Get ALB DNS
ALB_DNS=$(aws cloudformation describe-stacks \
  --stack-name gpu-orchestrator-ecs \
  --query 'Stacks[0].Outputs[?OutputKey==`LoadBalancerDNS`].OutputValue' \
  --output text)

# Test Canvas Service
curl http://${ALB_DNS}/session -X POST

# Test Orchestrator
curl http://${ALB_DNS}/api/v1/health
```

### Check ECS Service Status

```bash
# List all services
aws ecs list-services --cluster short-drama-backend-cluster

# Describe Canvas Service
aws ecs describe-services \
  --cluster short-drama-backend-cluster \
  --services canvas-service

# Describe Orchestrator
aws ecs describe-services \
  --cluster short-drama-backend-cluster \
  --services orchestrator-service
```

### Common Issues

#### Service won't start - Image not found

```bash
# Check if images exist in ECR
aws ecr describe-images --repository-name orchestrator
aws ecr describe-images --repository-name canvas-service

# If missing, rebuild and push
./build-and-push.sh
```

#### Health check failing

```bash
# Check task logs
aws ecs list-tasks --cluster short-drama-backend-cluster --service canvas-service
# Copy task ARN from output
aws logs tail /ecs/canvas-service --follow

# Check if health endpoint works locally
docker run -p 9000:9000 canvas-service:latest
curl http://localhost:9000/health
```

#### Service not accessible via ALB

```bash
# Check target health
aws elbv2 describe-target-health --target-group-arn <TARGET_GROUP_ARN>

# Check security groups allow traffic
# ALB SG should allow port 80 from 0.0.0.0/0
# ECS SG should allow ports 8080, 9000 from ALB SG
```

## 📈 Scaling

### Manual Scaling

```bash
# Scale Canvas Service to 2 tasks
aws ecs update-service \
  --cluster short-drama-backend-cluster \
  --service canvas-service \
  --desired-count 2

# Scale Orchestrator to 2 tasks
aws ecs update-service \
  --cluster short-drama-backend-cluster \
  --service orchestrator-service \
  --desired-count 2
```

### Auto-Scaling (Add to CDK)

```python
# In ecs_stack.py, add after service creation:

canvas_scaling = self.canvas_service.auto_scale_task_count(
    min_capacity=1,
    max_capacity=5,
)

canvas_scaling.scale_on_cpu_utilization(
    "CpuScaling",
    target_utilization_percent=75,
    scale_in_cooldown=Duration.seconds(60),
    scale_out_cooldown=Duration.seconds(60),
)
```

## 🧹 Cleanup

### Destroy All Resources

```bash
# WARNING: This deletes everything!
cdk destroy --all

# Manually delete ECR images if needed
aws ecr batch-delete-image \
  --repository-name orchestrator \
  --image-ids imageTag=latest

aws ecr batch-delete-image \
  --repository-name canvas-service \
  --image-ids imageTag=latest
```

## 🔗 Related Documentation

- [CDK Infrastructure README](./README.md) - Full CDK documentation
- [Canvas Service README](../canvas_service/README.md) - Canvas API docs
- [Orchestrator README](../orchestrator/README.md) - Orchestrator docs
- [Docker Compose Guide](../DOCKER_COMPOSE_README.md) - Local development

## 💡 Best Practices

1. **Use Secrets Manager** for sensitive environment variables
2. **Enable auto-scaling** for production workloads
3. **Set up CloudWatch alarms** for critical metrics
4. **Use multiple availability zones** (already configured)
5. **Implement CI/CD** for automated deployments
6. **Tag images** with git commit SHA instead of just `latest`
7. **Enable CloudTrail** for audit logging
8. **Use AWS WAF** with ALB for security

## 🎯 Next Steps

1. ✅ **Deploy infrastructure** - `./build-and-push.sh && cdk deploy --all`
2. ⬜ **Configure custom domain** - Use Route53 and ACM
3. ⬜ **Set up CI/CD** - GitHub Actions or AWS CodePipeline
4. ⬜ **Add monitoring** - CloudWatch dashboards and alarms
5. ⬜ **Implement blue/green deployments** - ECS deployment controller
6. ⬜ **Add WAF rules** - Protect against common attacks

## 📞 Support

For issues:
1. Check CloudWatch logs first
2. Verify health endpoints work
3. Check security group rules
4. Review ECS task definition
5. Test locally with Docker Compose
