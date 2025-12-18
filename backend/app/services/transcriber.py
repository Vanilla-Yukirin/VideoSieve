"""
Audio transcription service using Faster-Whisper.
Optimized for CPU with int8 quantization.
"""
import asyncio
from typing import Callable, Optional
from faster_whisper import WhisperModel
from ..core.config import settings
from ..utils.logger import get_logger

logger = get_logger(__name__)

# Global model instance (singleton)
_model: Optional[WhisperModel] = None
_model_lock = asyncio.Lock()


async def get_whisper_model() -> WhisperModel:
    """
    Get or initialize the Whisper model.
    Uses singleton pattern to avoid loading multiple times.
    """
    global _model
    
    async with _model_lock:
        if _model is None:
            logger.info(f"Loading Whisper model: {settings.WHISPER_MODEL}")
            loop = asyncio.get_event_loop()
            
            def _load_model():
                return WhisperModel(
                    settings.WHISPER_MODEL,
                    device=settings.WHISPER_DEVICE,
                    compute_type=settings.WHISPER_COMPUTE_TYPE,
                    num_workers=2
                )
            
            _model = await loop.run_in_executor(None, _load_model)
            logger.info("Whisper model loaded successfully")
        
        return _model


async def transcribe_audio(
    audio_path: str,
    task_id: str,
    on_progress: Optional[Callable] = None
) -> str:
    """
    Transcribe audio file to text.
    
    Args:
        audio_path: Path to audio file
        task_id: Task ID for logging
        on_progress: Callback function(progress: int, message: str)
    
    Returns:
        Transcribed text in simplified Chinese
    """
    logger.info(f"[{task_id}] Starting transcription: {audio_path}")
    
    try:
        # Get model
        model = await get_whisper_model()
        
        if on_progress:
            await on_progress(0, "开始转录...")
        
        # Run transcription in executor
        loop = asyncio.get_event_loop()
        
        def _transcribe():
            segments, info = model.transcribe(
                audio_path,
                language="zh",  # Force Chinese
                beam_size=5,
                vad_filter=True,  # Voice activity detection
                vad_parameters=dict(min_silence_duration_ms=500)
            )
            
            # Collect all segments
            result_segments = []
            for segment in segments:
                result_segments.append({
                    'start': segment.start,
                    'end': segment.end,
                    'text': segment.text
                })
            
            return result_segments
        
        segments = await loop.run_in_executor(None, _transcribe)
        
        # Process segments with progress updates
        full_text = []
        total_segments = len(segments)
        
        for i, segment in enumerate(segments):
            full_text.append(segment['text'].strip())
            
            if on_progress and i % 10 == 0:  # Update every 10 segments
                progress = int((i + 1) / total_segments * 100)
                await on_progress(progress, f"转录进度: {i + 1}/{total_segments} 段")
        
        # Combine text
        transcript = " ".join(full_text)
        
        if on_progress:
            await on_progress(100, "转录完成")
        
        logger.info(f"[{task_id}] Transcription complete: {len(transcript)} characters")
        return transcript
        
    except Exception as e:
        logger.error(f"[{task_id}] Transcription failed: {str(e)}")
        raise Exception(f"转录失败: {str(e)}")
