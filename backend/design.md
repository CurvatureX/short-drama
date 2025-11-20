# GPU 异步编排系统设计文档

**版本**: 2.0
**状态**: 已批准
**最后更新**: 2025-11-18

---

## 1. 摘要 (Executive Summary)

本文档设计了一个**成本优化的异步任务处理系统**。此系统的核心目标是允许前端（Client）像调用一个 24/7 服务一样调用一个昂贵的 GPU API，而该 GPU 实例（EC2）只在真正需要时才启动，并在连续 **30 分钟**没有新任务时自动关闭。

我们将构建一个 **Orchestrator Service（编排器）** 作为系统的唯一入口（门面）。它负责接收所有 API 请求，将其转换为 SQS 队列中的任务，并立即返回一个 `task_id`。一个特定的 GPU 实例将通过一个 **Adapter 脚本**来消费队列中的任务。

关机逻辑是解耦的：一个 **CloudWatch 告警**将监控 SQS 队列，如果队列连续 30 分钟没有可见消息，它将触发一个 **Lambda 函数**来安全地关闭 GPU 实例。

---

## 2. 核心业务规则 (Business Rules)

### 2.1 成本优先
GPU 实例在空闲时不应产生费用。通过按需启动和自动关机，最大限度降低云计算成本。

### 2.2 异步体验
前端（Client）提交任务时，必须在 **1 秒内**收到 `202 Accepted` 响应，不得等待 GPU 启动或任务处理。

### 2.3 单一实例
本设计针对一个特定的、已知的 GPU 实例（例如 `i-0f0f6fd680921de5f`）。

### 2.4 30 分钟关机策略（硬性）

**规则 A (空闲关机)**：
如果 SQS 队列连续 30 分钟为空（没有新任务提交），则关闭 GPU 实例。

**规则 B (超时清理)**：
如果一个任务导致 SQS 队列（对 CloudWatch 而言）"可见消息为 0"的状态持续了 30 分钟，系统将有意地关闭该实例。这被视为一个清理机制，用于处理不符合预期的、卡住的或运行过久的任务。

---

## 3. 架构图 (Architecture)

```
                    (HTTPS: 443)
    +------------+  POST /api/v1/...      +--------------------------+
    | Frontend   | -----------------------> | Orchestrator Service    | (AWS SDK)
    | (Client)   | <----------------------- | (AWS Fargate / t4g.small)|
    +------------+  GET /api/v1/jobs/{id}  +--------------------------+
       (轮询状态)     (立即返回 task_id)      | 1. 写 DynamoDB (PENDING)
                                            | 2. 发送 SQS 消息
                                            | 3. 检查 EC2 状态 -> StartInstances
                                            |
                  +------------------+      |
                  | AWS DynamoDB     | <----+ (读/写状态)
                  | (task_store 表)  | <------------------------------------+
                  +------------------+                                      |
                         ^                                                  |
                         |                                                  |
      +------------------|---------------------------------+                |
      | AWS EC2 GPU Instance (i-0f0f6fd680921de5f)       |                |
      | IP: 34.203.11.145                                 |                |
      | Type: g6e.2xlarge (NVIDIA L40S, 46GB VRAM)        |                |
      |                                                    |                |
      | +---------------------------+  +--------------------------+         |
      | | ComfyUI Unified API      | <--| Adapter Script          |         |
      | | (http://localhost:8000)  | 本地| (sqs_to_comfy_adapter.py)|         |
      | +---------------------------+ 调用| +--------------------------+         |
      |   • /api/v1/camera-angle/jobs   | | 1. 轮询 SQS             |         |
      |   • /api/v1/qwen-image-edit/jobs| | 2. 写 DynamoDB (PROC...)| ---------+
      |   • /api/v1/jobs/{job_id}       | | 3. 调用本地 ComfyUI API |
      |                                  | | 4. 写 DynamoDB (COMP...)|
      +----------------------------------+ | 5. 删除 SQS 消息        |
                         ^                 +--------------------------+
                         |                          |
                         +--------------------------|
                                                    |
                                      (从 SQS 拉取) |
                                                    |
                         +--------------------------+
                         | AWS SQS                 |
                         | (gpu_tasks_queue)       |
                         +--------------------------+
                                    |
                                    | 1. (外部监控) CloudWatch 检查
                                    |    ApproximateNumberOfMessagesVisible == 0
                                    |    持续 30 分钟
                                    v
                         +--------------------------+
                         | CloudWatch Alarm         |
                         | (QueueEmptyFor30Min)     |
                         +--------------------------+
                                    |
                                    | 2. (触发)
                                    v
                         +--------------------------+
                         | AWS Lambda Function      |
                         | (shutdown-gpu-lambda)    |
                         |                          | (AWS SDK)
                         | 3. 调用 ec2:StopInstances|
                         |    on 'i-0f0f6fd680921de5f'|
                         +--------------------------+
```

