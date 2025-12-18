"""
Task API 验证和序列化的 Pydantic 模式。
"""
from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, List
from datetime import datetime


class TaskCreate(BaseModel):
    """创建新任务的模式。"""
    video_url: str = Field(..., description="要处理的视频URL", min_length=1)


class TaskUpdate(BaseModel):
    """更新任务字段的模式。"""
    status: Optional[str] = None
    progress: Optional[int] = Field(None, ge=0, le=100)
    error_message: Optional[str] = None
    audio_path: Optional[str] = None
    transcript: Optional[str] = None
    optimized_text: Optional[str] = None
    summary: Optional[str] = None
    logs: Optional[List[str]] = None


class TaskResponse(BaseModel):
    """任务响应的模式。"""
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
    """任务列表的模式。"""
    tasks: List[TaskResponse]
    total: int


class TaskStreamEvent(BaseModel):
    """SSE 事件的模式。"""
    task_id: str
    status: str
    progress: int
    logs: List[str]  # 最近 5 条日志
    error_message: Optional[str] = None
