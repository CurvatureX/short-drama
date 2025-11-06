# AWS IAM Configuration for EC2

This document explains how AWS credentials are handled for S3 access.

## 🔐 IAM Role-Based Authentication (Recommended)

When running on **AWS EC2**, the application automatically uses IAM role credentials. **No hardcoded credentials needed!**

### How It Works

```
┌─────────────────────────────────────────────────┐
│           EC2 Instance                           │
│                                                   │
│  ┌───────────────────────────────────────┐      │
│  │  Application (server.py)              │      │
│  │                                        │      │
│  │  boto3.client("s3")                   │      │
│  │     ↓                                  │      │
│  │  No credentials in .env?               │      │
│  │     ↓                                  │      │
│  │  Use EC2 Instance Metadata Service    │      │
│  │     ↓                                  │      │
│  │  Get IAM Role Credentials             │      │
│  └────────────┬──────────────────────────┘      │
│               │                                   │
└───────────────┼───────────────────────────────────┘
                │
                ▼
        ┌──────────────┐
        │   AWS IAM    │
        │              │
        │  EC2 Role    │
        │  with S3     │
        │  Permissions │
        └──────┬───────┘
               │
               ▼
        ┌──────────────┐
        │   S3 Bucket  │
        │ short-drama- │
        │   assets     │
        └──────────────┘
```

## ✅ Required IAM Permissions

The EC2 instance needs an IAM role with these S3 permissions:

### IAM Policy for S3 Access

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:DeleteObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::short-drama-assets",
        "arn:aws:s3:::short-drama-assets/*"
      ]
    }
  ]
}
```

## 🚀 Setup Steps

### 1. Create IAM Role

```bash
# Via AWS CLI
aws iam create-role \
  --role-name ImageGeneratorEC2Role \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Principal": {"Service": "ec2.amazonaws.com"},
      "Action": "sts:AssumeRole"
    }]
  }'
```

### 2. Create and Attach Policy

```bash
# Create policy
aws iam create-policy \
  --policy-name ImageGeneratorS3Access \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:DeleteObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::short-drama-assets",
        "arn:aws:s3:::short-drama-assets/*"
      ]
    }]
  }'

# Attach policy to role
aws iam attach-role-policy \
  --role-name ImageGeneratorEC2Role \
  --policy-arn arn:aws:iam::YOUR_ACCOUNT_ID:policy/ImageGeneratorS3Access
```

### 3. Create Instance Profile

```bash
# Create instance profile
aws iam create-instance-profile \
  --instance-profile-name ImageGeneratorProfile

# Add role to profile
aws iam add-role-to-instance-profile \
  --instance-profile-name ImageGeneratorProfile \
  --role-name ImageGeneratorEC2Role
```

### 4. Attach to EC2 Instance

```bash
# Attach instance profile to EC2
aws ec2 associate-iam-instance-profile \
  --instance-id i-1234567890abcdef0 \
  --iam-instance-profile Name=ImageGeneratorProfile
```

Or via **AWS Console**:
1. Go to EC2 → Instances
2. Select your instance
3. Actions → Security → Modify IAM role
4. Select `ImageGeneratorEC2Role`
5. Save

## 📝 Configuration Files

### .env File (No AWS Credentials Needed)

```bash
# Redis Configuration
REDIS_HOST=short-drama-redis-mqc7z9.serverless.use1.cache.amazonaws.com
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=

# AWS S3 Configuration
# Note: Credentials automatically obtained from IAM role on EC2
AWS_REGION=us-east-1
S3_BUCKET_NAME=short-drama-assets

# Hugging Face Configuration
HF_TOKEN=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

# Local Model Paths
COMFYUI_MODELS_BASE=/home/ubuntu/ComfyUI/models
```

### How boto3 Handles Credentials

The S3 service initializes boto3 like this:

```python
self.s3_client = boto3.client(
    "s3",
    aws_access_key_id=settings.aws_access_key_id,      # None on EC2
    aws_secret_access_key=settings.aws_secret_access_key,  # None on EC2
    region_name=settings.aws_region,                    # us-east-1
)
```

When `aws_access_key_id` and `aws_secret_access_key` are `None`, boto3 automatically:
1. Checks EC2 instance metadata service
2. Retrieves temporary credentials from the IAM role
3. Rotates credentials automatically

## 🔍 Verify IAM Role

### Check Instance Has Role

```bash
# On the EC2 instance
curl http://169.254.169.254/latest/meta-data/iam/security-credentials/

