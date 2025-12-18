"""
任务数据库模型。
表示一个视频处理任务及其所有状态和数据。
"""
from sqlalchemy import Column, String, Integer, Text, DateTime, JSON
from sqlalchemy.sql import func
from ..core.database import Base
import uuid


class Task(Base):
    """用于存储视频处理任务的任务模型。"""
    
    __tablename__ = "tasks"
    
    # 主键
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # 任务数据
    video_url = Column(String(500), nullable=False, index=True)
    status = Column(
        String(20),
        nullable=False,
        default="pending",
        index=True
    )  # pending, downloading, transcribing, processing, completed, failed
    
    progress = Column(Integer, default=0)  # 0-100
    error_message = Column(Text, nullable=True)
    
    # 文件路径和处理结果
    audio_path = Column(String(500), nullable=True)
    transcript = Column(Text, nullable=True)
    optimized_text = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    
    # 日志（存储为 JSON 数组）
    logs = Column(JSON, default=list)
    
    # 时间戳
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    def __repr__(self):
        return f"<Task(id={self.id}, status={self.status}, progress={self.progress})>"
