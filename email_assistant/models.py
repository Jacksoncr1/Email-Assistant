from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


JsonDict = dict[str, Any]


@dataclass(frozen=True)
class User:
    id: str
    tenant_id: str
    email_address: str
    external_user_id: str | None
    created_at: str


@dataclass(frozen=True)
class OAuthTokens:
    access_token: str
    refresh_token: str
    expires_at: str | None = None
    scopes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CredentialRecord:
    id: str
    tenant_id: str
    user_id: str
    provider: str
    encrypted_access_token: str
    encrypted_refresh_token: str
    expires_at: str | None
    scopes: list[str]
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class DecryptedCredential:
    provider: str
    access_token: str
    refresh_token: str
    expires_at: str | None
    scopes: list[str]


@dataclass(frozen=True)
class ToneProfile:
    user_id: str
    tenant_id: str
    formality: int = 50
    warmth: int = 60
    brevity: int = 50
    custom_instructions: str = ""
    updated_at: str | None = None


@dataclass(frozen=True)
class ProviderMessage:
    provider: str
    provider_message_id: str
    sender: str
    recipient: str
    subject: str
    body: str
    snippet: str
    received_at: str


@dataclass(frozen=True)
class TriageResult:
    category: str
    priority: str
    summary: str
    needs_reply: bool
    detected_intents: list[str]
    injection_detected: bool
    confidence: float


@dataclass(frozen=True)
class DraftResult:
    subject: str
    body: str


@dataclass(frozen=True)
class StoredEmail:
    id: str
    tenant_id: str
    user_id: str
    provider: str
    provider_message_id: str
    sender: str
    recipient: str
    subject: str
    body: str
    snippet: str
    received_at: str
    category: str
    priority: str
    summary: str
    needs_reply: bool
    injection_detected: bool
    confidence: float
    created_at: str


@dataclass(frozen=True)
class Draft:
    id: str
    tenant_id: str
    user_id: str
    email_id: str
    provider: str
    subject: str
    body: str
    status: str
    provider_draft_id: str | None
    created_at: str


@dataclass(frozen=True)
class TokenUsage:
    operation: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float = 0.0


@dataclass(frozen=True)
class SyncResult:
    tenant_id: str
    user_id: str
    providers_checked: list[str]
    messages_seen: int
    messages_stored: int
    drafts_created: int = 0


@dataclass(frozen=True)
class OAuthState:
    state: str
    tenant_id: str
    user_id: str
    provider: str
    redirect_uri: str
    created_at: str
    consumed_at: str | None


def to_dict(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    if isinstance(value, list):
        return [to_dict(item) for item in value]
    if isinstance(value, dict):
        return {key: to_dict(item) for key, item in value.items()}
    return value
