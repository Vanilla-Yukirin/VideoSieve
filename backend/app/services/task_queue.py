"""
Task queue management with asyncio.
Handles task processing with Whisper single-threading and LLM concurrency.
"""
import asyncio
import os
from typing import Dict, Optional
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.task import Task
from ..core.database import AsyncSessionLocal
from ..utils.logger import get_logger
from .downloader import download_audio
from .transcriber import transcribe_audio
from .ai_processor import optimize_transcript, generate_summary

logger = get_logger(__name__)

# Global state
_transcription_lock = asyncio.Lock()  # Ensure single Whisper task
_task_processors: Dict[str, asyncio.Task] = {}  # Track running tasks
_task_updates: Dict[str, asyncio.Queue] = {}  # SSE update queues


def get_task_update_queue(task_id: str) -> asyncio.Queue:
    """Get or create update queue for a task."""
    if task_id not in _task_updates:
        _task_updates[task_id] = asyncio.Queue()
    return _task_updates[task_id]


def cleanup_task_queue(task_id: str):
    """Clean up task update queue."""
    if task_id in _task_updates:
        del _task_updates[task_id]


async def update_task(
    task_id: str,
    status: Optional[str] = None,
    progress: Optional[int] = None,
    log_message: Optional[str] = None,
    error_message: Optional[str] = None,
    **kwargs
):
    """
    Update task in database and notify SSE listeners.
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Task).where(Task.id == task_id)
        )
        task = result.scalar_one_or_none()
        
        if not task:
            return
        
        # Update fields
        if status:
            task.status = status
        if progress is not None:
            task.progress = progress
        if error_message:
            task.error_message = error_message
        
        # Update additional fields
        for key, value in kwargs.items():
            if hasattr(task, key):
                setattr(task, key, value)
        
        # Add log message
        if log_message:
            if task.logs is None:
                task.logs = []
            task.logs.append({
                "time": datetime.now().isoformat(),
                "message": log_message
            })
        
        await session.commit()
        
        # Notify SSE listeners
        if task_id in _task_updates:
            try:
                await _task_updates[task_id].put({
                    "task_id": task_id,
                    "status": task.status,
                    "progress": task.progress,
                    "logs": task.logs[-5:] if task.logs else [],  # Last 5 logs
                    "error_message": task.error_message
                })
            except:
                pass


async def process_task(task_id: str):
    """
    Process a single task through all stages.
    """
    logger.info(f"[{task_id}] Starting task processing")
    
    try:
        # Get task
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Task).where(Task.id == task_id)
            )
            task = result.scalar_one_or_none()
            
            if not task:
                logger.error(f"[{task_id}] Task not found")
                return
            
            video_url = task.video_url
        
        # Stage 1: Download audio
        await update_task(task_id, status="downloading", progress=0, log_message="开始下载音频...")
        
        async def download_progress(progress: int, message: str):
            await update_task(task_id, progress=progress, log_message=message)
        
        audio_path = await download_audio(video_url, task_id, download_progress)
        await update_task(
            task_id,
            status="downloading",
            progress=100,
            log_message="音频下载完成",
            audio_path=audio_path
        )
        
        # Stage 2: Transcribe (single-threaded)
        await update_task(task_id, status="transcribing", progress=0, log_message="等待转录...")
        
        async with _transcription_lock:
            logger.info(f"[{task_id}] Acquired transcription lock")
            await update_task(task_id, log_message="开始转录音频...")
            
            async def transcribe_progress(progress: int, message: str):
                await update_task(task_id, progress=progress, log_message=message)
            
            transcript = await transcribe_audio(audio_path, task_id, transcribe_progress)
            await update_task(
                task_id,
                status="transcribing",
                progress=100,
                log_message="转录完成",
                transcript=transcript
            )
        
        # Stage 3: AI Processing (concurrent)
        await update_task(task_id, status="processing", progress=0, log_message="开始AI处理...")
        
        # Run optimization and summarization concurrently
        await update_task(task_id, progress=30, log_message="优化转录文本...")
        optimized_task = optimize_transcript(transcript, task_id)
        
        await update_task(task_id, progress=60, log_message="生成摘要...")
        summary_task = generate_summary(transcript, task_id)
        
        # Wait for both
        optimized_text, summary = await asyncio.gather(optimized_task, summary_task)
        
        await update_task(
            task_id,
            status="completed",
            progress=100,
            log_message="处理完成！",
            optimized_text=optimized_text,
            summary=summary
        )
        
        logger.info(f"[{task_id}] Task completed successfully")
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"[{task_id}] Task failed: {error_msg}")
        await update_task(
            task_id,
            status="failed",
            error_message=error_msg,
            log_message=f"处理失败: {error_msg}"
        )
    
    finally:
        # Cleanup
        if task_id in _task_processors:
            del _task_processors[task_id]


async def enqueue_task(task_id: str):
    """
    Enqueue a task for processing.
    """
    if task_id in _task_processors:
        logger.warning(f"[{task_id}] Task already processing")
        return
    
    # Create async task
    task = asyncio.create_task(process_task(task_id))
    _task_processors[task_id] = task
    
    logger.info(f"[{task_id}] Task enqueued")


def is_task_processing(task_id: str) -> bool:
    """Check if a task is currently processing."""
    return task_id in _task_processors
