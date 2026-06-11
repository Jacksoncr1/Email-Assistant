"""Public package surface for the email assistant module."""

from .assistant import EmailAssistantModule, build_module
from .config import AppSettings
from .models import Draft, StoredEmail, SyncResult, ToneProfile, User

__all__ = [
    "AppSettings",
    "Draft",
    "EmailAssistantModule",
    "StoredEmail",
    "SyncResult",
    "ToneProfile",
    "User",
    "build_module",
]
