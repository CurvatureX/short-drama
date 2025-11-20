# CDK Infrastructure Architecture

**Version**: 1.0.0
**Last Updated**: 2025-11-18

This document provides a detailed view of the CDK infrastructure architecture.

---

## Stack Dependency Graph

```
┌─────────────────┐     ┌─────────────────┐
│   SqsStack      │     │ DynamoDbStack   │
│                 │     │                 │
│ • Queue         │     │ • Table         │
│ • DLQ           │     │ • GSI           │
└────────┬────────┘     └────────┬────────┘
         │                       │
         └───────┬───────────────┘
                 │
                 ▼
         ┌─────────────────┐
         │   IamStack      │
         │                 │
         │ • Orchestrator  │
         │ • GPU Instance  │
         │ • Lambda Role   │
         └────────┬────────┘
                  │
                  ▼
         ┌─────────────────┐
         │  LambdaStack    │
         │                 │
         │ • Function      │
         │ • Permission    │
         └────────┬────────┘
                  │
         ┌────────┴────────┐
         │                 │
         ▼                 │
┌─────────────────┐        │
│  AlarmStack     │        │
│                 │        │
│ • Alarm         │◄───────┘
│ • Action        │
└─────────────────┘
```

---

## Resource Breakdown by Stack

### 1. SqsStack (`gpu-orchestrator-sqs`)

**Resources Created:**
```
AWS::SQS::Queue × 2
├── gpu_tasks_queue (Main Queue)
│   ├── VisibilityTimeout: 300 seconds
│   ├── ReceiveMessageWaitTime: 20 seconds
│   ├── MessageRetentionPeriod: 86400 seconds (1 day)
│   └── RedrivePolicy → gpu_tasks_queue_dlq (max 3 retries)
└── gpu_tasks_queue_dlq (Dead Letter Queue)
    ├── MessageRetentionPeriod: 1209600 seconds (14 days)
    └── RemovalPolicy: RETAIN
```

**Outputs:**
- `QueueUrl`: Main queue URL
- `QueueArn`: Main queue ARN
- `DLQUrl`: DLQ URL

**Cost:** Free tier (< 1M requests/month)

---

### 2. DynamoDbStack (`gpu-orchestrator-dynamodb`)

**Resources Created:**
```
AWS::DynamoDB::Table
└── task_store
    ├── Primary Key
    │   └── task_id (String, HASH)
    ├── Global Secondary Index
    │   └── status-created_at-index
    │       ├── status (String, HASH)
    │       └── created_at (Number, RANGE)
    ├── BillingMode: PAY_PER_REQUEST
    ├── PointInTimeRecovery: Enabled
    ├── TimeToLive: ttl attribute
    └── RemovalPolicy: RETAIN
```

**Schema:**
```json
{
  "task_id": "uuid-string",           // Primary key
  "status": "pending|processing|completed|failed",
  "job_type": "/api/v1/.../jobs",
  "created_at": 1234567890,           // Unix timestamp
  "updated_at": 1234567890,
  "result_s3_uri": "s3://...",        // Optional
  "error_message": "...",             // Optional
  "comfy_job_id": "uuid-string",      // Optional
  "ttl": 1234567890                   // Optional (30 days after created_at)
}
```

**Outputs:**
- `TableName`: task_store
- `TableArn`: Table ARN

**Cost:** ~$5/month (on-demand pricing)

---

### 3. IamStack (`gpu-orchestrator-iam`)

**Resources Created:**
```
AWS::IAM::Role × 3
├── orchestrator-task-role
│   ├── Principal: ecs-tasks.amazonaws.com
│   └── Policies:
│       ├── sqs:SendMessage, GetQueueAttributes (gpu_tasks_queue)
│       ├── dynamodb:PutItem, GetItem, UpdateItem, Query (task_store)
│       └── ec2:DescribeInstances, StartInstances (GPU instance)
│
├── gpu-instance-role
│   ├── Principal: ec2.amazonaws.com
│   └── Policies:
│       ├── sqs:ReceiveMessage, DeleteMessage, ChangeMessageVisibility (gpu_tasks_queue)
│       ├── dynamodb:GetItem, UpdateItem, PutItem (task_store)
│       └── s3:GetObject, PutObject (all buckets - TODO: restrict)
│
└── lambda-gpu-shutdown-role
    ├── Principal: lambda.amazonaws.com
    ├── ManagedPolicy: AWSLambdaBasicExecutionRole
    └── Policies:
        ├── ec2:DescribeInstances (all instances)
        └── ec2:StopInstances (GPU instance with tag Purpose=GPU-ComfyUI)

AWS::IAM::InstanceProfile
└── gpu-instance-profile
    └── Roles: [gpu-instance-role]
```

**Security Features:**
- ✅ Tag-based resource restrictions (EC2 operations)
- ✅ Least privilege principle
- ✅ Resource-specific ARNs where possible
- ✅ Separate roles for each component

