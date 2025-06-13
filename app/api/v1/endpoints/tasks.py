from fastapi import APIRouter, HTTPException, Depends
from typing import Optional
import logging

from app.services.task_manager import task_manager, TaskStatus
from app.models.tasks import TaskResponse, TaskListResponse, TaskStatusResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["tasks"])

@router.get("/{task_id}", response_model=TaskResponse)
async def get_task_status(task_id: str):
    """
    Get the status of a specific task
    
    Returns detailed information about the task including its current status,
    progress, and result (if completed).
    """
    task = await task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return TaskResponse(**task)

@router.get("/", response_model=TaskListResponse)
async def list_tasks(task_type: Optional[str] = None):
    """
    List all tasks, optionally filtered by type
    
    Returns a list of all tasks in the system, with optional filtering
    by task type.
    """
    tasks = await task_manager.list_tasks(task_type)
    return TaskListResponse(
        tasks={k: TaskResponse(**v) for k, v in tasks.items()},
        total=len(tasks)
    ) 