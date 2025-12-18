"""
使用 yt-dlp 的视频下载服务。
支持 30+ 平台，包括 YouTube、Bilibili、TikTok 等。
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
    """跟踪下载进度。"""
    
    def __init__(self, on_progress: Optional[Callable] = None):
        self.on_progress = on_progress
    
    def __call__(self, d: dict):
        """由 yt-dlp 调用，提供进度信息。"""
        if d['status'] == 'downloading':
            try:
                percent = d.get('_percent_str', '0%').strip('%')
                progress = float(percent)
                if self.on_progress:
                    asyncio.create_task(
                        self.on_progress(int(progress), f"下载中: {percent}%")
                    )
            except Exception:
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
    从视频 URL 下载音频。
    
    参数:
        url: 视频 URL
        task_id: 任务 ID，用于文件名
        on_progress: 回调函数(progress: int, message: str)
    
    返回:
        下载的音频文件路径
    """
    logger.info(f"[{task_id}] 开始下载: {url}")
    
    # 确保输出目录存在
    output_dir = Path(settings.AUDIO_OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 输出模板
    output_template = str(output_dir / f"{task_id}.%(ext)s")
    
    # yt-dlp 选项
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
        # 在执行器中运行以避免阻塞
        loop = asyncio.get_event_loop()
        
        def _download():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
        
        await loop.run_in_executor(None, _download)
        
        # 查找下载的文件
        audio_path = output_dir / f"{task_id}.mp3"
        
        if not audio_path.exists():
            # 尝试其他扩展名
            for ext in ['m4a', 'webm', 'opus']:
                alt_path = output_dir / f"{task_id}.{ext}"
                if alt_path.exists():
                    audio_path = alt_path
                    break
        
        if not audio_path.exists():
            raise FileNotFoundError("下载后未找到音频文件")
        
        logger.info(f"[{task_id}] 下载完成: {audio_path}")
        return str(audio_path)
        
    except Exception as e:
        logger.error(f"[{task_id}] 下载失败: {str(e)}")
        raise Exception(f"下载失败: {str(e)}")
