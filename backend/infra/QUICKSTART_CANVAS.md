# Quick Start: Deploy Canvas Service + Orchestrator to ECS

完整的一键部署指南。

## 🚀 快速部署（3步）

```bash
cd /Users/jingweizhang/Workspace/short-drama/backend/infra

# Step 1: 构建并推送Docker镜像到ECR
./build-and-push.sh

# Step 2: 部署所有基础设施
./deploy.sh

# Step 3: 获取ALB地址
aws cloudformation describe-stacks \
  --stack-name gpu-orchestrator-ecs \
  --query 'Stacks[0].Outputs[?OutputKey==`LoadBalancerDNS`].OutputValue' \
  --output text
```

完成！两个服务已经部署到ECS Fargate。

## 📋 详细说明

### Step 1: 构建Docker镜像

`build-and-push.sh` 脚本会：
- 自动创建ECR仓库（如果不存在）
- 构建 Canvas Service 和 Orchestrator 的Docker镜像
- 推送到ECR

```bash
./build-and-push.sh
```

预计时间：5-10分钟

### Step 2: 部署基础设施

`deploy.sh` 脚本会部署：
- ✅ VPC (2个可用区)
- ✅ Application Load Balancer
- ✅ ECS Cluster
- ✅ 2个Fargate服务 (Canvas + Orchestrator)
- ✅ SQS队列
- ✅ DynamoDB表
- ✅ IAM角色
- ✅ Lambda自动关机
- ✅ CloudWatch告警

```bash
./deploy.sh
```

预计时间：10-15分钟

### Step 3: 验证部署

```bash
# 获取ALB地址
ALB_DNS=$(aws cloudformation describe-stacks \
  --stack-name gpu-orchestrator-ecs \
  --query 'Stacks[0].Outputs[?OutputKey==`LoadBalancerDNS`].OutputValue' \
  --output text)

echo "Canvas Service: http://${ALB_DNS}"
echo "Orchestrator: http://${ALB_DNS}/api/v1"

# 测试Canvas Service
curl -X POST http://${ALB_DNS}/session

# 测试Orchestrator
curl http://${ALB_DNS}/health
```

## 🔄 更新服务

当代码有更新时：

```bash
# 重新构建并推送镜像
./build-and-push.sh

# 强制部署新版本
aws ecs update-service \
  --cluster short-drama-backend-cluster \
  --service canvas-service \
  --force-new-deployment

aws ecs update-service \
  --cluster short-drama-backend-cluster \
  --service orchestrator-service \
  --force-new-deployment
```

## 📊 查看日志

```bash
# Canvas Service日志
aws logs tail /ecs/canvas-service --follow

# Orchestrator日志
aws logs tail /ecs/orchestrator --follow
```

## 🎯 路由配置

ALB自动路由：
- `http://ALB_DNS/api/v1/*` → Orchestrator (端口8080)
- `http://ALB_DNS/*` (其他路径) → Canvas Service (端口9000)

## 🧹 清理资源

```bash
# 销毁所有资源（谨慎！）
cdk destroy --all
```

## 💡 故障排查

### 镜像推送失败

```bash
# 重新登录ECR
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin \
  $(aws sts get-caller-identity --query Account --output text).dkr.ecr.us-east-1.amazonaws.com
```

### 服务健康检查失败

```bash
# 查看任务日志
aws logs tail /ecs/canvas-service --since 5m
aws logs tail /ecs/orchestrator --since 5m
```

### CDK部署失败

```bash
# 检查CDK语法
cdk synth

# 查看差异
cdk diff

# 查看堆栈事件
aws cloudformation describe-stack-events \
  --stack-name gpu-orchestrator-ecs \
  --max-items 10
```

## 📚 更多文档

- [完整部署指南](./DEPLOYMENT_GUIDE.md) - 详细的部署文档
- [CDK README](./README.md) - CDK基础设施说明
- [Canvas Service](../canvas_service/README.md) - Canvas Service API文档
- [Orchestrator](../orchestrator/README.md) - Orchestrator文档

## ✅ 部署检查清单

- [ ] AWS CLI已配置
- [ ] CDK已安装 (`npm install -g aws-cdk`)
- [ ] Docker正在运行
- [ ] CDK已bootstrap (`cdk bootstrap`)
- [ ] 执行 `./build-and-push.sh`
- [ ] 执行 `./deploy.sh`
- [ ] 获取ALB DNS地址
- [ ] 测试两个服务的健康检查

---

如有问题，请查看 [DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md) 获取详细说明。
