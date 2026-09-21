"""Infrastructure adapters for VideoSieve."""

from .event_bus import InMemoryEventBus, SQLiteEventBus
from .interfaces import EventBus, EventSubscription, JobRepository, WorkspaceStore
from .models import (
    InfraEvent,
    JobRecord,
    OperationLogRecord,
    ProjectRecord,
    ProviderSecretRecord,
    SystemSettingRecord,
    UserCookieRecord,
)
from .secrets import SecretCipherError, decrypt_secret, encrypt_secret
from .sqlite_repository import SQLiteJobRepository
from .workspace import FileSystemWorkspaceStore

__all__ = [
    "EventBus",
    "EventSubscription",
    "FileSystemWorkspaceStore",
    "InfraEvent",
    "JobRecord",
    "JobRepository",
    "OperationLogRecord",
    "ProviderSecretRecord",
    "ProjectRecord",
    "InMemoryEventBus",
    "SQLiteJobRepository",
    "SQLiteEventBus",
    "SystemSettingRecord",
    "UserCookieRecord",
    "WorkspaceStore",
    "SecretCipherError",
    "decrypt_secret",
    "encrypt_secret",
    "__version__",
]

__version__ = "0.1.0"