# Should output: ImageGeneratorEC2Role
```

### Check Role Credentials

```bash
# Get temporary credentials (refreshed automatically)
curl http://169.254.169.254/latest/meta-data/iam/security-credentials/ImageGeneratorEC2Role

# Output shows temporary credentials:
{
  "AccessKeyId": "ASIA...",
  "SecretAccessKey": "...",
  "Token": "...",
  "Expiration": "2025-01-07T12:34:56Z"
}
```

### Test S3 Access

```bash
# Test from EC2 instance
aws s3 ls s3://short-drama-assets/

# Should list bucket contents
```

## 🐛 Troubleshooting

### Issue: S3 upload fails with "Access Denied"

**Cause**: IAM role not attached or missing permissions

**Solution**:
```bash
# Check if instance has IAM role
aws ec2 describe-instances \
  --instance-ids i-YOUR_INSTANCE_ID \
  --query 'Reservations[0].Instances[0].IamInstanceProfile'

# If no role, attach one
aws ec2 associate-iam-instance-profile \
  --instance-id i-YOUR_INSTANCE_ID \
  --iam-instance-profile Name=ImageGeneratorProfile
```

### Issue: "No credentials found"

**Cause**: boto3 can't find credentials

**Check**:
```bash
# On EC2 instance
curl http://169.254.169.254/latest/meta-data/iam/security-credentials/

# Should return role name, not 404
```

### Issue: Credentials work in AWS CLI but not in app

**Cause**: App might be using old environment variables

**Solution**:
```bash
# Unset any AWS credential environment variables
unset AWS_ACCESS_KEY_ID
unset AWS_SECRET_ACCESS_KEY

# Restart service
sudo systemctl restart image-generator
```

## 💡 Best Practices

1. **Never hardcode credentials** - Use IAM roles on EC2
2. **Principle of least privilege** - Only grant necessary S3 permissions
3. **Separate roles per environment** - Different roles for dev/staging/prod
4. **Monitor access** - Use CloudTrail to track S3 operations
5. **Rotate credentials regularly** - IAM role credentials rotate automatically

## 🔐 For Local Development

If running locally (not on EC2), you have options:

### Option 1: AWS CLI Credentials

```bash
# Configure AWS CLI
aws configure

# boto3 will use these credentials automatically
```

### Option 2: Environment Variables

```bash
# In .env (local only)
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
```

### Option 3: IAM User Credentials

Create an IAM user with S3 permissions and use access keys locally.

**⚠️ Warning**: Never commit credentials to git!

## 📊 Credential Resolution Order

boto3 checks for credentials in this order:

1. **Parameters passed to client** (`aws_access_key_id`, `aws_secret_access_key`)
2. **Environment variables** (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`)
3. **Shared credentials file** (`~/.aws/credentials`)
4. **Shared config file** (`~/.aws/config`)
5. **IAM role (EC2 instance metadata)** ← **We use this on EC2**

## 🔗 Related Documentation

- [AWS IAM Roles for EC2](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/iam-roles-for-amazon-ec2.html)
- [boto3 Credentials](https://boto3.amazonaws.com/v1/documentation/api/latest/guide/credentials.html)
- [Deployment Guide](AWS_DEPLOYMENT.md)

## ✅ Summary

**On AWS EC2:**
- ✅ IAM role provides automatic credentials
- ✅ No secrets in `.env` file
- ✅ Credentials rotate automatically
- ✅ More secure than hardcoded keys

**Configuration:**
- `.env` file only needs: `AWS_REGION` and `S3_BUCKET_NAME`
- No `AWS_ACCESS_KEY_ID` or `AWS_SECRET_ACCESS_KEY` needed
- Application automatically uses IAM role credentials