---

## 4. 详细组件职责

### 4.1. 📍 Orchestrator Service (CPU 实例 / Fargate)

这是系统的唯一入口和"大脑"。

#### 职责 1：API 门面 (Facade)
- 实现并向公网暴露所有 `POST /api/v1/.../jobs` 和 `GET /api/v1/jobs/{id}` 端点
- 处理前端的身份验证（如果需要）

#### 职责 2：任务创建与路由
- 接收 POST 请求
- 生成一个唯一的 `task_id` (例如 UUID)
- 将任务状态 (`PENDING`) 和 `task_id` 写入 DynamoDB
- 将完整的任务信息（包含 `task_id` 和原始 `request_body`）打包发送到 SQS
- **立即**向前端返回 `202 Accepted` 和 `task_id`

#### 职责 3：GPU 启动器 (Starter)
- 在发送 SQS 消息之前，调用 `ec2:DescribeInstances` 检查 `i-0f0f6fd680921de5f` 的状态
- 如果状态是 `stopped`，则调用 `ec2:StartInstances` 唤醒它
- 如果状态是 `running` 或 `pending`，则什么都不做

#### 职责 4：状态报告
- 响应 `GET /api/v1/jobs/{id}` 请求
- 它只查询 DynamoDB 表来获取 `task_id` 的最新状态，然后原样返回

---

### 4.2. 🚀 GPU Worker (EC2 实例)

**实例详情**：
- **Instance ID**: `i-0f0f6fd680921de5f`
- **Public IP**: `34.203.11.145` (动态，每次启动可能变化)
- **Instance Type**: `g6e.2xlarge`
- **GPU**: NVIDIA L40S (46GB VRAM)
- **OS**: Ubuntu 22.04 LTS
- **Region**: us-east-1

这是"苦力"。它由两个协同工作的进程组成，这两个进程都通过 **systemd** 开机自启。

#### 组件 1：ComfyUI Unified API Service ✅ 已完成

**服务文件**: `/etc/systemd/system/comfyui-unified-api.service`
**运行状态**: ✅ Active and running
**监听端口**: `http://localhost:8000`

**关键特性**：
- ✅ 统一的 RESTful API 设计
- ✅ 版本化路径 (`/api/v1/`)
- ✅ 支持 S3 URI 和 HTTPS URL
- ✅ 异步任务处理
- ✅ 自动重启（10秒延迟）

**API 端点**：
```
GET  /                                      # API 信息
GET  /health                                # 健康检查

POST /api/v1/camera-angle/jobs              # 相机角度转换
GET  /api/v1/camera-angle/jobs/{job_id}     # 查询相机角度任务

POST /api/v1/qwen-image-edit/jobs           # Qwen 图像编辑
GET  /api/v1/qwen-image-edit/jobs/{job_id}  # 查询 Qwen 编辑任务

GET  /api/v1/jobs/{job_id}                  # 统一任务状态查询
```

**底层工作流**：
- **Camera Angle**: `camera-multi-angle.json`
  - 输入：1 张图片
  - 默认步数：8
  - 用途：相机视角转换

