"""
用于实时任务更新的 Server-Sent Events (SSE) 端点。
"""
import asyncio
import json
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..core.database import get_db
from ..models.task import Task
from ..services.task_queue import get_task_update_queue, cleanup_task_queue
from ..utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


async def task_event_generator(task_id: str):
    """
    为任务更新生成 SSE 事件。
    """
    logger.info(f"[{task_id}] SSE 连接已建立")
    
    # 获取初始任务状态
    async with AsyncSession(bind=None) as session:
        from ..core.database import engine
        async with AsyncSession(engine) as session:
            result = await session.execute(
                select(Task).where(Task.id == task_id)
            )
            task = result.scalar_one_or_none()
            
            if not task:
                logger.warning(f"[{task_id}] SSE 未找到任务")
                return
            
            # 发送初始状态
            initial_data = {
                "task_id": task.id,
                "status": task.status,
                "progress": task.progress,
                "logs": task.logs[-5:] if task.logs else [],
                "error_message": task.error_message
            }
            yield f"data: {json.dumps(initial_data)}\n\n"
    
    # 获取更新队列
    queue = get_task_update_queue(task_id)
    
    try:
        # 流式传输更新
        while True:
            try:
                # 等待更新，超时用于心跳
                update = await asyncio.wait_for(queue.get(), timeout=30.0)
                
                # 发送更新
                yield f"data: {json.dumps(update)}\n\n"
                
                # 如果任务完成或失败则停止
                if update.get("status") in ["completed", "failed"]:
                    logger.info(f"[{task_id}] 任务结束，关闭 SSE")
                    break
                    
            except asyncio.TimeoutError:
                # 发送心跳
                yield f": heartbeat\n\n"
                
    except GeneratorExit:
        logger.info(f"[{task_id}] 客户端关闭 SSE 连接")
    except Exception as e:
        logger.error(f"[{task_id}] SSE 错误: {str(e)}")
    finally:
        cleanup_task_queue(task_id)


@router.get("/{task_id}/stream")
async def stream_task_progress(task_id: str, db: AsyncSession = Depends(get_db)):
    """
    通过 SSE 流式传输实时任务进度更新。
    """
    # 验证任务是否存在
    result = await db.execute(
        select(Task).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail=f"未找到任务 {task_id}")
    
    return StreamingResponse(
        task_event_generator(task_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # 禁用 nginx 缓冲
        }
    )
