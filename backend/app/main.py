"""
FastAPI application entry point.
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
    """Application lifespan manager."""
    # Startup
    logger.info("Starting VideoSieve backend...")
    logger.info(f"OpenAI Base URL: {settings.OPENAI_BASE_URL}")
    logger.info(f"OpenAI Model: {settings.OPENAI_MODEL}")
    logger.info(f"Whisper Model: {settings.WHISPER_MODEL}")
    logger.info(f"Database: {settings.DATABASE_URL}")
    
    # Initialize database
    await init_db()
    logger.info("Database initialized")
    
    yield
    
    # Shutdown
    logger.info("Shutting down VideoSieve backend...")


# Create FastAPI app
app = FastAPI(
    title="VideoSieve API",
    description="AI-powered video transcription, optimization, and summarization service",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])
app.include_router(sse.router, prefix="/api/tasks", tags=["sse"])


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "VideoSieve API",
        "version": "1.0.0",
        "status": "running"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}
