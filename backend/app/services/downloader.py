"""
Video download service using yt-dlp.
Supports 30+ platforms including YouTube, Bilibili, TikTok, etc.
"""
import os
import asyncio
from pathlib import Path
from typing import Callable, Optional
import yt_dlp
from ..core.config import settings
from ..utils.logger import get_logger

logger = get_logger(__name__)


class DownloadProgress:
    """Track download progress."""
    
    def __init__(self, on_progress: Optional[Callable] = None):
        self.on_progress = on_progress
    
    def __call__(self, d: dict):
        """Called by yt-dlp with progress info."""
        if d['status'] == 'downloading':
            try:
                percent = d.get('_percent_str', '0%').strip('%')
                progress = float(percent)
                if self.on_progress:
                    asyncio.create_task(
                        self.on_progress(int(progress), f"下载中: {percent}%")
                    )
            except:
                pass
        elif d['status'] == 'finished':
            if self.on_progress:
                asyncio.create_task(
                    self.on_progress(100, "下载完成")
                )


async def download_audio(
    url: str,
    task_id: str,
    on_progress: Optional[Callable] = None
) -> str:
    """
    Download audio from video URL.
    
    Args:
        url: Video URL
        task_id: Task ID for filename
        on_progress: Callback function(progress: int, message: str)
    
    Returns:
        Path to downloaded audio file
    """
    logger.info(f"[{task_id}] Starting download: {url}")
    
    # Ensure output directory exists
    output_dir = Path(settings.AUDIO_OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Output template
    output_template = str(output_dir / f"{task_id}.%(ext)s")
    
    # yt-dlp options
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': output_template,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'quiet': True,
        'no_warnings': True,
        'progress_hooks': [DownloadProgress(on_progress)],
    }
    
    try:
        # Run in executor to avoid blocking
        loop = asyncio.get_event_loop()
        
        def _download():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
        
        await loop.run_in_executor(None, _download)
        
        # Find the downloaded file
        audio_path = output_dir / f"{task_id}.mp3"
        
        if not audio_path.exists():
            # Try other extensions
            for ext in ['m4a', 'webm', 'opus']:
                alt_path = output_dir / f"{task_id}.{ext}"
                if alt_path.exists():
                    audio_path = alt_path
                    break
        
        if not audio_path.exists():
            raise FileNotFoundError("Audio file not found after download")
        
        logger.info(f"[{task_id}] Download complete: {audio_path}")
        return str(audio_path)
        
    except Exception as e:
        logger.error(f"[{task_id}] Download failed: {str(e)}")
        raise Exception(f"下载失败: {str(e)}")
