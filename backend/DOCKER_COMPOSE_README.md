# Docker Compose Setup

This guide explains how to run Canvas Service and Orchestrator locally using Docker Compose.

## Quick Start

### 1. Ensure Environment Variables

Make sure `backend/.env` exists with all required variables:

```bash
cd /Users/jingweizhang/Workspace/short-drama/backend
cat .env  # Check if it exists and has all required vars
```

Required variables:
- `SUPABASE_URL`
- `SUPABASE_SECRET_KEY`
- `AWS_ACCESS_KEY` (or `AWS_ACCESS_KEY_ID`)
- `AWS_ACCESS_SECRET` (or `AWS_SECRET_ACCESS_KEY`)
- `S3_BUCKET_NAME`
- `SQS_QUEUE_URL`
- `CPU_SQS_QUEUE_URL`
- `DYNAMODB_TABLE`
- `GPU_INSTANCE_ID`
- `CLOUDFRONT_DOMAIN`

### 2. Start Services

```bash
# From the backend directory
cd /Users/jingweizhang/Workspace/short-drama/backend

# Start in foreground (see logs)
docker-compose up --build

# Or start in background
docker-compose up -d --build
```

### 3. Verify Services

```bash
# Check service status
docker-compose ps

# Test canvas service
curl http://localhost:9000/health

# Test orchestrator
curl http://localhost:8080/health
```

### 4. View Logs

```bash
# All services
docker-compose logs -f

# Canvas service only
docker-compose logs -f canvas-service

# Orchestrator only
docker-compose logs -f orchestrator
```

### 5. Stop Services

```bash
# Stop and remove containers
docker-compose down

# Stop, remove containers, and remove volumes
docker-compose down -v
```

## Service Details

### Canvas Service (Port 9000)

**Endpoints:**
- `GET /health` - Health check
- `POST /session` - Create new session
- `POST /upload` - Upload image
- `GET /images?session_id=xxx` - List session images
- `POST /add-image` - Add existing S3 image to session
- `POST /update-position` - Update image position
- `DELETE /delete-image` - Delete image from session

**Dependencies:**
- Supabase (PostgreSQL database)
- S3 (image storage)
- CloudFront (optional CDN)

### Orchestrator (Port 8080)

**Endpoints:**
- `GET /health` - Health check
- `POST /api/v1/qwen-image-edit/jobs` - Submit Qwen image edit job
- `POST /api/v1/camera-angle/jobs` - Submit camera angle job
- `POST /api/v1/face-mask/tasks` - Submit face mask task
- `POST /api/v1/full-face-swap/tasks` - Submit face swap task
- `GET /api/v1/jobs/{job_id}` - Get job status

**Dependencies:**
- SQS (task queues)
- DynamoDB (task status)
- EC2 (GPU instance management)
- S3 (result storage)

## Network

Both services are on the same Docker network (`backend-network`), allowing them to communicate:

```
canvas-service:9000 <--> orchestrator:8080
```

## Resource Limits

Each service has resource constraints to prevent resource exhaustion:

**Limits:**
- CPU: 0.5 cores
- Memory: 512 MB

**Reservations:**
- CPU: 0.25 cores
- Memory: 256 MB

Adjust these in `docker-compose.yml` if needed.

## Health Checks

Both services have health checks that run every 30 seconds:

- **Start period**: 10s (grace period before checks begin)
- **Interval**: 30s
- **Timeout**: 5s
- **Retries**: 3

Docker Compose will restart unhealthy containers automatically.

## Troubleshooting

### Service won't start

1. **Check logs**:
   ```bash
   docker-compose logs canvas-service
   docker-compose logs orchestrator
   ```

2. **Check environment variables**:
   ```bash
   docker-compose config
   ```

3. **Rebuild images**:
   ```bash
   docker-compose build --no-cache
   docker-compose up
   ```

### Port conflicts

If ports 9000 or 8080 are already in use:

1. **Find processes using ports**:
   ```bash
   lsof -i :9000
   lsof -i :8080
   ```

2. **Kill processes or change ports** in `docker-compose.yml`:
   ```yaml
   ports:
     - "9001:9000"  # Map to different host port
   ```

### Connection refused

1. **Check if containers are running**:
   ```bash
   docker-compose ps
   ```

2. **Check if services are healthy**:
   ```bash
   docker inspect backend-canvas-service-1 --format='{{.State.Health.Status}}'
   docker inspect backend-orchestrator-1 --format='{{.State.Health.Status}}'
   ```

3. **Test from inside container**:
   ```bash
   docker-compose exec canvas-service curl http://localhost:9000/health
   docker-compose exec orchestrator curl http://localhost:8080/health
   ```

### Environment variable issues

If services can't connect to external resources:

1. **Verify .env is loaded**:
   ```bash
   docker-compose config | grep -A 5 environment
   ```

2. **Check AWS credentials**:
   ```bash
   docker-compose exec orchestrator env | grep AWS
   ```

3. **Check Supabase config**:
   ```bash
   docker-compose exec canvas-service env | grep SUPABASE
   ```

## Development Workflow

### Make code changes

1. **Edit source files** (e.g., `canvas_service/server.py`)
2. **Rebuild and restart**:
   ```bash
   docker-compose up --build
   ```

### Test single service

```bash
# Rebuild only canvas service
docker-compose build canvas-service
docker-compose up canvas-service

# Rebuild only orchestrator
docker-compose build orchestrator
docker-compose up orchestrator
```

### Interactive debugging

```bash
# Get shell in running container
docker-compose exec canvas-service /bin/bash

# Run Python interpreter
docker-compose exec orchestrator python

# Check installed packages
docker-compose exec canvas-service pip list
```

## Production Deployment

For production deployment to AWS ECS, see:
- [ECS_DEPLOYMENT_GUIDE.md](./ECS_DEPLOYMENT_GUIDE.md)
- `deploy-to-ecs.sh` - Deployment script
- `setup-ecs-service.sh` - Initial ECS setup

## Comparison: Docker Compose vs ECS

| Feature | Docker Compose | ECS Fargate |
|---------|----------------|-------------|
| **Use Case** | Local development | Production deployment |
| **Scaling** | Manual | Auto-scaling |
| **High Availability** | Single host | Multi-AZ |
| **Monitoring** | docker logs | CloudWatch |
| **Cost** | Free (local) | ~$30/month |
| **Setup Time** | Minutes | Hours (first time) |
| **Networking** | Bridge network | VPC with ALB |
| **Security** | Local only | IAM, SG, Secrets Manager |

## Next Steps

1. ✅ **Local testing** - Use Docker Compose
2. ✅ **Environment setup** - Configure `.env`
3. ⬜ **ECS deployment** - Follow ECS deployment guide
4. ⬜ **CI/CD** - Set up automated deployments
5. ⬜ **Monitoring** - Configure CloudWatch dashboards