**Outputs:**
- `OrchestratorRoleArn`
- `GpuInstanceRoleArn`
- `GpuInstanceProfileArn`
- `LambdaRoleArn`

**Cost:** Free

---

### 4. LambdaStack (`gpu-orchestrator-lambda`)

**Resources Created:**
```
AWS::Lambda::Function
└── shutdown-gpu-lambda
    ├── Runtime: python3.11
    ├── Handler: lambda_shutdown.lambda_handler
    ├── Code: ../orchestrator/lambda_shutdown.py
    ├── Memory: 128 MB
    ├── Timeout: 60 seconds
    ├── ReservedConcurrentExecutions: 1
    ├── Role: lambda-gpu-shutdown-role
    └── Environment:
        ├── GPU_INSTANCE_ID: i-0f0f6fd680921de5f
        └── AWS_REGION: us-east-1

AWS::Lambda::Permission
└── AllowCloudWatchInvoke
    ├── Principal: lambda.alarms.cloudwatch.amazonaws.com
    └── Action: lambda:InvokeFunction
```

**Function Logic:**
1. Receive CloudWatch Alarm event
2. Check if alarm is in ALARM state
3. Describe GPU instance state
4. If running → Stop instance
5. Return status

**Outputs:**
- `FunctionArn`
- `FunctionName`

**Cost:** Free tier (< 1M invocations/month)

---

### 5. AlarmStack (`gpu-orchestrator-alarm`)

**Resources Created:**
```
AWS::CloudWatch::Alarm
└── QueueEmptyFor30Min
    ├── MetricName: ApproximateNumberOfMessagesVisible
    ├── Namespace: AWS/SQS
    ├── Dimensions: QueueName=gpu_tasks_queue
    ├── Statistic: Average
    ├── Period: 300 seconds (5 minutes)
    ├── EvaluationPeriods: 6
    ├── DatapointsToAlarm: 6
    ├── Threshold: 0
    ├── ComparisonOperator: LessThanOrEqualToThreshold
    ├── TreatMissingData: notBreaching
    └── AlarmActions:
        └── Lambda: shutdown-gpu-lambda
```

**Trigger Logic:**
- Monitors queue every 5 minutes
- If all 6 consecutive periods (30 min) have 0 messages
- Enters ALARM state
- Invokes Lambda to shutdown GPU

**Outputs:**
- `AlarmName`
- `AlarmArn`

**Cost:** Free (first 10 alarms are free)

---

## Complete Resource List

| Resource Type | Count | Name/Pattern |
|---------------|-------|--------------|
| SQS Queue | 2 | gpu_tasks_queue, gpu_tasks_queue_dlq |
| DynamoDB Table | 1 | task_store |
| DynamoDB GSI | 1 | status-created_at-index |
| IAM Role | 3 | orchestrator-task-role, gpu-instance-role, lambda-gpu-shutdown-role |
| IAM Instance Profile | 1 | gpu-instance-profile |
| Lambda Function | 1 | shutdown-gpu-lambda |
| Lambda Permission | 1 | AllowCloudWatchInvoke |
| CloudWatch Alarm | 1 | QueueEmptyFor30Min |
| **Total** | **11** | |

---

## CloudFormation Templates

After `cdk synth`, templates are in `cdk.out/`:

```
cdk.out/
├── gpu-orchestrator-sqs.template.json       (~150 lines)
├── gpu-orchestrator-dynamodb.template.json  (~80 lines)
├── gpu-orchestrator-iam.template.json       (~300 lines)
├── gpu-orchestrator-lambda.template.json    (~120 lines)
├── gpu-orchestrator-alarm.template.json     (~60 lines)
└── manifest.json
```

---

## Deployment Order

CDK automatically handles dependencies, but the logical order is:

```
1. SqsStack        (no dependencies)
2. DynamoDbStack   (no dependencies)
   ↓
3. IamStack        (depends on: SqsStack, DynamoDbStack)
   ↓
4. LambdaStack     (depends on: IamStack)
   ↓
5. AlarmStack      (depends on: LambdaStack, SqsStack)
```

**Total deployment time:** 3-5 minutes

---

## Infrastructure as Code Benefits

### Why CDK over CloudFormation?

✅ **Type Safety**: Python typing catches errors at compile time
✅ **Reusability**: Import stacks as modules
✅ **Abstraction**: High-level constructs (Queue, Table)
✅ **Version Control**: Track infrastructure changes in git
✅ **Testing**: Unit test infrastructure code
✅ **Modularity**: Separate stacks for independent deployment

### Why CDK over Terraform?

✅ **AWS Native**: First-class support for new AWS features
✅ **CloudFormation**: Uses proven CloudFormation engine
✅ **Python**: Same language as Lambda and orchestrator
✅ **No State Files**: CloudFormation manages state
✅ **Rollback**: Automatic rollback on failure

---

## Customization Points

### Change GPU Instance ID

