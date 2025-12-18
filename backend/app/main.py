"""
FastAPI 应用程序入口点。
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from .core.config import settings
from .core.database import init_db
from .api import tasks, sse
from .utils.logger import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用程序生命周期管理器。"""
    # 启动
    logger.info("启动 VideoSieve 后端...")
    logger.info(f"OpenAI Base URL: {settings.OPENAI_BASE_URL}")
    logger.info(f"OpenAI Model: {settings.OPENAI_MODEL}")
    logger.info(f"Whisper Model: {settings.WHISPER_MODEL}")
    logger.info(f"Database: {settings.DATABASE_URL}")
    
    # 初始化数据库
    await init_db()
    logger.info("数据库已初始化")
    
    yield
    
    # 关闭
    logger.info("关闭 VideoSieve 后端...")


# 创建 FastAPI 应用
app = FastAPI(
    title="VideoSieve API",
    description="AI 驱动的视频转录、优化和摘要生成服务",
    version="1.0.0",
    lifespan=lifespan
)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 包含路由器
app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])
app.include_router(sse.router, prefix="/api/tasks", tags=["sse"])


@app.get("/")
async def root():
    """根端点。"""
    return {
        "name": "VideoSieve API",
        "version": "1.0.0",
        "status": "running"
    }


@app.get("/health")
async def health_check():
    """健康检查端点。"""
    return {"status": "healthy"}
