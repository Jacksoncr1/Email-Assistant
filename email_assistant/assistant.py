from __future__ import annotations

import secrets

from .config import AppSettings
from .llm import LLMGateway, build_llm_client
from .models import (
    CredentialRecord,
    DecryptedCredential,
    Draft,
    OAuthTokens,
    StoredEmail,
    SyncResult,
    ToneProfile,
    User,
)
from .providers import ProviderRegistry, build_default_registry
from .postgres_storage import PostgresStore
from .security import TokenCipher
from .storage import SqliteStore


class EmailAssistantModule:
    """Application service that host products can import directly."""

    def __init__(
        self,
        *,
        store: SqliteStore,
        cipher: TokenCipher,
        providers: ProviderRegistry,
        llm_gateway: LLMGateway,
    ) -> None:
        self.store = store
        self.cipher = cipher
        self.providers = providers
        self.llm_gateway = llm_gateway

    def register_user(
        self, *, tenant_id: str, email_address: str, external_user_id: str | None = None
    ) -> User:
        return self.store.create_user(tenant_id, email_address, external_user_id)

    def begin_oauth(
        self,
        *,
        tenant_id: str,
        user_id: str,
        provider_name: str,
        redirect_uri: str,
        scopes: list[str] | None = None,
    ) -> dict[str, str]:
        provider = self.providers.get(provider_name)
        requested_scopes = scopes or ["email.read", "email.drafts"]
        state = secrets.token_urlsafe(32)
        self.store.create_oauth_state(tenant_id, user_id, provider_name, redirect_uri, state)
        return {
            "state": state,
            "authorization_url": provider.build_authorization_url(
                state=state, redirect_uri=redirect_uri, scopes=requested_scopes
            ),
        }

    def complete_oauth(
        self, *, provider_name: str, state: str, code: str, redirect_uri: str | None = None
    ) -> User:
        oauth_state = self.store.consume_oauth_state(state, provider_name)
        provider = self.providers.get(provider_name)
        tokens = provider.exchange_code(code=code, redirect_uri=redirect_uri or oauth_state.redirect_uri)
        self.store.save_credentials(
            oauth_state.tenant_id,
            oauth_state.user_id,
            provider_name,
            self.cipher.encrypt(tokens.access_token),
            self.cipher.encrypt(tokens.refresh_token),
            tokens.expires_at,
            tokens.scopes,
        )
        return self.store.get_user(oauth_state.tenant_id, oauth_state.user_id)

    def connect_mock_provider(self, *, tenant_id: str, user_id: str) -> CredentialRecord:
        """Attach mock provider credentials without a browser redirect."""

        tokens = OAuthTokens(
            access_token=f"mock-access-token:auto:{user_id}",
            refresh_token=f"mock-refresh-token:auto:{user_id}",
            scopes=["email.read", "email.drafts"],
        )
        return self.store.save_credentials(
            tenant_id,
            user_id,
            "mock",
            self.cipher.encrypt(tokens.access_token),
            self.cipher.encrypt(tokens.refresh_token),
            tokens.expires_at,
            tokens.scopes,
        )

    def sync_user(
        self, *, tenant_id: str, user_id: str, provider_name: str | None = None
    ) -> SyncResult:
        user = self.store.get_user(tenant_id, user_id)
        credentials = self.store.list_credentials(tenant_id, user_id, provider_name)
        providers_checked: list[str] = []
        messages_seen = 0
        messages_stored = 0

        for credential_record in credentials:
            provider = self.providers.get(credential_record.provider)
            decrypted = self._decrypt_credential(credential_record)
            providers_checked.append(credential_record.provider)
            messages = provider.list_messages(credential=decrypted, user=user)
            messages_seen += len(messages)

            for message in messages:
                triage, usage = self.llm_gateway.triage_email(message)
                stored_email, created = self.store.upsert_email(tenant_id, user_id, message, triage)
                if created:
                    messages_stored += 1
                self._record_usage(tenant_id, user_id, usage)
                self.store.record_ledger(
                    tenant_id,
                    user_id,
                    email_id=stored_email.id,
                    event="triage",
                    status="completed",
                    detail=f"{triage.category}/{triage.priority}",
                )

        return SyncResult(
            tenant_id=tenant_id,
            user_id=user_id,
            providers_checked=providers_checked,
            messages_seen=messages_seen,
            messages_stored=messages_stored,
        )

    def list_emails(
        self,
        *,
        tenant_id: str,
        user_id: str,
        limit: int = 50,
        category: str | None = None,
    ) -> list[StoredEmail]:
        return self.store.list_emails(tenant_id, user_id, limit=limit, category=category)

    def generate_draft(self, *, tenant_id: str, user_id: str, email_id: str) -> Draft:
        email = self.store.get_email(tenant_id, user_id, email_id)
        tone_profile = self.store.get_tone_profile(tenant_id, user_id)
        draft_result, usage = self.llm_gateway.draft_reply(email, tone_profile)
        credentials = self.store.list_credentials(tenant_id, user_id, email.provider)
        provider_draft_id = None

        if credentials:
            provider = self.providers.get(email.provider)
            provider_draft_id = provider.create_draft(
                credential=self._decrypt_credential(credentials[0]),
                user=self.store.get_user(tenant_id, user_id),
                email=email,
                subject=draft_result.subject,
                body=draft_result.body,
            )

        draft = self.store.save_draft(
            tenant_id,
            user_id,
            email_id,
            provider=email.provider,
            subject=draft_result.subject,
            body=draft_result.body,
            provider_draft_id=provider_draft_id,
        )
        self._record_usage(tenant_id, user_id, usage)
        self.store.record_ledger(
            tenant_id,
            user_id,
            email_id=email_id,
            event="draft",
            status="created",
            detail=draft.id,
        )
        return draft

    def list_drafts(self, *, tenant_id: str, user_id: str, limit: int = 50) -> list[Draft]:
        return self.store.list_drafts(tenant_id, user_id, limit=limit)

    def get_tone_profile(self, *, tenant_id: str, user_id: str) -> ToneProfile:
        return self.store.get_tone_profile(tenant_id, user_id)

    def update_tone_profile(
        self,
        *,
        tenant_id: str,
        user_id: str,
        formality: int | None = None,
        warmth: int | None = None,
        brevity: int | None = None,
        custom_instructions: str | None = None,
    ) -> ToneProfile:
        return self.store.update_tone_profile(
            tenant_id,
            user_id,
            formality=formality,
            warmth=warmth,
            brevity=brevity,
            custom_instructions=custom_instructions,
        )

    def _decrypt_credential(self, record: CredentialRecord) -> DecryptedCredential:
        return DecryptedCredential(
            provider=record.provider,
            access_token=self.cipher.decrypt(record.encrypted_access_token),
            refresh_token=self.cipher.decrypt(record.encrypted_refresh_token),
            expires_at=record.expires_at,
            scopes=record.scopes,
        )

    def _record_usage(self, tenant_id: str, user_id: str, usage) -> None:
        self.store.record_usage(
            tenant_id,
            user_id,
            operation=usage.operation,
            provider=usage.provider,
            model=usage.model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            estimated_cost_usd=usage.estimated_cost_usd,
        )


def build_module(settings: AppSettings | None = None) -> EmailAssistantModule:
    settings = settings or AppSettings.from_env()
    settings.ensure_local_directories()
    if settings.use_postgres:
        store = PostgresStore(settings.normalized_db_path)
    else:
        store = SqliteStore(settings.normalized_db_path)
    store.init_db()
    cipher = TokenCipher(settings.secret_key, environment=settings.environment)
    llm_client = build_llm_client(
        settings.llm_provider,
        openai_api_key=settings.openai_api_key,
        openai_model=settings.openai_model,
    )
    return EmailAssistantModule(
        store=store,
        cipher=cipher,
        providers=build_default_registry(),
        llm_gateway=LLMGateway(llm_client),
    )
