"""Infrastructure adapters for VideoSieve."""

from .event_bus import RedisEventBus
from .interfaces import EventBus, EventSubscription, JobRepository, WorkspaceStore
from .models import (
    AuthUserRecord,
    GuestCooldownRecord,
    InfraEvent,
    JobRecord,
    OperationLogRecord,
    ProjectRecord,
    SystemSettingRecord,
    UserCookieRecord,
)
from .sqlite_repository import SQLiteJobRepository
from .workspace import FileSystemWorkspaceStore

__all__ = [
    "EventBus",
    "EventSubscription",
    "FileSystemWorkspaceStore",
    "GuestCooldownRecord",
    "InfraEvent",
    "AuthUserRecord",
    "JobRecord",
    "JobRepository",
    "OperationLogRecord",
    "ProjectRecord",
    "RedisEventBus",
    "SQLiteJobRepository",
    "SystemSettingRecord",
    "UserCookieRecord",
    "WorkspaceStore",
    "__version__",
]

__version__ = "0.1.0"
