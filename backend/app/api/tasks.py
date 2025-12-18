"""
REST API endpoints for task management.
"""
import os
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from ..core.database import get_db
from ..models.task import Task
from ..schemas.task import TaskCreate, TaskResponse, TaskListResponse
from ..services.task_queue import enqueue_task
from ..utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.post("/", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    task_data: TaskCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new video processing task.
    """
    logger.info(f"Creating task for URL: {task_data.video_url}")
    
    # Create task
    task = Task(
        video_url=task_data.video_url,
        status="pending",
        progress=0,
        logs=[{
            "time": str(Task.created_at),
            "message": "任务已创建"
        }]
    )
    
    db.add(task)
    await db.commit()
    await db.refresh(task)
    
    # Enqueue for processing
    await enqueue_task(task.id)
    
    logger.info(f"Task created: {task.id}")
    return task


@router.get("/", response_model=TaskListResponse)
async def list_tasks(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """
    Get list of all tasks.
    """
    # Get total count
    count_result = await db.execute(select(Task))
    total = len(count_result.scalars().all())
    
    # Get paginated tasks
    result = await db.execute(
        select(Task)
        .order_by(desc(Task.created_at))
        .offset(skip)
        .limit(limit)
    )
    tasks = result.scalars().all()
    
    return TaskListResponse(tasks=tasks, total=total)


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Get a specific task by ID.
    """
    result = await db.execute(
        select(Task).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} not found"
        )
    
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Delete a task and its associated audio file.
    """
    result = await db.execute(
        select(Task).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} not found"
        )
    
    # Delete audio file if exists
    if task.audio_path and os.path.exists(task.audio_path):
        try:
            os.remove(task.audio_path)
            logger.info(f"Deleted audio file: {task.audio_path}")
        except Exception as e:
            logger.warning(f"Failed to delete audio file: {e}")
    
    # Delete from database
    await db.delete(task)
    await db.commit()
    
    logger.info(f"Task deleted: {task_id}")


@router.get("/{task_id}/transcript")
async def get_transcript(
    task_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get task transcript."""
    result = await db.execute(
        select(Task).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} not found"
        )
    
    if not task.transcript:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transcript not yet available"
        )
    
    return {"transcript": task.transcript}


@router.get("/{task_id}/optimized")
async def get_optimized(
    task_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get optimized text."""
    result = await db.execute(
        select(Task).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} not found"
        )
    
    if not task.optimized_text:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Optimized text not yet available"
        )
    
    return {"optimized_text": task.optimized_text}


@router.get("/{task_id}/summary")
async def get_summary(
    task_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get task summary."""
    result = await db.execute(
        select(Task).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} not found"
        )
    
    if not task.summary:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Summary not yet available"
        )
    
    return {"summary": task.summary}
