from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class AppSettings:
    """Runtime settings for the module.

    The defaults favor a local demo that can run without cloud accounts. A
    production deployment should provide a strong secret, a durable database,
    and real provider/LLM adapters.
    """

    db_path: str = "./data/email_assistant.db"
    database_url: str | None = None
    secret_key: str = "dev-only-email-assistant-secret"
    environment: str = "development"
    llm_provider: str = "local"
    openai_api_key: str | None = None
    openai_model: str | None = None
    public_base_url: str = "http://localhost:8000"

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "AppSettings":
        if environ is None:
            try:
                from dotenv import load_dotenv

                load_dotenv()
            except ImportError:
                pass
        env = environ or os.environ
        return cls(
            db_path=env.get("EMAIL_ASSISTANT_DB_PATH", cls.db_path),
            database_url=env.get("EMAIL_ASSISTANT_DATABASE_URL")
            or env.get("SUPABASE_DATABASE_URL")
            or None,
            secret_key=env.get("EMAIL_ASSISTANT_SECRET_KEY", cls.secret_key),
            environment=env.get("EMAIL_ASSISTANT_ENVIRONMENT", cls.environment).lower(),
            llm_provider=env.get("EMAIL_ASSISTANT_LLM_PROVIDER", cls.llm_provider).lower(),
            openai_api_key=env.get("EMAIL_ASSISTANT_OPENAI_API_KEY") or None,
            openai_model=env.get("EMAIL_ASSISTANT_OPENAI_MODEL") or None,
            public_base_url=env.get("EMAIL_ASSISTANT_PUBLIC_BASE_URL", cls.public_base_url).rstrip("/"),
        )

    @property
    def normalized_db_path(self) -> str:
        if self.database_url:
            return self.database_url
        if self.db_path.startswith("sqlite:///"):
            return self.db_path.removeprefix("sqlite:///")
        return self.db_path

    def ensure_local_directories(self) -> None:
        if self.use_postgres:
            return
        db_path = self.normalized_db_path
        if db_path == ":memory:":
            return
        Path(db_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)

    @property
    def use_postgres(self) -> bool:
        value = self.database_url or self.db_path
        return value.startswith("postgres://") or value.startswith("postgresql://")
