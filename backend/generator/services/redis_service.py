"""
Redis service for task status tracking
"""

import redis
import json
import logging
from typing import Optional, Dict, Any
from config import settings

logger = logging.getLogger(__name__)


class RedisService:
    """Service for managing task status in Redis"""

    def __init__(self):
        try:
            self.redis_client = redis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                db=settings.redis_db,
                password=settings.redis_password if settings.redis_password else None,
                decode_responses=True,
                socket_connect_timeout=10,  # 10 second timeout
                socket_timeout=5,
                ssl=True,  # AWS ElastiCache Serverless requires TLS
                ssl_cert_reqs=None,  # Don't verify SSL certificate
            )
            # Test connection
            self.redis_client.ping()
            self.connected = True
            logger.info(f"✓ Connected to Redis at {settings.redis_host}:{settings.redis_port}")
        except Exception as e:
            logger.error(f"✗ Redis connection failed: {e}")
            logger.warning("Running without Redis - task status tracking disabled")
            self.redis_client = None
            self.connected = False

    def get_client(self) -> redis.Redis:
        """Get Redis client instance"""
        return self.redis_client

    def set_task_status(
        self,
        session_id: str,
        status: str,
        progress: int = 0,
        message: str = "",
        result_url: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        """
        Set task status in Redis

        Args:
            session_id: Unique session identifier
            status: Task status (pending, processing, completed, failed)
            progress: Progress percentage (0-100)
            message: Status message
            result_url: URL to the generated file (S3 URL)
            error: Error message if task failed
        """
        if not self.connected or not self.redis_client:
            logger.warning(f"Redis not connected, skipping status update for {session_id}")
            return

        try:
            task_data = {
                "session_id": session_id,
                "status": status,
                "progress": progress,
                "message": message,
            }

            if result_url:
                task_data["result_url"] = result_url

            if error:
                task_data["error"] = error

            key = f"task:{session_id}"
            self.redis_client.setex(
                key, settings.task_ttl, json.dumps(task_data)
            )
            logger.info(f"Task {session_id} status updated: {status} ({progress}%)")
        except Exception as e:
            logger.error(f"Failed to set task status: {e}")

    def get_task_status(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get task status from Redis

        Args:
            session_id: Unique session identifier

        Returns:
            Task status data or None if not found
        """
        if not self.connected or not self.redis_client:
            logger.warning(f"Redis not connected, cannot get status for {session_id}")
            return None

        try:
            key = f"task:{session_id}"
            data = self.redis_client.get(key)

            if data:
                return json.loads(data)
            return None
        except Exception as e:
            logger.error(f"Failed to get task status: {e}")
            return None

    def delete_task_status(self, session_id: str) -> None:
        """Delete task status from Redis"""
        if not self.connected or not self.redis_client:
            return

        try:
            key = f"task:{session_id}"
            self.redis_client.delete(key)
            logger.info(f"Task {session_id} deleted from Redis")
        except Exception as e:
            logger.error(f"Failed to delete task status: {e}")

    def ping(self) -> bool:
        """Check if Redis is connected"""
        if not self.connected or not self.redis_client:
            return False

        try:
            return self.redis_client.ping()
        except Exception as e:
            logger.error(f"Redis connection error: {str(e)}")
            return False


# Singleton instance
redis_service = RedisService()
