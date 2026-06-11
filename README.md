# AI Email Assistant Module

A reusable, multi-tenant email assistant module for inbox triage and safe draft generation. It is designed to run by itself as a FastAPI service or be imported by a larger product as a Python module.

The current version is intentionally practical: it includes a local SQLite store, encrypted credential handling, a mock email provider, a deterministic local assistant, REST endpoints, a CLI demo, and tests. Gmail, Outlook, PostgreSQL, Redis/Celery deployment, and hosted LLM adapters can be added behind the existing interfaces without changing the host product API.

## What It Does

- Registers users under a required `tenant_id`.
- Stores OAuth-style credentials encrypted at the database boundary.
- Supports OAuth start/callback flow shape, plus a mock provider for local demos.
- Syncs inbox messages from provider adapters.
- Triages email into category, priority, summary, reply need, and prompt-injection flags.
- Generates reply drafts only. It never sends email directly.
- Stores processing ledger and token usage records for auditing.
- Exposes the workflow through both Python and FastAPI.

## Project Structure

```text
email_assistant/
  assistant.py    # Main service class for host products
  app.py          # FastAPI route factory
  cli.py          # Local demo and setup commands
  config.py       # Environment-backed settings
  llm.py          # Guardrailed LLM gateway and local/OpenAI adapters
  providers.py    # Email provider protocol and mock provider
  security.py     # Token encryption utilities
  storage.py      # SQLite persistence adapter
  worker.py       # Celery-compatible sync task entry
tests/
  test_assistant.py
  test_security.py
  test_storage.py
```

## Quickstart

Requires Python 3.10 or newer. Python 3.11+ is recommended for production.

```cmd
scripts\setup.cmd
```

If you prefer to run the commands manually from Command Prompt:

```cmd
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
.venv\Scripts\python.exe -m email_assistant generate-secret
```

Put the generated secret into `.env` as `EMAIL_ASSISTANT_SECRET_KEY`.

Initialize the database:

```cmd
.venv\Scripts\python.exe -m email_assistant init-db
```

Run the local end-to-end demo:

```cmd
scripts\demo.cmd
```

That demo registers a user, connects the mock provider, syncs mock inbox messages, triages them, and creates a draft reply.

## Run The API

```cmd
scripts\api.cmd
```

Open:

```text
http://127.0.0.1:8000/docs
```

Useful endpoints:

```text
GET  /health
POST /tenants/{tenant_id}/users
POST /tenants/{tenant_id}/users/{user_id}/providers/mock/connect
POST /tenants/{tenant_id}/users/{user_id}/sync
GET  /tenants/{tenant_id}/users/{user_id}/emails
POST /tenants/{tenant_id}/users/{user_id}/emails/{email_id}/draft
GET  /tenants/{tenant_id}/users/{user_id}/drafts
GET  /tenants/{tenant_id}/users/{user_id}/tone-profile
PUT  /tenants/{tenant_id}/users/{user_id}/tone-profile
```

Example user creation body:

```json
{
  "email_address": "demo@example.com",
  "external_user_id": "parent-app-user-123"
}
```

## Deploy With Vercel And Supabase

This project now supports a local SQLite mode and a Vercel + Supabase mode.

What was added for deployment:

- [app.py](app.py) exposes a top-level FastAPI `app` for Vercel.
- [vercel.json](vercel.json) keeps project config minimal so Vercel can auto-detect the root FastAPI app.
- [.python-version](.python-version) pins Vercel to Python 3.12.
- [database/migrations/001_initial_supabase.sql](database/migrations/001_initial_supabase.sql) creates the Supabase/Postgres tables.
- `PostgresStore` is selected automatically when `EMAIL_ASSISTANT_DATABASE_URL` is set.

### 1. Create Supabase Tables

Create a Supabase project, open the SQL Editor, and run:

```sql
-- database/migrations/001_initial_supabase.sql
```

The schema mirrors the local SQLite schema so the same service code works in both places.

### 2. Use The Supabase Pooler URL

For Vercel serverless functions, use Supabase's Transaction pooler connection string:

```text
postgres://postgres.PROJECT_REF:PASSWORD@aws-0-REGION.pooler.supabase.com:6543/postgres?sslmode=require
```

Put that value in Vercel as:

```text
EMAIL_ASSISTANT_DATABASE_URL=...
```

The app disables prepared statements for Postgres connections because Supabase transaction pooling does not support them.

