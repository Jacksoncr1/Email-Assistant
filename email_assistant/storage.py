from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator
from uuid import uuid4

from .exceptions import NotFoundError, TenantAccessError
from .models import (
    CredentialRecord,
    Draft,
    OAuthState,
    ProviderMessage,
    StoredEmail,
    ToneProfile,
    TriageResult,
    User,
)


class SqliteStore:
    """Small persistence adapter with mandatory tenant filters on public reads."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        if db_path != ":memory:":
            Path(db_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)

    def init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def create_user(self, tenant_id: str, email_address: str, external_user_id: str | None = None) -> User:
        now = utcnow()
        with self._connect() as conn:
            existing = conn.execute(
                """
                SELECT * FROM users
                WHERE tenant_id = ? AND lower(email_address) = lower(?)
                """,
                (tenant_id, email_address),
            ).fetchone()
            if existing is not None:
                return _user_from_row(existing)

            user_id = str(uuid4())
            conn.execute(
                """
                INSERT INTO users (id, tenant_id, email_address, external_user_id, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, tenant_id, email_address, external_user_id, now),
            )
            conn.execute(
                """
                INSERT INTO tone_profiles
                    (user_id, tenant_id, formality, warmth, brevity, custom_instructions, updated_at)
                VALUES (?, ?, 50, 60, 50, '', ?)
                """,
                (user_id, tenant_id, now),
            )
            return User(user_id, tenant_id, email_address, external_user_id, now)

    def get_user(self, tenant_id: str, user_id: str) -> User:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            if row is None:
                raise NotFoundError("User not found.")
            if row["tenant_id"] != tenant_id:
                raise TenantAccessError("User belongs to another tenant.")
            return _user_from_row(row)

    def save_credentials(
        self,
        tenant_id: str,
        user_id: str,
        provider: str,
        encrypted_access_token: str,
        encrypted_refresh_token: str,
        expires_at: str | None,
        scopes: list[str],
    ) -> CredentialRecord:
        self.get_user(tenant_id, user_id)
        now = utcnow()
        with self._connect() as conn:
            existing = conn.execute(
                """
                SELECT id, created_at FROM credentials
                WHERE tenant_id = ? AND user_id = ? AND provider = ?
                """,
                (tenant_id, user_id, provider),
            ).fetchone()
            credential_id = existing["id"] if existing else str(uuid4())
            created_at = existing["created_at"] if existing else now
            conn.execute(
                """
                INSERT INTO credentials (
                    id, tenant_id, user_id, provider, encrypted_access_token,
                    encrypted_refresh_token, expires_at, scopes_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, provider) DO UPDATE SET
                    encrypted_access_token = excluded.encrypted_access_token,
                    encrypted_refresh_token = excluded.encrypted_refresh_token,
                    expires_at = excluded.expires_at,
                    scopes_json = excluded.scopes_json,
                    updated_at = excluded.updated_at
                """,
                (
                    credential_id,
                    tenant_id,
                    user_id,
                    provider,
                    encrypted_access_token,
                    encrypted_refresh_token,
                    expires_at,
                    json.dumps(scopes),
                    created_at,
                    now,
                ),
            )
            row = conn.execute("SELECT * FROM credentials WHERE id = ?", (credential_id,)).fetchone()
            return _credential_from_row(row)

    def list_credentials(
        self, tenant_id: str, user_id: str, provider: str | None = None
    ) -> list[CredentialRecord]:
        self.get_user(tenant_id, user_id)
        params: list[str] = [tenant_id, user_id]
        query = "SELECT * FROM credentials WHERE tenant_id = ? AND user_id = ?"
        if provider is not None:
            query += " AND provider = ?"
            params.append(provider)
        with self._connect() as conn:
            return [_credential_from_row(row) for row in conn.execute(query, params).fetchall()]

    def create_oauth_state(
        self, tenant_id: str, user_id: str, provider: str, redirect_uri: str, state: str
    ) -> OAuthState:
        self.get_user(tenant_id, user_id)
        now = utcnow()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO oauth_states
                    (state, tenant_id, user_id, provider, redirect_uri, created_at, consumed_at)
                VALUES (?, ?, ?, ?, ?, ?, NULL)
                """,
                (state, tenant_id, user_id, provider, redirect_uri, now),
            )
            return OAuthState(state, tenant_id, user_id, provider, redirect_uri, now, None)

    def consume_oauth_state(self, state: str, provider: str) -> OAuthState:
        now = utcnow()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM oauth_states WHERE state = ? AND provider = ?",
                (state, provider),
            ).fetchone()
            if row is None:
                raise NotFoundError("OAuth state was not found.")
            if row["consumed_at"] is not None:
                raise NotFoundError("OAuth state was already consumed.")
            conn.execute("UPDATE oauth_states SET consumed_at = ? WHERE state = ?", (now, state))
            return _oauth_state_from_row(row)

    def get_tone_profile(self, tenant_id: str, user_id: str) -> ToneProfile:
        self.get_user(tenant_id, user_id)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM tone_profiles WHERE tenant_id = ? AND user_id = ?",
                (tenant_id, user_id),
            ).fetchone()
            if row is None:
                raise NotFoundError("Tone profile not found.")
            return _tone_from_row(row)

    def update_tone_profile(
        self,
        tenant_id: str,
        user_id: str,
        *,
        formality: int | None = None,
        warmth: int | None = None,
        brevity: int | None = None,
        custom_instructions: str | None = None,
    ) -> ToneProfile:
        current = self.get_tone_profile(tenant_id, user_id)
        updated = ToneProfile(
            user_id=user_id,
            tenant_id=tenant_id,
            formality=_clamp(formality if formality is not None else current.formality),
            warmth=_clamp(warmth if warmth is not None else current.warmth),
            brevity=_clamp(brevity if brevity is not None else current.brevity),
            custom_instructions=current.custom_instructions
            if custom_instructions is None
            else custom_instructions[:1000],
            updated_at=utcnow(),
        )
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE tone_profiles
                SET formality = ?, warmth = ?, brevity = ?, custom_instructions = ?, updated_at = ?
                WHERE tenant_id = ? AND user_id = ?
                """,
                (
                    updated.formality,
                    updated.warmth,
                    updated.brevity,
                    updated.custom_instructions,
                    updated.updated_at,
                    tenant_id,
                    user_id,
                ),
            )
        return updated

    def upsert_email(
        self, tenant_id: str, user_id: str, message: ProviderMessage, triage: TriageResult
    ) -> tuple[StoredEmail, bool]:
        self.get_user(tenant_id, user_id)
        now = utcnow()
        with self._connect() as conn:
            existing = conn.execute(
                """
                SELECT * FROM emails
                WHERE tenant_id = ? AND user_id = ? AND provider = ? AND provider_message_id = ?
                """,
                (tenant_id, user_id, message.provider, message.provider_message_id),
            ).fetchone()
            email_id = existing["id"] if existing else str(uuid4())
            created_at = existing["created_at"] if existing else now
            conn.execute(
                """
                INSERT INTO emails (
                    id, tenant_id, user_id, provider, provider_message_id, sender, recipient,
                    subject, body, snippet, received_at, category, priority, summary,
                    needs_reply, injection_detected, confidence, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, provider, provider_message_id) DO UPDATE SET
                    sender = excluded.sender,
                    recipient = excluded.recipient,
                    subject = excluded.subject,
                    body = excluded.body,
                    snippet = excluded.snippet,
                    received_at = excluded.received_at,
                    category = excluded.category,
                    priority = excluded.priority,
                    summary = excluded.summary,
                    needs_reply = excluded.needs_reply,
                    injection_detected = excluded.injection_detected,
                    confidence = excluded.confidence
                """,
                (
                    email_id,
                    tenant_id,
                    user_id,
                    message.provider,
                    message.provider_message_id,
                    message.sender,
                    message.recipient,
                    message.subject,
                    message.body,
                    message.snippet,
                    message.received_at,
                    triage.category,
                    triage.priority,
                    triage.summary,
                    int(triage.needs_reply),
                    int(triage.injection_detected),
                    triage.confidence,
                    created_at,
                ),
            )
            row = conn.execute("SELECT * FROM emails WHERE id = ?", (email_id,)).fetchone()
            return _email_from_row(row), existing is None

    def list_emails(
        self,
        tenant_id: str,
        user_id: str,
        *,
        limit: int = 50,
        category: str | None = None,
    ) -> list[StoredEmail]:
        self.get_user(tenant_id, user_id)
        limit = max(1, min(limit, 250))
        params: list[object] = [tenant_id, user_id]
        query = "SELECT * FROM emails WHERE tenant_id = ? AND user_id = ?"
        if category is not None:
            query += " AND category = ?"
            params.append(category)
        query += " ORDER BY received_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            return [_email_from_row(row) for row in conn.execute(query, params).fetchall()]

    def get_email(self, tenant_id: str, user_id: str, email_id: str) -> StoredEmail:
        self.get_user(tenant_id, user_id)
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM emails WHERE id = ?", (email_id,)).fetchone()
            if row is None:
                raise NotFoundError("Email not found.")
            if row["tenant_id"] != tenant_id or row["user_id"] != user_id:
                raise TenantAccessError("Email belongs to another tenant or user.")
            return _email_from_row(row)

    def save_draft(
        self,
        tenant_id: str,
        user_id: str,
        email_id: str,
        *,
        provider: str,
        subject: str,
        body: str,
        provider_draft_id: str | None,
        status: str = "drafted",
    ) -> Draft:
        self.get_email(tenant_id, user_id, email_id)
        now = utcnow()
        draft_id = str(uuid4())
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO drafts (
                    id, tenant_id, user_id, email_id, provider, subject, body,
                    status, provider_draft_id, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    draft_id,
                    tenant_id,
                    user_id,
                    email_id,
                    provider,
                    subject,
                    body,
                    status,
                    provider_draft_id,
                    now,
                ),
            )
            row = conn.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()
            return _draft_from_row(row)

    def list_drafts(self, tenant_id: str, user_id: str, *, limit: int = 50) -> list[Draft]:
        self.get_user(tenant_id, user_id)
        limit = max(1, min(limit, 250))
        with self._connect() as conn:
            return [
                _draft_from_row(row)
                for row in conn.execute(
                    """
                    SELECT * FROM drafts
                    WHERE tenant_id = ? AND user_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (tenant_id, user_id, limit),
                ).fetchall()
            ]

    def record_usage(
        self,
        tenant_id: str,
        user_id: str,
        *,
        operation: str,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        estimated_cost_usd: float,
    ) -> None:
        self.get_user(tenant_id, user_id)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO usage_events (
                    id, tenant_id, user_id, operation, provider, model,
                    input_tokens, output_tokens, estimated_cost_usd, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    tenant_id,
                    user_id,
                    operation,
                    provider,
                    model,
                    input_tokens,
                    output_tokens,
                    estimated_cost_usd,
                    utcnow(),
                ),
            )

    def record_ledger(
        self,
        tenant_id: str,
        user_id: str,
        *,
        email_id: str | None,
        event: str,
        status: str,
        detail: str = "",
    ) -> None:
        self.get_user(tenant_id, user_id)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO processing_ledger (
                    id, tenant_id, user_id, email_id, event, status, detail, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (str(uuid4()), tenant_id, user_id, email_id, event, status, detail, utcnow()),
            )


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _clamp(value: int) -> int:
    return max(0, min(100, int(value)))


def _user_from_row(row: sqlite3.Row) -> User:
    return User(
        id=row["id"],
        tenant_id=row["tenant_id"],
        email_address=row["email_address"],
        external_user_id=row["external_user_id"],
        created_at=row["created_at"],
    )


def _credential_from_row(row: sqlite3.Row) -> CredentialRecord:
    return CredentialRecord(
        id=row["id"],
        tenant_id=row["tenant_id"],
        user_id=row["user_id"],
        provider=row["provider"],
        encrypted_access_token=row["encrypted_access_token"],
        encrypted_refresh_token=row["encrypted_refresh_token"],
        expires_at=row["expires_at"],
        scopes=json.loads(row["scopes_json"] or "[]"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _tone_from_row(row: sqlite3.Row) -> ToneProfile:
    return ToneProfile(
        user_id=row["user_id"],
        tenant_id=row["tenant_id"],
        formality=row["formality"],
        warmth=row["warmth"],
        brevity=row["brevity"],
        custom_instructions=row["custom_instructions"],
        updated_at=row["updated_at"],
    )


def _email_from_row(row: sqlite3.Row) -> StoredEmail:
    return StoredEmail(
        id=row["id"],
        tenant_id=row["tenant_id"],
        user_id=row["user_id"],
        provider=row["provider"],
        provider_message_id=row["provider_message_id"],
        sender=row["sender"],
        recipient=row["recipient"],
        subject=row["subject"],
        body=row["body"],
        snippet=row["snippet"],
        received_at=row["received_at"],
        category=row["category"],
        priority=row["priority"],
        summary=row["summary"],
        needs_reply=bool(row["needs_reply"]),
        injection_detected=bool(row["injection_detected"]),
        confidence=float(row["confidence"]),
        created_at=row["created_at"],
    )


def _draft_from_row(row: sqlite3.Row) -> Draft:
    return Draft(
        id=row["id"],
        tenant_id=row["tenant_id"],
        user_id=row["user_id"],
        email_id=row["email_id"],
        provider=row["provider"],
        subject=row["subject"],
        body=row["body"],
        status=row["status"],
        provider_draft_id=row["provider_draft_id"],
        created_at=row["created_at"],
    )


def _oauth_state_from_row(row: sqlite3.Row) -> OAuthState:
    return OAuthState(
        state=row["state"],
        tenant_id=row["tenant_id"],
        user_id=row["user_id"],
        provider=row["provider"],
        redirect_uri=row["redirect_uri"],
        created_at=row["created_at"],
        consumed_at=row["consumed_at"],
    )


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    email_address TEXT NOT NULL,
    external_user_id TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(tenant_id, email_address)
);

CREATE TABLE IF NOT EXISTS credentials (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    encrypted_access_token TEXT NOT NULL,
    encrypted_refresh_token TEXT NOT NULL,
    expires_at TEXT,
    scopes_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(user_id, provider),
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS oauth_states (
    state TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    redirect_uri TEXT NOT NULL,
    created_at TEXT NOT NULL,
    consumed_at TEXT,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tone_profiles (
    user_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    formality INTEGER NOT NULL,
    warmth INTEGER NOT NULL,
    brevity INTEGER NOT NULL,
    custom_instructions TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS emails (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    provider_message_id TEXT NOT NULL,
    sender TEXT NOT NULL,
    recipient TEXT NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    snippet TEXT NOT NULL,
    received_at TEXT NOT NULL,
    category TEXT NOT NULL,
    priority TEXT NOT NULL,
    summary TEXT NOT NULL,
    needs_reply INTEGER NOT NULL,
    injection_detected INTEGER NOT NULL,
    confidence REAL NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(user_id, provider, provider_message_id),
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS drafts (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    email_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    status TEXT NOT NULL,
    provider_draft_id TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY(email_id) REFERENCES emails(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS usage_events (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    operation TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    estimated_cost_usd REAL NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS processing_ledger (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    email_id TEXT,
    event TEXT NOT NULL,
    status TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_users_tenant ON users(tenant_id);
CREATE INDEX IF NOT EXISTS idx_emails_user_received ON emails(user_id, received_at);
CREATE INDEX IF NOT EXISTS idx_drafts_user_created ON drafts(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_usage_user_created ON usage_events(user_id, created_at);
"""
