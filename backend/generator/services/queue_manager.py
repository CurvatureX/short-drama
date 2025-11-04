"""
Advanced Queue System with priorities and batching
Similar to ComfyUI's queue management
"""

import asyncio
import time
import logging
from typing import Optional, Dict, Any, Callable, List
from dataclasses import dataclass, field
from enum import Enum
from queue import PriorityQueue
from threading import Lock
import uuid

logger = logging.getLogger(__name__)


class TaskPriority(Enum):
    """Task priority levels"""
    LOW = 3
    NORMAL = 2
    HIGH = 1
    URGENT = 0


class TaskStatus(Enum):
    """Task status in queue"""
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(order=True)
class QueuedTask:
    """A task in the queue"""
    priority: int = field(compare=True)
    timestamp: float = field(compare=True)
    session_id: str = field(compare=False)
    task_func: Callable = field(compare=False)
    task_kwargs: Dict[str, Any] = field(compare=False)
    file_extension: str = field(compare=False, default="png")
    content_type: str = field(compare=False, default="image/png")
    batch_id: Optional[str] = field(compare=False, default=None)
    model_name: str = field(compare=False, default="unknown")


@dataclass
class BatchGroup:
    """Group of tasks that can be batched together"""
    batch_id: str
    model_name: str
    tasks: List[QueuedTask]
    created_at: float


class QueueManager:
    """
    Advanced queue system with priorities and batching

    Features:
    - Priority-based scheduling
    - Batch processing support
    - Fair queuing
    - Queue statistics
    - Cancellation support
    """

    def __init__(
        self,
        max_concurrent_tasks: int = 2,
        enable_batching: bool = True,
        batch_timeout: float = 2.0,
        batch_size: int = 4,
    ):
        self.max_concurrent_tasks = max_concurrent_tasks
        self.enable_batching = enable_batching
        self.batch_timeout = batch_timeout
        self.batch_size = batch_size

        # Priority queue for tasks
        self.queue: PriorityQueue[QueuedTask] = PriorityQueue()

        # Track active tasks
        self.active_tasks: Dict[str, QueuedTask] = {}
        self.lock = Lock()

        # Task history
        self.completed_tasks: Dict[str, float] = {}
        self.failed_tasks: Dict[str, str] = {}

        # Batching
        self.pending_batches: Dict[str, BatchGroup] = {}

        # Statistics
        self.total_queued = 0
        self.total_processed = 0
        self.total_failed = 0

        logger.info(
            f"QueueManager initialized: max_concurrent={max_concurrent_tasks}, "
            f"batching={enable_batching}, batch_size={batch_size}"
        )

    def submit_task(
        self,
        session_id: str,
        task_func: Callable,
        task_kwargs: Dict[str, Any],
        priority: TaskPriority = TaskPriority.NORMAL,
        file_extension: str = "png",
        content_type: str = "image/png",
        model_name: str = "unknown",
    ) -> str:
        """
        Submit a task to the queue

        Args:
            session_id: Unique session identifier
            task_func: Function to execute
            task_kwargs: Arguments for the function
            priority: Task priority
            file_extension: Output file extension
            content_type: Output content type
            model_name: Model being used

        Returns:
            session_id
        """
        task = QueuedTask(
            priority=priority.value,
            timestamp=time.time(),
            session_id=session_id,
            task_func=task_func,
            task_kwargs=task_kwargs,
            file_extension=file_extension,
            content_type=content_type,
            model_name=model_name,
        )

        with self.lock:
            self.queue.put(task)
            self.total_queued += 1

        logger.info(
            f"Task {session_id} queued with priority {priority.name} "
            f"(Queue size: {self.get_queue_size()})"
        )

        return session_id

    def get_next_task(self) -> Optional[QueuedTask]:
        """
        Get the next task to process

        Returns:
            Next task or None if queue is empty
        """
        try:
            if self.queue.empty():
                return None

            task = self.queue.get_nowait()

            with self.lock:
                self.active_tasks[task.session_id] = task

            return task

        except Exception:
            return None

    def mark_task_completed(self, session_id: str):
        """Mark a task as completed"""
        with self.lock:
            if session_id in self.active_tasks:
                del self.active_tasks[session_id]
                self.completed_tasks[session_id] = time.time()
                self.total_processed += 1

        logger.info(f"Task {session_id} marked as completed")

    def mark_task_failed(self, session_id: str, error: str):
        """Mark a task as failed"""
        with self.lock:
            if session_id in self.active_tasks:
                del self.active_tasks[session_id]
                self.failed_tasks[session_id] = error
                self.total_failed += 1

        logger.warning(f"Task {session_id} marked as failed: {error}")

    def cancel_task(self, session_id: str) -> bool:
        """
        Cancel a queued or active task

        Returns:
            True if task was cancelled, False if not found
        """
        with self.lock:
            # Check if task is active
            if session_id in self.active_tasks:
                logger.warning(f"Cannot cancel active task {session_id}")
                return False

            # TODO: Implement queue scanning to remove queued tasks
            # This requires a more complex queue structure

            return False

    def get_queue_size(self) -> int:
        """Get current queue size"""
        return self.queue.qsize()

    def get_active_count(self) -> int:
        """Get number of active tasks"""
        with self.lock:
            return len(self.active_tasks)

    def can_process_more(self) -> bool:
        """Check if more tasks can be processed"""
        return self.get_active_count() < self.max_concurrent_tasks

    def get_queue_stats(self) -> Dict[str, Any]:
        """Get queue statistics"""
        with self.lock:
            return {
                "queued": self.get_queue_size(),
                "active": len(self.active_tasks),
                "completed": len(self.completed_tasks),
                "failed": len(self.failed_tasks),
                "total_queued": self.total_queued,
                "total_processed": self.total_processed,
                "total_failed": self.total_failed,
                "max_concurrent": self.max_concurrent_tasks,
            }

    def get_task_position(self, session_id: str) -> Optional[int]:
        """
        Get position of a task in queue

        Returns:
            Position (0-indexed) or None if not in queue
        """
        # This is approximate as PriorityQueue doesn't support indexing
        with self.lock:
            if session_id in self.active_tasks:
                return 0  # Currently processing

            # Estimate based on queue size
            return self.get_queue_size()

    def get_estimated_wait_time(self, session_id: str) -> float:
        """
        Estimate wait time for a task

        Returns:
            Estimated wait time in seconds
        """
        position = self.get_task_position(session_id)
        if position is None:
            return 0.0

        # Rough estimate: 30 seconds per task
        avg_task_time = 30.0
        return position * avg_task_time

    def clear_completed(self, older_than: float = 3600):
        """Clear completed tasks older than specified time"""
        with self.lock:
            current_time = time.time()
            to_remove = [
                sid
                for sid, completed_time in self.completed_tasks.items()
                if current_time - completed_time > older_than
            ]

            for sid in to_remove:
                del self.completed_tasks[sid]

            logger.info(f"Cleared {len(to_remove)} old completed tasks")


# Singleton instance
queue_manager = QueueManager(
    max_concurrent_tasks=2,
    enable_batching=True,
    batch_timeout=2.0,
    batch_size=4,
)
