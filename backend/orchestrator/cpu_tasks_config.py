"""
CPU Tasks Configuration

Configuration for CPU-bound tasks that are processed by paid-api-service.
"""

import os

# CPU Task Queue Configuration
CPU_QUEUE_NAME = os.getenv('CPU_QUEUE_NAME', 'cpu_tasks_queue')
CPU_QUEUE_URL = os.getenv('CPU_QUEUE_URL', '')

# DynamoDB configuration (reuses existing table)
CPU_DYNAMODB_TABLE = os.getenv('DYNAMODB_TABLE', 'task_store')

# AWS Configuration
AWS_REGION = os.getenv('AWS_DEFAULT_REGION', 'us-east-1')

# Paid API Service Configuration
PAID_API_SERVICE_URL = os.getenv('PAID_API_SERVICE_URL', 'http://localhost:8000')

# Task types handled by paid-api-service
CPU_TASK_TYPES = {
    'face_mask': '/api/v1/face-mask/jobs',
    'face_swap': '/api/v1/face-swap/jobs',
    'full_face_swap': '/api/v1/full-face-swap/jobs'
}
