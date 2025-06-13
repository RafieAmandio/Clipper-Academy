from typing import Dict, Any, Optional
import asyncio
import uuid
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class TaskStatus:
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class TaskManager:
    def __init__(self):
        self._tasks: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
    
    async def create_task(self, task_type: str, metadata: Dict[str, Any] = None) -> str:
        """Create a new task and return its ID"""
        task_id = str(uuid.uuid4())
        async with self._lock:
            self._tasks[task_id] = {
                "id": task_id,
                "type": task_type,
                "status": TaskStatus.PENDING,
                "created_at": datetime.now(),
                "updated_at": datetime.now(),
                "metadata": metadata or {},
                "result": None,
                "error": None
            }
        logger.info(f"Created task {task_id} of type {task_type}")
        return task_id
    
    async def update_task(self, task_id: str, status: str, result: Any = None, error: str = None) -> None:
        """Update task status and result"""
        async with self._lock:
            if task_id not in self._tasks:
                raise KeyError(f"Task {task_id} not found")
            
            self._tasks[task_id].update({
                "status": status,
                "updated_at": datetime.now(),
                "result": result,
                "error": error
            })
            logger.info(f"Updated task {task_id} to status {status}")
    
    async def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get task information"""
        return self._tasks.get(task_id)
    
    async def list_tasks(self, task_type: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        """List all tasks, optionally filtered by type"""
        if task_type:
            return {k: v for k, v in self._tasks.items() if v["type"] == task_type}
        return self._tasks

# Global task manager instance
task_manager = TaskManager() 