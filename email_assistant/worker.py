from __future__ import annotations

from dataclasses import asdict

from .assistant import build_module

try:
    from celery import Celery
except ImportError:
    Celery = None


if Celery is not None:
    celery_app = Celery("email_assistant")

    @celery_app.task(name="email_assistant.sync_user")
    def sync_user_task(tenant_id: str, user_id: str, provider_name: str | None = None) -> dict:
        module = build_module()
        return asdict(
            module.sync_user(tenant_id=tenant_id, user_id=user_id, provider_name=provider_name)
        )

else:
    celery_app = None

    def sync_user_task(tenant_id: str, user_id: str, provider_name: str | None = None) -> dict:
        module = build_module()
        return asdict(
            module.sync_user(tenant_id=tenant_id, user_id=user_id, provider_name=provider_name)
        )
