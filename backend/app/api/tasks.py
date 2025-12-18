"""
任务管理的 REST API 端点。
"""
import os
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from datetime import datetime

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
    创建新的视频处理任务。
    """
    logger.info(f"为 URL 创建任务: {task_data.video_url}")
    
    # 创建任务
    task = Task(
        video_url=task_data.video_url,
        status="pending",
        progress=0,
        logs=[{
            "time": datetime.now().isoformat(),
            "message": "任务已创建"
        }]
    )
    
    db.add(task)
    await db.commit()
    await db.refresh(task)
    
    # 加入处理队列
    await enqueue_task(task.id)
    
    logger.info(f"任务已创建: {task.id}")
    return task


@router.get("/", response_model=TaskListResponse)
async def list_tasks(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """
    获取所有任务的列表。
    """
    # 获取总数
    count_result = await db.execute(select(Task))
    total = len(count_result.scalars().all())
    
    # 获取分页任务
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
    通过 ID 获取特定任务。
    """
    result = await db.execute(
        select(Task).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"未找到任务 {task_id}"
        )
    
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    删除任务及其关联的音频文件。
    """
    result = await db.execute(
        select(Task).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"未找到任务 {task_id}"
        )
    
    # 删除音频文件（如果存在）
    if task.audio_path and os.path.exists(task.audio_path):
        try:
            os.remove(task.audio_path)
            logger.info(f"已删除音频文件: {task.audio_path}")
        except Exception as e:
            logger.warning(f"删除音频文件失败: {e}")
    
    # 从数据库中删除
    await db.delete(task)
    await db.commit()
    
    logger.info(f"任务已删除: {task_id}")


@router.get("/{task_id}/transcript")
async def get_transcript(
    task_id: str,
    db: AsyncSession = Depends(get_db)
):
    """获取任务转录。"""
    result = await db.execute(
        select(Task).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"未找到任务 {task_id}"
        )
    
    if not task.transcript:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="转录尚未可用"
        )
    
    return {"transcript": task.transcript}


@router.get("/{task_id}/optimized")
async def get_optimized(
    task_id: str,
    db: AsyncSession = Depends(get_db)
):
    """获取优化文本。"""
    result = await db.execute(
        select(Task).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"未找到任务 {task_id}"
        )
    
    if not task.optimized_text:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="优化文本尚未可用"
        )
    
    return {"optimized_text": task.optimized_text}


@router.get("/{task_id}/summary")
async def get_summary(
    task_id: str,
    db: AsyncSession = Depends(get_db)
):
    """获取任务摘要。"""
    result = await db.execute(
        select(Task).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"未找到任务 {task_id}"
        )
    
    if not task.summary:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="摘要尚未可用"
        )
    
    return {"summary": task.summary}