- **Qwen Image Edit**: `AIO.json` (Qwen-Image-Edit-Rapid-AIO)
  - 输入：1-3 张图片（支持多图输入）
  - 默认步数：4（更快）
  - 采样器：可配置（sa_solver, lcm, euler_a, er_sde）
  - 用途：线稿提取、风格转换、通用图像编辑

**服务管理**：
```bash
# 查看状态
sudo systemctl status comfyui-unified-api

# 重启服务
sudo systemctl restart comfyui-unified-api

# 查看日志
sudo journalctl -u comfyui-unified-api -f
tail -f /var/log/comfyui-unified-api.log
```

**职责**：
- 监听本地 `localhost:8000`，**不暴露给公网**
- 处理 POST 请求并执行 GPU 计算
- 返回结果（或状态）
- **不需要知道** SQS 或 AWS 的存在

#### 组件 2：ComfyUI 核心引擎 ✅ 已完成

**服务文件**: `/etc/systemd/system/comfyui.service`
**运行状态**: ✅ Active and running
**监听端口**: `http://localhost:8188`
**版本**: ComfyUI v0.3.68
**Python 环境**: `/home/ubuntu/ComfyUI/venv` (PyTorch 2.6.0+cu124)

**已安装组件**：
- ✅ ComfyUI Manager
- ✅ Custom nodes (全部正常加载)
  - `comfyui_controlnet_aux`
  - `was-ns`
  - `comfyui-easy-use`
- ✅ Qwen-Image-Edit 模型支持

**服务管理**：
```bash
# 查看状态
sudo systemctl status comfyui

# 重启服务
sudo systemctl restart comfyui

# 查看日志
sudo journalctl -u comfyui -f
```

#### 组件 3：Adapter 脚本 ⏳ 待开发

**文件名**: `sqs_to_comfy_adapter.py`
**状态**: ⏳ 未开发

**职责**：充当 SQS 和本地 ComfyUI 之间的"桥梁"

**核心逻辑**：
1. 在无限 `while True` 循环中运行
2. **轮询**：长轮询 `gpu_tasks_queue`
3. **收到任务**：
   - 更新 DynamoDB，将 `task_id` 状态设为 `PROCESSING`
   - 从 SQS 消息体中解析出 `api_path` 和 `request_body`
   - 向 `http://localhost:8000{api_path}` 发送一个 POST 请求
4. **轮询本地**：
   - ComfyUI API 返回它自己的 `comfy_job_id`
   - Adapter 脚本开始轮询 `http://localhost:8000/api/v1/jobs/{comfy_job_id}`
   - 持续轮询直到状态变为 `completed` 或 `failed`
5. **完成任务**：
   - 将最终结果（`result_s3_uri` 或 `error`）写回 DynamoDB
   - 更新状态为 `COMPLETED` 或 `FAILED`
   - 从 SQS 中删除该消息

**重要**：此脚本**没有任何关机逻辑**。关机由独立的 CloudWatch + Lambda 系统处理。

**systemd 配置** (待创建):
```ini
[Unit]
Description=SQS to ComfyUI Adapter Service
After=network.target comfyui-unified-api.service
Requires=comfyui-unified-api.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/comfyui_api_service
Environment="PATH=/home/ubuntu/ComfyUI/venv/bin:/usr/local/bin:/usr/bin:/bin"
Environment="AWS_REGION=us-east-1"
Environment="SQS_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/.../gpu_tasks_queue"
Environment="DYNAMODB_TABLE=task_store"
ExecStart=/home/ubuntu/ComfyUI/venv/bin/python /home/ubuntu/comfyui_api_service/sqs_to_comfy_adapter.py
Restart=always
RestartSec=10
StandardOutput=append:/var/log/sqs-adapter.log
StandardError=append:/var/log/sqs-adapter-error.log

[Install]
WantedBy=multi-user.target
```

---

### 4.3. 💤 自动关机系统 (CloudWatch + Lambda) ⏳ 待开发

这是一个独立的、解耦的系统，用于执行我们的 30 分钟业务规则。

#### 组件 1：CloudWatch Alarm ⏳ 待创建

**职责**：监控 `AWS/SQS` 命名空间下的 `ApproximateNumberOfMessagesVisible` 指标

