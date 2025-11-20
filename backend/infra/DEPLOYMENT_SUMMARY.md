# GPU Orchestration System - 部署总结

**部署时间**: 2025-11-18 12:50 - 12:57 (北京时间)
**部署状态**: ✅ 成功完成
**AWS Account**: 982081090398
**AWS Region**: us-east-1

---

## 📊 已部署的资源清单

### 1. ✅ SQS Queue Stack (`gpu-orchestrator-sqs`)

| 资源类型 | 名称 | URL/ARN |
|---------|------|---------|
| **主队列** | `gpu_tasks_queue` | `https://sqs.us-east-1.amazonaws.com/982081090398/gpu_tasks_queue` |
| **死信队列(DLQ)** | `gpu_tasks_queue_dlq` | `https://sqs.us-east-1.amazonaws.com/982081090398/gpu_tasks_queue_dlq` |

**配置参数**:
- Visibility Timeout: 300 秒 (5分钟)
- Receive Wait Time: 20 秒 (长轮询)
- Message Retention: 86400 秒 (1天)
- Max Receive Count: 3 (重试3次后进入DLQ)

---

### 2. ✅ DynamoDB Table Stack (`gpu-orchestrator-dynamodb`)

| 资源类型 | 名称 | ARN |
|---------|------|-----|
| **表** | `task_store` | `arn:aws:dynamodb:us-east-1:982081090398:table/task_store` |
| **GSI** | `status-created_at-index` | (用于按状态查询任务) |

**表结构**:
- Primary Key: `task_id` (String)
- GSI Partition Key: `status` (String)
- GSI Sort Key: `created_at` (Number)
- Billing Mode: PAY_PER_REQUEST
- Point-in-Time Recovery: ✅ Enabled
- TTL Attribute: `ttl`

---

### 3. ✅ IAM Roles Stack (`gpu-orchestrator-iam`)

| IAM Resource | 名称 | ARN |
|-------------|------|-----|
| **Orchestrator Role** | `gpu-orchestrator-task-role` | `arn:aws:iam::982081090398:role/gpu-orchestrator-task-role` |
| **GPU Instance Role** | `gpu-instance-role` | `arn:aws:iam::982081090398:role/gpu-instance-role` |
| **Lambda Role** | `lambda-gpu-shutdown-role` | `arn:aws:iam::982081090398:role/lambda-gpu-shutdown-role` |
| **Instance Profile** | `gpu-instance-profile` | `arn:aws:iam::982081090398:instance-profile/gpu-instance-profile` |

**权限分配**:

**Orchestrator Role**:
- ✅ SQS: SendMessage, GetQueueAttributes
- ✅ DynamoDB: PutItem, GetItem, UpdateItem, Query
- ✅ EC2: DescribeInstances, StartInstances (带tag条件)

**GPU Instance Role**:
- ✅ SQS: ReceiveMessage, DeleteMessage, ChangeMessageVisibility
- ✅ DynamoDB: GetItem, UpdateItem, PutItem
- ✅ S3: GetObject, PutObject

**Lambda Role**:
- ✅ EC2: DescribeInstances, StopInstances (带tag条件)
- ✅ CloudWatch Logs: CreateLogGroup, CreateLogStream, PutLogEvents

---

### 4. ✅ Lambda Function Stack (`gpu-orchestrator-lambda`)

| 属性 | 值 |
|-----|---|
| **Function Name** | `shutdown-gpu-lambda` |
| **ARN** | `arn:aws:lambda:us-east-1:982081090398:function:shutdown-gpu-lambda` |
| **Runtime** | Python 3.11 |
| **Handler** | `lambda_shutdown.lambda_handler` |
| **Memory** | 128 MB |
| **Timeout** | 60 seconds |
| **Environment** | `GPU_INSTANCE_ID=i-0f0f6fd680921de5f` |

**功能**: 当CloudWatch Alarm触发时（队列空闲30分钟），通过SNS接收通知并关闭GPU实例

---

### 5. ✅ CloudWatch Alarm Stack (`gpu-orchestrator-alarm`)

| 资源类型 | 名称 | ARN |
|---------|------|-----|
| **Alarm** | `QueueEmptyFor30Min` | `arn:aws:cloudwatch:us-east-1:982081090398:alarm:QueueEmptyFor30Min` |
| **SNS Topic** | `gpu-shutdown-alerts` | `arn:aws:sns:us-east-1:982081090398:gpu-shutdown-alerts` |

**告警配置**:
- Metric: `ApproximateNumberOfMessagesVisible`
- Namespace: `AWS/SQS`
- Threshold: 0 messages
- Evaluation Periods: 6 × 5分钟 = 30分钟
- Action: 发送SNS消息 → Lambda → 关闭GPU实例

---

## 🧪 测试结果

### ✅ 测试1: SQS消息发送
```bash
发送测试消息成功
Message ID: c51dfdc7-802b-47c3-b8c9-a7d0714f9e54
队列中消息数: 1
```

### ✅ 测试2: Lambda Function配置
```json
{
  "Name": "shutdown-gpu-lambda",
  "Runtime": "python3.11",
  "Role": "arn:aws:iam::982081090398:role/lambda-gpu-shutdown-role",
  "Handler": "lambda_shutdown.lambda_handler",
  "Environment": {
    "Variables": {
      "GPU_INSTANCE_ID": "i-0f0f6fd680921de5f"
    }
  }
}
```

---

## 📝 下一步操作

### 1. **更新Orchestrator配置文件**