### 3. Add Vercel Environment Variables

In the Vercel dashboard, add:

```text
EMAIL_ASSISTANT_DATABASE_URL=...
EMAIL_ASSISTANT_SECRET_KEY=your-generated-secret
EMAIL_ASSISTANT_ENVIRONMENT=production
EMAIL_ASSISTANT_LLM_PROVIDER=local
EMAIL_ASSISTANT_PUBLIC_BASE_URL=https://your-project.vercel.app
```

If you enable the OpenAI adapter later, also add:

```text
EMAIL_ASSISTANT_LLM_PROVIDER=openai
EMAIL_ASSISTANT_OPENAI_API_KEY=...
EMAIL_ASSISTANT_OPENAI_MODEL=...
```

### 4. Deploy

Install the Vercel CLI if needed, then deploy from the project root:

```cmd
vercel
vercel --prod
```

After deployment, check:

```text
https://your-project.vercel.app/health
https://your-project.vercel.app/docs
```

If Vercel reports `unmatched-function-pattern`, make sure `vercel.json` does not contain a `functions` entry for `app.py`. Vercel's `functions` config patterns must match files inside an `api/` directory, while this project uses Vercel's FastAPI auto-detection from the root `app.py`.

### Architecture On Vercel

```text
Browser / Parent App
        |
        v
Vercel Python Function (FastAPI)
        |
        v
Supabase Postgres via Transaction Pooler
```

For this backend, Supabase is used as Postgres storage. If the parent product already uses Supabase Auth, store that auth user id in this module's `external_user_id` field when registering users.

## Use As A Python Module

```python
from email_assistant import AppSettings, build_module

module = build_module(AppSettings.from_env())
user = module.register_user(
    tenant_id="tenant-a",
    email_address="alex@example.com",
    external_user_id="parent-user-123",
)

module.connect_mock_provider(tenant_id="tenant-a", user_id=user.id)
sync = module.sync_user(tenant_id="tenant-a", user_id=user.id)
emails = module.list_emails(tenant_id="tenant-a", user_id=user.id)
draft = module.generate_draft(
    tenant_id="tenant-a",
    user_id=user.id,
    email_id=emails[0].id,
)
```

## Configuration

Set these in `.env` or the host environment:

```text
EMAIL_ASSISTANT_DB_PATH=./data/email_assistant.db
EMAIL_ASSISTANT_DATABASE_URL=
EMAIL_ASSISTANT_SECRET_KEY=change-me
EMAIL_ASSISTANT_ENVIRONMENT=development
EMAIL_ASSISTANT_LLM_PROVIDER=local
EMAIL_ASSISTANT_PUBLIC_BASE_URL=http://localhost:8000
```

Optional OpenAI adapter:

```text
EMAIL_ASSISTANT_LLM_PROVIDER=openai
EMAIL_ASSISTANT_OPENAI_API_KEY=...
EMAIL_ASSISTANT_OPENAI_MODEL=...
```

If no hosted LLM is configured, the module uses `LocalHeuristicLLMClient`, which is deterministic and works offline. It is useful for development, tests, frontend integration, and demos.

## Security Model

- Every public storage method requires `tenant_id` and `user_id`.
- Cross-tenant access raises `TenantAccessError`.
- OAuth tokens are encrypted before being stored.
- Production mode requires the `cryptography` package and Fernet-backed encryption.
- Email content is treated as untrusted input.
- Prompt-injection patterns are flagged during triage.
- The assistant only creates drafts. It does not send email.

## Testing

Run the standard-library test suite:

```cmd
scripts\test.cmd
```

Current coverage checks:

- Token encryption roundtrip and tamper rejection.
- Tenant isolation.
- Mock provider sync.
- Idempotent repeated syncs.
- Prompt-injection detection.
- Draft creation.

## Current Status

Implemented:

- Phase 1 core: tenant users, credential encryption, OAuth-shaped state/callback flow.
- Phase 2 local foundation: sync orchestration and provider adapter protocol.
- Phase 3 core: guarded LLM gateway, structured triage result, token usage logging.
- Phase 4 foundation: tone profile settings and embeddable API/module layer.

Next production steps:

- Add Gmail and Outlook provider adapters.
- Add PostgreSQL storage adapter and migrations.
- Add Redis/Celery schedule configuration.
- Add cost-aware rate limits per tenant/user.
- Add a small dashboard that consumes the existing REST API.
