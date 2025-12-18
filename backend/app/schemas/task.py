"""
Pydantic schemas for Task API validation and serialization.
"""
from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, List
from datetime import datetime


class TaskCreate(BaseModel):
    """Schema for creating a new task."""
    video_url: str = Field(..., description="Video URL to process", min_length=1)


class TaskUpdate(BaseModel):
    """Schema for updating task fields."""
    status: Optional[str] = None
    progress: Optional[int] = Field(None, ge=0, le=100)
    error_message: Optional[str] = None
    audio_path: Optional[str] = None
    transcript: Optional[str] = None
    optimized_text: Optional[str] = None
    summary: Optional[str] = None
    logs: Optional[List[str]] = None


class TaskResponse(BaseModel):
    """Schema for task response."""
    id: str
    video_url: str
    status: str
    progress: int
    error_message: Optional[str] = None
    audio_path: Optional[str] = None
    transcript: Optional[str] = None
    optimized_text: Optional[str] = None
    summary: Optional[str] = None
    logs: List[str] = []
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class TaskListResponse(BaseModel):
    """Schema for listing tasks."""
    tasks: List[TaskResponse]
    total: int


class TaskStreamEvent(BaseModel):
    """Schema for SSE events."""
    task_id: str
    status: str
    progress: int
    logs: List[str]  # Last 5 logs
    error_message: Optional[str] = None
