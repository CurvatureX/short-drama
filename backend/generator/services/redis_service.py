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
        self.redis_client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db,
            password=settings.redis_password,
            decode_responses=True,
        )

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

    def get_task_status(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get task status from Redis

        Args:
            session_id: Unique session identifier

        Returns:
            Task status data or None if not found
        """
        key = f"task:{session_id}"
        data = self.redis_client.get(key)

        if data:
            return json.loads(data)
        return None

    def delete_task_status(self, session_id: str) -> None:
        """Delete task status from Redis"""
        key = f"task:{session_id}"
        self.redis_client.delete(key)
        logger.info(f"Task {session_id} deleted from Redis")

    def ping(self) -> bool:
        """Check if Redis is connected"""
        try:
            return self.redis_client.ping()
        except Exception as e:
            logger.error(f"Redis connection error: {str(e)}")
            return False


# Singleton instance
redis_service = RedisService()
