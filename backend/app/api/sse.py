"""
Server-Sent Events (SSE) endpoints for real-time task updates.
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
    Generate SSE events for task updates.
    """
    logger.info(f"[{task_id}] SSE connection established")
    
    # Get initial task state
    async with AsyncSession(bind=None) as session:
        from ..core.database import engine
        async with AsyncSession(engine) as session:
            result = await session.execute(
                select(Task).where(Task.id == task_id)
            )
            task = result.scalar_one_or_none()
            
            if not task:
                logger.warning(f"[{task_id}] Task not found for SSE")
                return
            
            # Send initial state
            initial_data = {
                "task_id": task.id,
                "status": task.status,
                "progress": task.progress,
                "logs": task.logs[-5:] if task.logs else [],
                "error_message": task.error_message
            }
            yield f"data: {json.dumps(initial_data)}\n\n"
    
    # Get update queue
    queue = get_task_update_queue(task_id)
    
    try:
        # Stream updates
        while True:
            try:
                # Wait for update with timeout (for heartbeat)
                update = await asyncio.wait_for(queue.get(), timeout=30.0)
                
                # Send update
                yield f"data: {json.dumps(update)}\n\n"
                
                # Stop if task completed or failed
                if update.get("status") in ["completed", "failed"]:
                    logger.info(f"[{task_id}] Task finished, closing SSE")
                    break
                    
            except asyncio.TimeoutError:
                # Send heartbeat
                yield f": heartbeat\n\n"
                
    except GeneratorExit:
        logger.info(f"[{task_id}] SSE connection closed by client")
    except Exception as e:
        logger.error(f"[{task_id}] SSE error: {str(e)}")
    finally:
        cleanup_task_queue(task_id)


@router.get("/{task_id}/stream")
async def stream_task_progress(task_id: str, db: AsyncSession = Depends(get_db)):
    """
    Stream real-time task progress updates via SSE.
    """
    # Verify task exists
    result = await db.execute(
        select(Task).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    
    return StreamingResponse(
        task_event_generator(task_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )
