"""
AI processing service using OpenAI-compatible APIs.
Handles text optimization, summarization, and translation.
"""
import asyncio
from typing import Optional
from openai import AsyncOpenAI
from ..core.config import settings
from ..utils.logger import get_logger

logger = get_logger(__name__)

# Global OpenAI client
client = AsyncOpenAI(
    api_key=settings.OPENAI_API_KEY,
    base_url=settings.OPENAI_BASE_URL
)


async def optimize_transcript(text: str, task_id: str) -> str:
    """
    Optimize transcribed text: fix grammar, punctuation, and formatting.
    
    Args:
        text: Raw transcript text
        task_id: Task ID for logging
    
    Returns:
        Optimized text in simplified Chinese
    """
    logger.info(f"[{task_id}] Starting text optimization")
    
    prompt = f"""你是一个专业的文本编辑助手。请优化以下视频转录文本：

1. 修正语法错误和口语化表达
2. 添加适当的标点符号
3. 合理分段，提高可读性
4. 保持原意不变
5. **必须使用简体中文输出**

转录文本：
{text}

请直接输出优化后的文本，不要添加任何解释或说明。"""

    try:
        response = await client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "你是一个专业的中文文本编辑助手，擅长优化转录文本。必须使用简体中文输出。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=4096
        )
        
        optimized = response.choices[0].message.content.strip()
        logger.info(f"[{task_id}] Text optimization complete")
        return optimized
        
    except Exception as e:
        logger.error(f"[{task_id}] Text optimization failed: {str(e)}")
        raise Exception(f"文本优化失败: {str(e)}")


async def generate_summary(text: str, task_id: str) -> str:
    """
    Generate a concise summary of the text.
    
    Args:
        text: Text to summarize
        task_id: Task ID for logging
    
    Returns:
        Summary in simplified Chinese (200-300 characters)
    """
    logger.info(f"[{task_id}] Starting summary generation")
    
    prompt = f"""请为以下文本生成一个简洁的摘要：

要求：
1. 提取核心内容和关键信息
2. 200-300字左右
3. 保持客观准确
4. **必须使用简体中文输出**

文本：
{text}

请直接输出摘要，不要添加任何解释或说明。"""

    try:
        response = await client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "你是一个专业的内容摘要助手。必须使用简体中文输出。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.5,
            max_tokens=500
        )
        
        summary = response.choices[0].message.content.strip()
        logger.info(f"[{task_id}] Summary generation complete")
        return summary
        
    except Exception as e:
        logger.error(f"[{task_id}] Summary generation failed: {str(e)}")
        raise Exception(f"摘要生成失败: {str(e)}")


async def translate_text(text: str, target_lang: str, task_id: str) -> str:
    """
    Translate text to target language.
    
    Args:
        text: Text to translate
        target_lang: Target language (e.g., "English", "Japanese")
        task_id: Task ID for logging
    
    Returns:
        Translated text
    """
    logger.info(f"[{task_id}] Starting translation to {target_lang}")
    
    prompt = f"""请将以下文本翻译成{target_lang}：

{text}

请直接输出翻译结果，不要添加任何解释或说明。"""

    try:
        response = await client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": f"你是一个专业的翻译助手，擅长将中文翻译成{target_lang}。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=4096
        )
        
        translated = response.choices[0].message.content.strip()
        logger.info(f"[{task_id}] Translation complete")
        return translated
        
    except Exception as e:
        logger.error(f"[{task_id}] Translation failed: {str(e)}")
        raise Exception(f"翻译失败: {str(e)}")
