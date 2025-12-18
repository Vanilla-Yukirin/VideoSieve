"""
数据库连接和会话管理。
使用 SQLAlchemy 和异步 SQLite 支持。
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from .config import settings

# 创建异步引擎
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}
)

# 创建异步会话工厂
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

# 模型基类
Base = declarative_base()


async def get_db():
    """
    提供数据库会话的依赖项。
    使用后自动关闭会话。
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """初始化数据库表。"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