**规则**：当指标 `== 0` 连续 30 分钟（例如：6 个周期，每周期 5 分钟），触发 `ALARM` 状态

**配置参数**：
```yaml
AlarmName: QueueEmptyFor30Min
Namespace: AWS/SQS
MetricName: ApproximateNumberOfMessagesVisible
Statistic: Average
Period: 300  # 5 分钟
EvaluationPeriods: 6  # 6 × 5 = 30 分钟
Threshold: 0
ComparisonOperator: LessThanOrEqualToThreshold
```

#### 组件 2：Lambda Function ⏳ 待开发

**函数名**: `shutdown-gpu-lambda`
**运行时**: Python 3.11
**触发器**: CloudWatch Alarm (QueueEmptyFor30Min)

**职责**：
- 作为 ALARM 的动作被触发
- 调用 `ec2:DescribeInstances` 检查 `i-0f0f6fd680921de5f` 是否处于 `running` 状态
- 如果是 `running`，调用 `ec2:StopInstances` 将其关闭
- 记录关机事件到 CloudWatch Logs

**所需 IAM 权限**：
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeInstances",
        "ec2:StopInstances"
      ],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "ec2:ResourceTag/Purpose": "GPU-ComfyUI"
        }
      }
    },
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "*"
    }
  ]
}
```

---

## 5. Orchestrator API 设计 (前端可见) ⏳ 待开发

前端只与这个 API 交互。它完美模仿了现有的 ComfyUI API 结构，但提供了**异步响应**。

**Base URL**: `https://api.your-domain.com` (指向 Orchestrator 的 ALB/Fargate)

### 5.1. POST `/api/v1/camera-angle/jobs`

提交一个相机角度转换任务。

**Request Body** (与现有 API 一致):
```json
{
  "image_url": "s3://bucket/image.jpg",
  "prompt": "将镜头转为俯视",
  "seed": 12345,
  "steps": 8
}
```

**Response** (立即返回):
```json
{
  "job_id": "a1b2c3d4-e5f6-7890-g1h2-i3j4k5l6m7n8",
  "status": "pending",
  "result_s3_uri": null,
  "error": null
}
```

### 5.2. POST `/api/v1/qwen-image-edit/jobs`

提交一个 Qwen 图像编辑任务。

**Request Body** (与现有 API 一致):
```json
{
  "image_url": "s3://bucket/main.jpg",
  "prompt": "提取黑白线稿",
  "image2_url": "s3://bucket/ref1.jpg",
  "steps": 4,
  "cfg": 1.0,
  "sampler_name": "sa_solver"
}
```

**Response** (立即返回):
```json
{
  "job_id": "b1c2d3e4-f5g6-7890-h1i2-j3k4l5m6n7o8",
  "status": "pending",
  "result_s3_uri": null,
  "error": null
}
```

### 5.3. GET `/api/v1/jobs/{job_id}`

获取任何任务的状态（统一查询端点）。

**Request**:
```
GET https://api.your-domain.com/api/v1/jobs/a1b2c3d4-e5f6-7890-g1h2-i3j4k5l6m7n8
```

**Response** (处理中):
```json
{
  "job_id": "a1b2c3d4-...",
  "status": "processing",
  "result_s3_uri": null,
  "error": null
}
```

**Response** (已完成):
```json
{
  "job_id": "a1b2c3d4-...",
  "status": "completed",
  "result_s3_uri": "s3://bucket/comfyui-results/camera-angle/a1b2c3d4.../output.png",
  "error": null
}
```

### 5.4. GET `/health`

检查 Orchestrator 服务的健康。

**Response**:
```json
{
  "status": "healthy",
  "message": "Orchestrator is running"
}
```

---

## 6. 内部数据模型

### 6.1. SQS 消息体 (Message Body)

这是 Orchestrator 发送给 `gpu_tasks_queue` 的 JSON 载荷。

