"""
使用 asyncio 的任务队列管理。
处理 Whisper 单线程和 LLM 并发的任务处理。
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

# 全局状态
_transcription_lock = asyncio.Lock()  # 确保单个 Whisper 任务
_task_processors: Dict[str, asyncio.Task] = {}  # 跟踪运行中的任务
_task_updates: Dict[str, asyncio.Queue] = {}  # SSE 更新队列


def get_task_update_queue(task_id: str) -> asyncio.Queue:
    """获取或创建任务的更新队列。"""
    if task_id not in _task_updates:
        _task_updates[task_id] = asyncio.Queue()
    return _task_updates[task_id]


def cleanup_task_queue(task_id: str):
    """清理任务更新队列。"""
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
    在数据库中更新任务并通知 SSE 监听器。
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Task).where(Task.id == task_id)
        )
        task = result.scalar_one_or_none()
        
        if not task:
            return
        
        # 更新字段
        if status:
            task.status = status
        if progress is not None:
            task.progress = progress
        if error_message:
            task.error_message = error_message
        
        # 更新附加字段
        for key, value in kwargs.items():
            if hasattr(task, key):
                setattr(task, key, value)
        
        # 添加日志消息
        if log_message:
            if task.logs is None:
                task.logs = []
            task.logs.append({
                "time": datetime.now().isoformat(),
                "message": log_message
            })
        
        await session.commit()
        
        # 通知 SSE 监听器
        if task_id in _task_updates:
            try:
                await _task_updates[task_id].put({
                    "task_id": task_id,
                    "status": task.status,
                    "progress": task.progress,
                    "logs": task.logs[-5:] if task.logs else [],  # 最近 5 条日志
                    "error_message": task.error_message
                })
            except Exception:
                pass


async def process_task(task_id: str):
    """
    通过所有阶段处理单个任务。
    """
    logger.info(f"[{task_id}] 开始任务处理")
    
    try:
        # 获取任务
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Task).where(Task.id == task_id)
            )
            task = result.scalar_one_or_none()
            
            if not task:
                logger.error(f"[{task_id}] 未找到任务")
                return
            
            video_url = task.video_url
        
        # 阶段 1: 下载音频
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
        
        # 阶段 2: 转录（单线程）
        await update_task(task_id, status="transcribing", progress=0, log_message="等待转录...")
        
        async with _transcription_lock:
            logger.info(f"[{task_id}] 获得转录锁")
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
        
        # 阶段 3: AI 处理（并发）
        await update_task(task_id, status="processing", progress=0, log_message="开始AI处理...")
        
        # 并发运行优化和摘要
        await update_task(task_id, progress=30, log_message="优化转录文本...")
        optimized_task = optimize_transcript(transcript, task_id)
        
        await update_task(task_id, progress=60, log_message="生成摘要...")
        summary_task = generate_summary(transcript, task_id)
        
        # 等待两者完成
        optimized_text, summary = await asyncio.gather(optimized_task, summary_task)
        
        await update_task(
            task_id,
            status="completed",
            progress=100,
            log_message="处理完成！",
            optimized_text=optimized_text,
            summary=summary
        )
        
        logger.info(f"[{task_id}] 任务成功完成")
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"[{task_id}] 任务失败: {error_msg}")
        await update_task(
            task_id,
            status="failed",
            error_message=error_msg,
            log_message=f"处理失败: {error_msg}"
        )
    
    finally:
        # 清理
        if task_id in _task_processors:
            del _task_processors[task_id]


async def enqueue_task(task_id: str):
    """
    将任务加入处理队列。
    """
    if task_id in _task_processors:
        logger.warning(f"[{task_id}] 任务已在处理中")
        return
    
    # 创建异步任务
    task = asyncio.create_task(process_task(task_id))
    _task_processors[task_id] = task
    
    logger.info(f"[{task_id}] 任务已加入队列")


def is_task_processing(task_id: str) -> bool:
    """检查任务是否正在处理中。"""
    return task_id in _task_processors
