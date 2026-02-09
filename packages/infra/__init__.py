"""Infrastructure adapters for VideoSieve."""

from .event_bus import RedisEventBus
from .interfaces import EventBus, EventSubscription, JobRepository, WorkspaceStore
from .models import InfraEvent, JobRecord, ProjectRecord, UserCookieRecord
from .sqlite_repository import SQLiteJobRepository
from .workspace import FileSystemWorkspaceStore

__all__ = [
    "EventBus",
    "EventSubscription",
    "FileSystemWorkspaceStore",
    "InfraEvent",
    "JobRecord",
    "JobRepository",
    "ProjectRecord",
    "RedisEventBus",
    "SQLiteJobRepository",
    "UserCookieRecord",
    "WorkspaceStore",
    "__version__",
]

__version__ = "0.1.0"