```json
{
  "task_id": "a1b2c3d4-e5f6-7890-g1h2-i3j4k5l6m7n8",
  "api_path": "/api/v1/camera-angle/jobs",
  "request_body": {
    "image_url": "s3://bucket/image.jpg",
    "prompt": "将镜头转为俯视",
    "seed": 12345,
    "steps": 8
  }
}
```

**字段说明**：
- `task_id`: 唯一的 ID，用于 DynamoDB 跟踪
- `api_path`: **极其重要**，Adapter 脚本需要知道 `localhost:8000` 上的哪个端点
- `request_body`: 原始的、未经修改的 JSON 请求

### 6.2. DynamoDB 表 (task_store) ⏳ 待创建

这是我们的"单一事实来源"。

**主键**: `task_id` (String)

**示例项目 (Item)**:
```json
{
  "task_id": "a1b2c3d4-...",
  "status": "completed",
  "job_type": "/api/v1/camera-angle/jobs",
  "created_at": 1678886400,
  "updated_at": 1678886520,
  "result_s3_uri": "s3://bucket/comfyui-results/camera-angle/a1b2c3d4.../output.png",
  "error_message": null,
  "comfy_job_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**状态流转**:
```
PENDING → PROCESSING → COMPLETED
                     ↘ FAILED
```

**索引设计** (可选):
- **GSI**: `status-created_at-index` (用于查询特定状态的任务列表)

---

## 7. 工作流程示例

### 7.1. 正常流程（成功案例）

```
1. 前端 → Orchestrator: POST /api/v1/camera-angle/jobs
   ↓
2. Orchestrator:
   - 生成 task_id: "abc-123"
   - 写入 DynamoDB: {task_id: "abc-123", status: "pending"}
   - 发送到 SQS: {task_id: "abc-123", api_path: "/api/v1/camera-angle/jobs", ...}
   - 检查 EC2 状态 → 如果 stopped，调用 StartInstances
   ↓
3. Orchestrator → 前端: 202 Accepted {job_id: "abc-123", status: "pending"}
   ↓
4. 前端开始轮询: GET /api/v1/jobs/abc-123 (每2秒)
   ↓
5. GPU Instance 启动（约2分钟）
   ↓
6. Adapter 脚本开始运行:
   - 从 SQS 拉取消息: {task_id: "abc-123", api_path: "/api/v1/camera-angle/jobs", ...}
   - 更新 DynamoDB: {task_id: "abc-123", status: "processing"}
   - POST http://localhost:8000/api/v1/camera-angle/jobs
   ↓
7. ComfyUI API 返回: {job_id: "comfy-xyz-789", status: "pending"}
   ↓
8. Adapter 脚本轮询 ComfyUI:
   - GET http://localhost:8000/api/v1/jobs/comfy-xyz-789
   - 等待状态变为 "completed"
   ↓
9. ComfyUI 完成处理（约30秒）
   ↓
10. Adapter 脚本:
    - 收到结果: {status: "completed", result_s3_uri: "s3://..."}
    - 更新 DynamoDB: {task_id: "abc-123", status: "completed", result_s3_uri: "s3://..."}
    - 删除 SQS 消息
    ↓
11. 前端下次轮询: GET /api/v1/jobs/abc-123
    ↓
12. Orchestrator → 前端: {job_id: "abc-123", status: "completed", result_s3_uri: "s3://..."}
    ↓
13. 30 分钟后无新任务
    ↓
14. CloudWatch Alarm 触发 → Lambda 关闭 GPU 实例
```

### 7.2. 失败流程（任务失败）

```
1-7. [同正常流程]
   ↓
8. ComfyUI 处理失败（图片下载失败、GPU OOM 等）
   ↓
9. Adapter 脚本:
   - 收到结果: {status: "failed", error: "Image download failed"}
   - 更新 DynamoDB: {task_id: "abc-123", status: "failed", error_message: "Image download failed"}
   - 删除 SQS 消息
   ↓
10. 前端轮询: GET /api/v1/jobs/abc-123
    ↓
