"""
Configuration management using Pydantic Settings.
Loads environment variables and provides type-safe configuration.
"""
from pydantic_settings import BaseSettings
from typing import List
import os


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # OpenAI API Configuration
    OPENAI_API_KEY: str
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_MODEL: str = "gpt-4o-mini"
    
    # Database Configuration
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/db/videosieve.db"
    
    # Whisper Configuration
    WHISPER_MODEL: str = "base"  # tiny, base, small, medium, large
    WHISPER_DEVICE: str = "cpu"
    WHISPER_COMPUTE_TYPE: str = "int8"
    
    # Task Queue Configuration
    MAX_CONCURRENT_TASKS: int = 5
    
    # File Storage Configuration
    AUDIO_OUTPUT_DIR: str = "./data/audio"
    
    # CORS Configuration
    CORS_ORIGINS: str = '["http://localhost:3000","http://127.0.0.1:3000"]'
    
    class Config:
        env_file = ".env"
        case_sensitive = True
    
    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS origins from JSON string."""
        import json
        try:
            return json.loads(self.CORS_ORIGINS)
        except:
            return ["http://localhost:3000"]


# Global settings instance
settings = Settings()

# Ensure data directories exist
os.makedirs(os.path.dirname(settings.DATABASE_URL.replace("sqlite+aiosqlite:///", "")), exist_ok=True)
os.makedirs(settings.AUDIO_OUTPUT_DIR, exist_ok=True)
