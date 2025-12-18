"""
使用 OpenAI 兼容 API 的 AI 处理服务。
处理文本优化、摘要生成和翻译。
"""
import asyncio
from typing import Optional
from openai import AsyncOpenAI
from ..core.config import settings
from ..utils.logger import get_logger

logger = get_logger(__name__)

# 全局 OpenAI 客户端
client = AsyncOpenAI(
    api_key=settings.OPENAI_API_KEY,
    base_url=settings.OPENAI_BASE_URL
)


async def optimize_transcript(text: str, task_id: str) -> str:
    """
    优化转录文本：修正语法、标点和格式。
    
    参数:
        text: 原始转录文本
        task_id: 任务 ID，用于日志记录
    
    返回:
        简体中文优化文本
    """
    logger.info(f"[{task_id}] 开始文本优化")
    
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
        logger.info(f"[{task_id}] 文本优化完成")
        return optimized
        
    except Exception as e:
        logger.error(f"[{task_id}] 文本优化失败: {str(e)}")
        raise Exception(f"文本优化失败: {str(e)}")


async def generate_summary(text: str, task_id: str) -> str:
    """
    生成文本的简洁摘要。
    
    参数:
        text: 要摘要的文本
        task_id: 任务 ID，用于日志记录
    
    返回:
        简体中文摘要（200-300 字）
    """
    logger.info(f"[{task_id}] 开始生成摘要")
    
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
        logger.info(f"[{task_id}] 摘要生成完成")
        return summary
        
    except Exception as e:
        logger.error(f"[{task_id}] 摘要生成失败: {str(e)}")
        raise Exception(f"摘要生成失败: {str(e)}")


async def translate_text(text: str, target_lang: str, task_id: str) -> str:
    """
    将文本翻译成目标语言。
    
    参数:
        text: 要翻译的文本
        target_lang: 目标语言（例如 "英语"、"日语"）
        task_id: 任务 ID，用于日志记录
    
    返回:
        翻译后的文本
    """
    logger.info(f"[{task_id}] 开始翻译为 {target_lang}")
    
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
        logger.info(f"[{task_id}] 翻译完成")
        return translated
        
    except Exception as e:
        logger.error(f"[{task_id}] 翻译失败: {str(e)}")
        raise Exception(f"翻译失败: {str(e)}")
