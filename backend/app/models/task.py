"""
Task database model.
Represents a video processing task with all its states and data.
"""
from sqlalchemy import Column, String, Integer, Text, DateTime, JSON
from sqlalchemy.sql import func
from ..core.database import Base
import uuid


class Task(Base):
    """Task model for storing video processing tasks."""
    
    __tablename__ = "tasks"
    
    # Primary key
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Task data
    video_url = Column(String(500), nullable=False, index=True)
    status = Column(
        String(20),
        nullable=False,
        default="pending",
        index=True
    )  # pending, downloading, transcribing, processing, completed, failed
    
    progress = Column(Integer, default=0)  # 0-100
    error_message = Column(Text, nullable=True)
    
    # File paths and processing results
    audio_path = Column(String(500), nullable=True)
    transcript = Column(Text, nullable=True)
    optimized_text = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    
    # Logs (stored as JSON array)
    logs = Column(JSON, default=list)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    def __repr__(self):
        return f"<Task(id={self.id}, status={self.status}, progress={self.progress})>"
