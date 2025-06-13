from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime

class TaskResponse(BaseModel):
    """Response model for task information"""
    id: str
    type: str
    status: str
    created_at: datetime
    updated_at: datetime
    metadata: Dict[str, Any] = Field(default_factory=dict)
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

class TaskListResponse(BaseModel):
    """Response model for listing tasks"""
    tasks: Dict[str, TaskResponse]
    total: int

class TaskStatusResponse(BaseModel):
    """Response model for task status"""
    status: str
    progress: Optional[float] = None
    message: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None 