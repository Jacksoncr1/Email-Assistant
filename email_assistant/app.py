from __future__ import annotations

from typing import Any

from .assistant import EmailAssistantModule, build_module
from .config import AppSettings
from .exceptions import ConfigurationError, EmailAssistantError, NotFoundError, TenantAccessError
from .models import to_dict


def create_app(
    settings: AppSettings | None = None, module: EmailAssistantModule | None = None
):
    try:
        from fastapi import Body, FastAPI, HTTPException, Query
    except ImportError as exc:
        raise ConfigurationError("Install FastAPI dependencies to run the HTTP API.") from exc

    settings = settings or AppSettings.from_env()
    service = module or build_module(settings)
    app = FastAPI(
        title="AI Email Assistant Module",
        version="0.1.0",
        description="Tenant-scoped email triage and draft generation service.",
    )

    def translate_error(exc: EmailAssistantError) -> HTTPException:
        if isinstance(exc, TenantAccessError):
            return HTTPException(status_code=403, detail=str(exc))
        if isinstance(exc, NotFoundError):
            return HTTPException(status_code=404, detail=str(exc))
        if isinstance(exc, ConfigurationError):
            return HTTPException(status_code=500, detail=str(exc))
        return HTTPException(status_code=400, detail=str(exc))

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "ok": True,
            "providers": service.providers.names(),
            "crypto_backend": service.cipher.backend,
        }

    @app.get("/")
    def root() -> dict[str, Any]:
        return {
            "name": "AI Email Assistant Module",
            "ok": True,
            "health_url": "/health",
            "docs_url": "/docs",
        }

    @app.post("/tenants/{tenant_id}/users")
    def register_user(tenant_id: str, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        try:
            user = service.register_user(
                tenant_id=tenant_id,
                email_address=str(payload["email_address"]),
                external_user_id=payload.get("external_user_id"),
            )
            return to_dict(user)
        except KeyError as exc:
            raise HTTPException(status_code=422, detail=f"Missing field: {exc.args[0]}") from exc
        except EmailAssistantError as exc:
            raise translate_error(exc) from exc

    @app.post("/tenants/{tenant_id}/users/{user_id}/oauth/{provider_name}/start")
    def start_oauth(
        tenant_id: str,
        user_id: str,
        provider_name: str,
        payload: dict[str, Any] = Body(default={}),
    ) -> dict[str, Any]:
        redirect_uri = payload.get(
            "redirect_uri", f"{settings.public_base_url}/oauth/{provider_name}/callback"
        )
        try:
            return service.begin_oauth(
                tenant_id=tenant_id,
                user_id=user_id,
                provider_name=provider_name,
                redirect_uri=redirect_uri,
                scopes=payload.get("scopes"),
            )
        except EmailAssistantError as exc:
            raise translate_error(exc) from exc

    @app.get("/oauth/{provider_name}/callback")
    def oauth_callback(
        provider_name: str,
        state: str,
        code: str,
        redirect_uri: str | None = Query(default=None),
    ) -> dict[str, Any]:
        try:
            user = service.complete_oauth(
                provider_name=provider_name,
                state=state,
                code=code,
                redirect_uri=redirect_uri,
            )
            return {"connected": True, "user": to_dict(user)}
        except EmailAssistantError as exc:
            raise translate_error(exc) from exc

    @app.post("/tenants/{tenant_id}/users/{user_id}/providers/mock/connect")
    def connect_mock(tenant_id: str, user_id: str) -> dict[str, Any]:
        try:
            credential = service.connect_mock_provider(tenant_id=tenant_id, user_id=user_id)
            return {"connected": True, "provider": credential.provider}
        except EmailAssistantError as exc:
            raise translate_error(exc) from exc

    @app.post("/tenants/{tenant_id}/users/{user_id}/sync")
    def sync_user(
        tenant_id: str,
        user_id: str,
        provider_name: str | None = Query(default=None),
    ) -> dict[str, Any]:
        try:
            result = service.sync_user(
                tenant_id=tenant_id, user_id=user_id, provider_name=provider_name
            )
            return to_dict(result)
        except EmailAssistantError as exc:
            raise translate_error(exc) from exc

    @app.get("/tenants/{tenant_id}/users/{user_id}/emails")
    def list_emails(
        tenant_id: str,
        user_id: str,
        limit: int = Query(default=50, ge=1, le=250),
        category: str | None = Query(default=None),
    ) -> dict[str, Any]:
        try:
            emails = service.list_emails(
                tenant_id=tenant_id, user_id=user_id, limit=limit, category=category
            )
            return {"items": to_dict(emails)}
        except EmailAssistantError as exc:
            raise translate_error(exc) from exc

    @app.post("/tenants/{tenant_id}/users/{user_id}/emails/{email_id}/draft")
    def create_draft(tenant_id: str, user_id: str, email_id: str) -> dict[str, Any]:
        try:
            draft = service.generate_draft(tenant_id=tenant_id, user_id=user_id, email_id=email_id)
            return to_dict(draft)
        except EmailAssistantError as exc:
            raise translate_error(exc) from exc

    @app.get("/tenants/{tenant_id}/users/{user_id}/drafts")
    def list_drafts(
        tenant_id: str, user_id: str, limit: int = Query(default=50, ge=1, le=250)
    ) -> dict[str, Any]:
        try:
            drafts = service.list_drafts(tenant_id=tenant_id, user_id=user_id, limit=limit)
            return {"items": to_dict(drafts)}
        except EmailAssistantError as exc:
            raise translate_error(exc) from exc

    @app.get("/tenants/{tenant_id}/users/{user_id}/tone-profile")
    def get_tone_profile(tenant_id: str, user_id: str) -> dict[str, Any]:
        try:
            return to_dict(service.get_tone_profile(tenant_id=tenant_id, user_id=user_id))
        except EmailAssistantError as exc:
            raise translate_error(exc) from exc

    @app.put("/tenants/{tenant_id}/users/{user_id}/tone-profile")
    def update_tone_profile(
        tenant_id: str, user_id: str, payload: dict[str, Any] = Body(...)
    ) -> dict[str, Any]:
        try:
            tone = service.update_tone_profile(
                tenant_id=tenant_id,
                user_id=user_id,
                formality=payload.get("formality"),
                warmth=payload.get("warmth"),
                brevity=payload.get("brevity"),
                custom_instructions=payload.get("custom_instructions"),
            )
            return to_dict(tone)
        except EmailAssistantError as exc:
            raise translate_error(exc) from exc

    return app