```python
# In app.py
gpu_instance_id = 'i-YOUR-INSTANCE-ID'
```

Or via context:
```bash
cdk deploy -c gpu_instance_id=i-YOUR-INSTANCE-ID
```

### Change Queue Timeout

```python
# In stacks/sqs_stack.py
visibility_timeout=Duration.seconds(600)  # Change from 300
```

### Change Alarm Period

```python
# In stacks/alarm_stack.py
evaluation_periods=12  # Change from 6 (60 min instead of 30)
```

### Add S3 Bucket Restriction

```python
# In stacks/iam_stack.py
resources=["arn:aws:s3:::your-bucket-name/*"]  # Instead of */*
```

### Enable DynamoDB Streams

```python
# In stacks/dynamodb_stack.py
stream=dynamodb.StreamViewType.NEW_AND_OLD_IMAGES
```

---

## Monitoring & Observability

### CloudWatch Dashboards (To Add)

Create a dashboard showing:
- SQS queue depth over time
- DynamoDB read/write capacity
- Lambda invocation count
- Alarm state history

```python
# Add to new stack: monitoring_stack.py
import aws_cdk.aws_cloudwatch as cloudwatch

dashboard = cloudwatch.Dashboard(
    self, "GpuOrchDashboard",
    dashboard_name="GPU-Orchestrator-Metrics"
)
```

### Custom Metrics (To Add)

Emit custom metrics from orchestrator:
- Task submission rate
- Task completion time
- GPU instance uptime

---

## Security Considerations

### Current Security Posture

✅ **Encryption at Rest**
- DynamoDB: Encrypted by default (AWS managed keys)
- SQS: Not encrypted (add KMS encryption)

✅ **Encryption in Transit**
- All AWS API calls use TLS

✅ **IAM Least Privilege**
- Tag-based conditions on EC2 operations
- Resource-specific permissions

### Recommended Improvements

1. **Add KMS Encryption to SQS**
```python
encryption=sqs.QueueEncryption.KMS
```

2. **Enable VPC for Lambda**
```python
vpc=ec2.Vpc.from_lookup(...)
```

3. **Add Secrets Manager for Credentials**
```python
from aws_cdk import aws_secretsmanager as secrets
```

4. **Restrict S3 to Specific Bucket**
```python
resources=["arn:aws:s3:::comfyui-results/*"]
```

---

## Disaster Recovery

### Backup Strategy

**DynamoDB:**
- Point-in-time recovery enabled ✅
- Retention: 35 days
- Recovery time: Minutes

**SQS:**
- DLQ retention: 14 days ✅
- No backup needed (transient data)

**Lambda:**
- Code in git ✅
- Redeploy from CDK

### Recovery Procedures

**Lost DynamoDB Table:**
```bash
# Restore from point-in-time
aws dynamodb restore-table-to-point-in-time \
  --source-table-name task_store \
  --target-table-name task_store-restored \
  --restore-date-time 2025-11-17T10:00:00Z
```

**Lost Stack:**
```bash
# Redeploy from CDK
cdk deploy gpu-orchestrator-dynamodb
```

---

## Cost Optimization

### Current Design

✅ **On-Demand Pricing**: DynamoDB (no over-provisioning)
✅ **Long Polling**: SQS (reduce API calls)
✅ **Reserved Concurrency**: Lambda (prevent runaway costs)
✅ **Free Tier**: SQS, Lambda, CloudWatch

### Further Optimizations

1. **DynamoDB Provisioned Capacity** (if predictable load)
2. **S3 Lifecycle Policies** (delete old results)
3. **CloudWatch Log Retention** (30 days instead of forever)

---

## Testing Strategy

### Unit Tests (To Add)

```python
# tests/test_stacks.py
import aws_cdk as cdk
from stacks.sqs_stack import SqsStack

def test_sqs_queue_created():
    app = cdk.App()
    stack = SqsStack(app, "TestStack", queue_name="test")
    template = app.synth().get_stack_by_name("TestStack").template

    assert "AWS::SQS::Queue" in template["Resources"]
```

### Integration Tests

```bash
# Deploy to test account
cdk deploy --all -c environment=test

# Run tests
pytest tests/integration/
```

---

## Migration & Updates

### Updating Existing Resources

CDK uses CloudFormation change sets:
1. Modify stack code
2. Run `cdk diff` to preview changes
3. Deploy with `cdk deploy`

### Breaking Changes

Some changes require replacement:
- Queue URL changes → Replace
- Table schema changes → Replace
- Lambda runtime changes → Update

CDK will warn you about replacements.

---

## Related Documentation

- **CDK API Reference**: https://docs.aws.amazon.com/cdk/api/v2/python/
- **CloudFormation Docs**: https://docs.aws.amazon.com/cloudformation/
- **Main Design**: `../design.md`
- **Quick Start**: `QUICKSTART.md`

---

**Infrastructure Version**: 1.0.0
**Last Reviewed**: 2025-11-18