11. Orchestrator → 前端: {job_id: "abc-123", status: "failed", error: "Image download failed"}
```

---

## 8. 已完成工作总结 ✅

### 8.1. GPU 服务器配置 ✅
- ✅ EC2 实例 `i-0f0f6fd680921de5f` (g6e.2xlarge, NVIDIA L40S 46GB)
- ✅ Ubuntu 22.04 LTS 安装完成
- ✅ NVIDIA Driver 安装完成
- ✅ CUDA 12.4 支持

### 8.2. ComfyUI 环境搭建 ✅
- ✅ ComfyUI v0.3.68 安装
- ✅ Python 虚拟环境配置 (`/home/ubuntu/ComfyUI/venv`)
- ✅ PyTorch 2.6.0+cu124 安装
- ✅ ComfyUI Manager 安装
- ✅ 所有自定义节点正常加载
  - `comfyui_controlnet_aux`
  - `was-ns`
  - `comfyui-easy-use`
- ✅ Qwen-Image-Edit 模型支持

### 8.3. ComfyUI 统一 API 服务 ✅
- ✅ 统一 API 服务 (`unified_api.py`) 开发完成
- ✅ RESTful 设计，版本化路径 (`/api/v1/`)
- ✅ 两个工作流支持:
  - Camera Angle (`camera-multi-angle.json`)
  - Qwen Image Edit (`AIO.json`)
- ✅ S3 和 HTTPS URL 支持
- ✅ 异步任务处理
- ✅ systemd 服务配置
- ✅ 自动启动和崩溃重启
- ✅ 日志记录系统

### 8.4. API 端点实现 ✅
- ✅ `GET /` - API 信息
- ✅ `GET /health` - 健康检查
- ✅ `POST /api/v1/camera-angle/jobs` - 相机角度转换
- ✅ `GET /api/v1/camera-angle/jobs/{job_id}` - 相机角度任务状态
- ✅ `POST /api/v1/qwen-image-edit/jobs` - Qwen 图像编辑
- ✅ `GET /api/v1/qwen-image-edit/jobs/{job_id}` - Qwen 编辑任务状态
- ✅ `GET /api/v1/jobs/{job_id}` - 统一任务状态查询

### 8.5. 文档完成 ✅
- ✅ API 参考文档 (`API_REFERENCE.md`)
- ✅ 快速开始指南 (`UNIFIED_QUICK_START.md`)
- ✅ 服务管理文档 (`SERVICE_MANAGEMENT.md`)
- ✅ 当前状态文档 (`CURRENT_API_STATUS.md`)
- ✅ 测试脚本 (`test_unified_api.py`)

---

## 9. 待开发工作清单 ⏳

### 9.1. 高优先级
- [ ] **Orchestrator Service** (Fargate / ECS)
  - [ ] FastAPI 应用开发
  - [ ] DynamoDB 集成
  - [ ] SQS 集成
  - [ ] EC2 启动逻辑
  - [ ] API Gateway / ALB 配置
  - [ ] SSL 证书配置

- [ ] **SQS Queue** 配置
  - [ ] 创建 `gpu_tasks_queue`
  - [ ] 配置可见性超时（建议 5 分钟）
  - [ ] 配置死信队列（DLQ）

- [ ] **DynamoDB Table** 创建
  - [ ] 创建 `task_store` 表
  - [ ] 配置 GSI (status-created_at-index)
  - [ ] 设置 TTL（可选，用于自动清理旧任务）

- [ ] **Adapter 脚本** (`sqs_to_comfy_adapter.py`)
  - [ ] SQS 长轮询逻辑
  - [ ] DynamoDB 写入逻辑
  - [ ] 本地 ComfyUI API 调用
  - [ ] 错误处理和重试
  - [ ] systemd 服务配置
  - [ ] 部署到 GPU 实例

### 9.2. 中优先级
- [ ] **CloudWatch Alarm** 配置
  - [ ] 创建 QueueEmptyFor30Min 告警
  - [ ] 配置告警阈值和评估周期
  - [ ] 连接到 Lambda 触发器

- [ ] **Lambda Function** (`shutdown-gpu-lambda`)
  - [ ] Python 代码开发
  - [ ] IAM 角色和权限配置
  - [ ] CloudWatch Logs 集成
  - [ ] 测试和验证

### 9.3. 低优先级（优化）
- [ ] 监控和告警
  - [ ] CloudWatch Dashboard
  - [ ] 任务失败率监控
  - [ ] GPU 使用率监控
  - [ ] 成本监控

- [ ] 安全加固
  - [ ] API 认证（API Key / JWT）
  - [ ] VPC 配置
  - [ ] Security Group 优化
  - [ ] IAM 权限最小化

- [ ] 性能优化
  - [ ] Adapter 脚本并发处理（可选）
  - [ ] DynamoDB 流式读取
  - [ ] S3 传输加速

---

## 10. 部署检查清单

### 10.1. GPU 实例准备 ✅
- [x] EC2 实例已配置
- [x] ComfyUI 服务运行正常
- [x] Unified API 服务运行正常
- [x] systemd 服务自动启动
- [ ] Adapter 脚本部署
- [ ] Adapter systemd 服务配置

### 10.2. AWS 资源创建 ⏳
- [ ] SQS 队列创建
- [ ] DynamoDB 表创建
- [ ] CloudWatch Alarm 配置
- [ ] Lambda 函数部署
- [ ] IAM 角色和权限配置

### 10.3. Orchestrator 部署 ⏳
- [ ] Fargate / ECS 集群创建
- [ ] Task Definition 配置
- [ ] Service 创建
- [ ] ALB / API Gateway 配置
- [ ] DNS 配置
- [ ] SSL 证书安装

### 10.4. 测试验证 ⏳
- [ ] 端到端流程测试
- [ ] GPU 自动启动测试
- [ ] 任务处理测试
- [ ] 30 分钟自动关机测试
- [ ] 失败场景测试
- [ ] 性能压测

---

## 11. 成本估算

### 11.1. GPU 实例成本
- **Instance Type**: g6e.2xlarge
- **按需价格**: ~$1.21/小时（us-east-1）
- **预计使用**: 每天 2-4 小时（取决于任务量）
- **月成本**: $72 - $144

### 11.2. 其他服务成本（估算）
- **Fargate**: $10-20/月（CPU 实例，24/7 运行）
- **DynamoDB**: $5-10/月（按需模式）
- **SQS**: 几乎免费（前 100 万请求免费）
- **Lambda**: 几乎免费（每月 100 万次调用免费）
- **数据传输**: $5-10/月

**总计月成本**: ~$92 - $184

---

## 12. 风险和缓解措施

### 12.1. 风险 1: GPU 启动延迟
**风险**: EC2 实例从 stopped 到 running 需要 2-3 分钟
**缓解**: 前端显示"任务已提交，正在启动 GPU..."的友好提示

### 12.2. 风险 2: 任务卡死
**风险**: 某个任务卡住，导致队列永远有"不可见"消息
**缓解**:
- SQS 可见性超时设为 5 分钟
- DLQ 捕获失败消息
- 30 分钟规则 B 自动清理

### 12.3. 风险 3: 意外关机
**风险**: 正在处理任务时被 CloudWatch Alarm 关机
**缓解**:
- CloudWatch 监控的是"可见消息数"，处理中的消息是不可见的
- 只有队列真正空闲 30 分钟才会触发

### 12.4. 风险 4: DynamoDB 写入失败
**风险**: 网络问题导致状态更新失败
**缓解**:
- Adapter 脚本实现重试逻辑（指数退避）
- 使用 DynamoDB 条件写入避免覆盖

---

## 13. 附录

### 13.1. 相关文档
- GPU 服务器详细配置: `CURRENT_API_STATUS.md`
- API 完整参考: `API_REFERENCE.md`
- 快速开始指南: `UNIFIED_QUICK_START.md`
- 服务管理手册: `SERVICE_MANAGEMENT.md`

### 13.2. 联系信息
- **技术负责人**: [Your Name]
- **项目仓库**: [GitHub URL]
- **文档更新**: 2025-11-18

---

**文档版本**: 2.0
**批准状态**: ✅ 已批准
**下一步**: 开始 Orchestrator Service 开发
