"""
使用 Faster-Whisper 的音频转录服务。
针对 CPU 进行了 int8 量化优化。
"""
import asyncio
from typing import Callable, Optional
from faster_whisper import WhisperModel
from ..core.config import settings
from ..utils.logger import get_logger

logger = get_logger(__name__)

# 全局模型实例（单例）
_model: Optional[WhisperModel] = None
_model_lock = asyncio.Lock()


async def get_whisper_model() -> WhisperModel:
    """
    获取或初始化 Whisper 模型。
    使用单例模式避免多次加载。
    """
    global _model
    
    async with _model_lock:
        if _model is None:
            logger.info(f"加载 Whisper 模型: {settings.WHISPER_MODEL}")
            loop = asyncio.get_event_loop()
            
            def _load_model():
                return WhisperModel(
                    settings.WHISPER_MODEL,
                    device=settings.WHISPER_DEVICE,
                    compute_type=settings.WHISPER_COMPUTE_TYPE,
                    num_workers=2
                )
            
            _model = await loop.run_in_executor(None, _load_model)
            logger.info("Whisper 模型加载成功")
        
        return _model


async def transcribe_audio(
    audio_path: str,
    task_id: str,
    on_progress: Optional[Callable] = None
) -> str:
    """
    将音频文件转录为文本。
    
    参数:
        audio_path: 音频文件路径
        task_id: 任务 ID，用于日志记录
        on_progress: 回调函数(progress: int, message: str)
    
    返回:
        简体中文转录文本
    """
    logger.info(f"[{task_id}] 开始转录: {audio_path}")
    
    try:
        # 获取模型
        model = await get_whisper_model()
        
        if on_progress:
            await on_progress(0, "开始转录...")
        
        # 在执行器中运行转录
        loop = asyncio.get_event_loop()
        
        def _transcribe():
            segments, info = model.transcribe(
                audio_path,
                language="zh",  # 强制中文
                beam_size=5,
                vad_filter=True,  # 语音活动检测
                vad_parameters=dict(min_silence_duration_ms=500)
            )
            
            # 收集所有片段
            result_segments = []
            for segment in segments:
                result_segments.append({
                    'start': segment.start,
                    'end': segment.end,
                    'text': segment.text
                })
            
            return result_segments
        
        segments = await loop.run_in_executor(None, _transcribe)
        
        # 处理片段并更新进度
        full_text = []
        total_segments = len(segments)
        
        for i, segment in enumerate(segments):
            full_text.append(segment['text'].strip())
            
            if on_progress and i % 10 == 0:  # 每 10 个片段更新一次
                progress = int((i + 1) / total_segments * 100)
                await on_progress(progress, f"转录进度: {i + 1}/{total_segments} 段")
        
        # 合并文本
        transcript = " ".join(full_text)
        
        if on_progress:
            await on_progress(100, "转录完成")
        
        logger.info(f"[{task_id}] 转录完成: {len(transcript)} 字符")
        return transcript
        
    except Exception as e:
        logger.error(f"[{task_id}] 转录失败: {str(e)}")
        raise Exception(f"转录失败: {str(e)}")