更新 `backend/.env`:
```bash
# AWS Configuration
AWS_DEFAULT_REGION=us-east-1

# SQS Configuration
SQS_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/982081090398/gpu_tasks_queue

# DynamoDB Configuration
DYNAMODB_TABLE=task_store

# GPU Instance Configuration
GPU_INSTANCE_ID=i-0f0f6fd680921de5f
```

### 2. **配置GPU Instance (待部署Adapter)**

需要在GPU实例上配置的文件：

**`/etc/systemd/system/sqs-adapter.service`** 中更新:
```ini
Environment="SQS_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/982081090398/gpu_tasks_queue"
Environment="DYNAMODB_TABLE=task_store"
```

**附加IAM Instance Profile**:
```bash
aws ec2 associate-iam-instance-profile \
  --instance-id i-0f0f6fd680921de5f \
  --iam-instance-profile Name=gpu-instance-profile \
  --region us-east-1
```

### 3. **部署Adapter到GPU实例**

```bash
# 1. 打包文件
cd backend/comfyui-api-service
tar czf adapter.tar.gz sqs_to_comfy_adapter.py sqs-adapter.service setup_adapter.sh

# 2. 复制到GPU实例
scp -i ~/.ssh/zzjw.pem adapter.tar.gz ubuntu@GPU_IP:~

# 3. 在GPU实例上安装
ssh -i ~/.ssh/zzjw.pem ubuntu@GPU_IP
tar xzf adapter.tar.gz
sudo mv sqs_to_comfy_adapter.py sqs-adapter.service setup_adapter.sh /home/ubuntu/comfyui_api_service/
cd /home/ubuntu/comfyui_api_service
chmod +x setup_adapter.sh
sudo ./setup_adapter.sh
```

### 4. **测试完整链路**

#### Test 1: 手动测试队列 → Adapter
```bash
# 发送测试消息
aws sqs send-message \
  --queue-url https://sqs.us-east-1.amazonaws.com/982081090398/gpu_tasks_queue \
  --message-body '{"task_id":"manual-test-001","api_path":"/api/v1/camera-angle/jobs","request_body":{"image_url":"https://example.com/test.jpg","prompt":"test","steps":8}}'

# 查看Adapter日志（在GPU实例上）
sudo journalctl -u sqs-adapter -f
```

#### Test 2: 测试自动关机
```bash
# 等待队列空闲30分钟，观察是否自动关机GPU实例
# 或手动触发告警测试Lambda
```

---

## 💰 成本估算

| 服务 | 使用量 | 月成本(USD) |
|-----|-------|------------|
| **SQS** | < 1M requests | 免费 |
| **DynamoDB** | On-demand, < 1M read/write | ~$5 |
| **Lambda** | < 1M invocations | 免费 |
| **CloudWatch Alarm** | 1 alarm | 免费 |
| **SNS** | < 1K notifications | 免费 |
| **IAM** | Roles & Policies | 免费 |
| **总计** | | **~$5/月** |

**注意**: GPU实例成本不在此列表中（按需计费，~$1.21/小时）

---

## 🔍 监控命令

### 检查SQS队列状态
```bash
aws sqs get-queue-attributes \
  --queue-url https://sqs.us-east-1.amazonaws.com/982081090398/gpu_tasks_queue \
  --attribute-names All
```

### 检查DynamoDB表
```bash
aws dynamodb describe-table --table-name task_store
```

### 检查Lambda日志
```bash
aws logs tail /aws/lambda/shutdown-gpu-lambda --follow
```

### 检查CloudWatch Alarm状态
```bash
aws cloudwatch describe-alarms --alarm-names QueueEmptyFor30Min
```

### 检查GPU实例状态
```bash
aws ec2 describe-instances \
  --instance-ids i-0f0f6fd680921de5f \
  --query 'Reservations[0].Instances[0].State.Name'
```

---

## 🎯 验证清单

- [x] CDK Bootstrap成功
- [x] 5个Stack全部部署成功
- [x] SQS队列创建成功
- [x] DynamoDB表创建成功（带GSI）
- [x] IAM Roles创建成功
- [x] Lambda Function部署成功
- [x] CloudWatch Alarm创建成功
- [x] SNS Topic创建成功
- [x] 测试消息成功发送到SQS
- [ ] GPU实例附加Instance Profile
- [ ] Adapter脚本部署到GPU实例
- [ ] 端到端测试完成
- [ ] 30分钟自动关机测试

---

## 📚 相关文档

- **设计文档**: `../design.md`
- **CDK README**: `README.md`
- **快速开始**: `QUICKSTART.md`
- **架构文档**: `ARCHITECTURE.md`
- **Adapter文档**: `../comfyui-api-service/ADAPTER_README.md`

---

## 🆘 故障排查

### 问题1: Lambda无法关闭GPU实例
**检查**:
```bash
# 1. 检查Lambda权限
aws lambda get-policy --function-name shutdown-gpu-lambda

# 2. 检查GPU实例是否有正确的tag
aws ec2 describe-tags --filters "Name=resource-id,Values=i-0f0f6fd680921de5f"
```

**解决**:
```bash
# 添加必要的tag
aws ec2 create-tags \
  --resources i-0f0f6fd680921de5f \
  --tags Key=Purpose,Value=GPU-ComfyUI
```

### 问题2: Adapter无法读取SQS消息
**检查**:
```bash
# 检查GPU实例的IAM role
aws ec2 describe-instances \
  --instance-ids i-0f0f6fd680921de5f \
  --query 'Reservations[0].Instances[0].IamInstanceProfile'
```

**解决**: 确保Instance Profile已附加（见"下一步操作"第2步）

---

**部署完成时间**: 2025-11-18 12:57 UTC
**总部署耗时**: ~7分钟
**部署状态**: ✅ 所有基础设施就绪，等待Adapter部署
