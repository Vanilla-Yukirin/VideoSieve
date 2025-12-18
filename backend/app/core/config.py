"""
配置管理使用 Pydantic Settings。
加载环境变量并提供类型安全的配置。
"""
from pydantic_settings import BaseSettings
from typing import List
import os


class Settings(BaseSettings):
    """应用程序设置，从环境变量加载。"""
    
    # OpenAI API 配置
    OPENAI_API_KEY: str
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_MODEL: str = "gpt-4o-mini"
    
    # 数据库配置
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/db/videosieve.db"
    
    # Whisper 配置
    WHISPER_MODEL: str = "base"  # tiny, base, small, medium, large
    WHISPER_DEVICE: str = "cpu"
    WHISPER_COMPUTE_TYPE: str = "int8"
    
    # 任务队列配置
    MAX_CONCURRENT_TASKS: int = 5
    
    # 文件存储配置
    AUDIO_OUTPUT_DIR: str = "./data/audio"
    
    # CORS 配置
    CORS_ORIGINS: str = '["http://localhost:3000","http://127.0.0.1:3000"]'
    
    class Config:
        env_file = ".env"
        case_sensitive = True
    
    @property
    def cors_origins_list(self) -> List[str]:
        """从 JSON 字符串解析 CORS 源列表。"""
        import json
        try:
            return json.loads(self.CORS_ORIGINS)
        except:
            return ["http://localhost:3000"]


# 全局设置实例
settings = Settings()

# 确保数据目录存在
os.makedirs(os.path.dirname(settings.DATABASE_URL.replace("sqlite+aiosqlite:///", "")), exist_ok=True)
os.makedirs(settings.AUDIO_OUTPUT_DIR, exist_ok=True)
