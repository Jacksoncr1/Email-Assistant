# Multi-Tenant AI Email Assistant Module

An enterprise-grade, asynchronous, multi-tenant AI engine designed to be embedded into customer-facing applications. This module allows parent applications to securely connect to consumer inboxes (Gmail/Outlook), execute background triage, monitor usage metrics, and generate context-aware email drafts matching user-defined tone profiles.

Built to scale horizontally, this service leverages decoupled worker queues, encrypted token management, and strict data isolation parameters.

---

## System Architecture

This module is architected as an event-driven microservice to ensure high availability, data security, and API rate-limit resilience across thousands of concurrent consumer inboxes.

              ┌────────────────────────────────────────┐
              │       Parent Application / UI          │
              └──────────────────┬─────────────────────┘
                                 │ (REST API / Webhooks)
                                 ▼
                    ┌────────────────────────┐
                    │    Module API Gateway  │
                    └────────────┬───────────┘
                                 │
                    ┌────────────▼───────────┐
                    │  Task Queue (Celery)   │
                    └────────────┬───────────┘
                                 │ (Distributed Tasks)
     ┌───────────────────────────┼───────────────────────────┐
     ▼                           ▼                           ▼
┌─────────────────┐         ┌─────────────────┐         ┌─────────────────┐
│  Sync Worker 1  │         │  Sync Worker 2  │         │  Sync Worker N  │
└────────┬────────┘         └────────┬────────┘         └────────┬────────┘
│                           │                           │
└───────────────────────────┼───────────────────────────┘
▼
┌───────────────────────────────────────┐
│         Central Services Layer        │
├───────────────────────────────────────┤
│  • AES-256 Token Encryption Vault     │
│  • PostgreSQL Multi-Tenant DB         │
│  • LLM Gateway & Token Rate-Limiter   │
└───────────────────────────────────────┘


### Core Components
1. **OAuth 2.0 Web Callback Handler:** Manages the multi-tenant web redirection flow, capturing user authorization codes securely from Google/Microsoft endpoints.
2. **Distributed Sync Workers:** Background daemons (Celery + Redis) that independently poll inboxes, handling service providers' API rate limits and execution retries.
3. **Data Isolation & Encryption Vault:** A PostgreSQL persistence layer enforcing row-level security combined with application-layer encryption for user refresh tokens.
4. **Guardrailed LLM Gateway:** An outbound API wrapper that enforces JSON schemas, strips injection attempts, and logs real-time token/cost footprints per user.

---

## Feature Roadmap & Development Phases

### Phase 1: Multi-Tenant Authentication & Token Security
* [ ] Implement an OAuth 2.0 web-redirection login pipeline (FastAPI/Flask endpoint).
* [ ] Design an application-layer cryptography utility using AES-256 (via `cryptography.fernet`) to encrypt/decrypt OAuth tokens at the database boundary.
* [ ] Create a relational, multi-tenant schema mapping users, credentials, and processing ledgers using strict foreign key isolation.

### Phase 2: Scalable Sync & Ingestion Infrastructure
* [ ] Set up a Celery task queuing system backed by Redis for concurrent task processing.
* [ ] Build a distributed background cron worker that schedules rolling inbox checks (e.g., every 10 minutes per active tenant).
* [ ] Implement an API request coordinator that respects provider rate limits (exponential backoff and jitter algorithms).

### Phase 3: Defensive LLM Pipeline & Safety Controls
* [ ] Design structured JSON output validation schemas (OpenAI Structured Outputs / Pydantic) to ensure predictable model triage categorizations.
* [ ] Implement an LLM wrapper that sanitizes email body inputs inside structural XML tags to mitigate prompt-injection vulnerabilities.
* [ ] Implement a database middleware counter tracking running token usage per `user_id` to prevent billing exploits.

### Phase 4: Customization Engine & Embedded UX (SDK Layer)
* [ ] Expose configuration endpoints allowing users to update tone profiles (sliders, custom directives) dynamically via DB state adjustments.
* [ ] Build a local mock dashboard interface to demonstrate webhook interactions and audit trails.

---

## Production Tech Stack

* **Language:** Python 3.11+
* **Framework Interface:** FastAPI (High-performance, async-first web routing)
* **Task Management:** Celery + Redis
* **Database:** PostgreSQL (Robust multi-tenant indexing and transaction tracking)
* **Encryption:** `cryptography` (Python Fernet primitives)
* **LLM Engine:** LiteLLM / OpenAI SDK with Pydantic output parsing

---

## Security & Compliance Architecture

Because this module operates on private user communication data, it adheres to strict operational boundaries:

> **Data Isolation:** Every transaction, log query, and ledger lookup contains a mandatory `user_id` context filter. Cross-tenant data leaks are guarded against at the application routing layer.

> **Write Sandboxing:** The AI engine does not possess permissions to transmit emails directly. Outbound actions are strictly restricted to writing payloads into the host inbox's native **Drafts** container, preserving an absolute human-in-the-loop requirement.

---

## Modular Setup & Installation

*(Instructions to be completed as development progresses)*
1. Provision a PostgreSQL instance and apply the structural migrations inside `/database/migrations`.
2. Configure environmental variables inside `.env` including your master AES encryption keys, provider client secrets, and LLM endpoints.
3. Initialize the distributed task broker daemon: `celery -A tasks worker --loglevel=info`.