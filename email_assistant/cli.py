from __future__ import annotations

import argparse
from dataclasses import asdict
from pprint import pprint

from .assistant import build_module
from .config import AppSettings
from .security import generate_secret_key


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AI email assistant module utilities.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("generate-secret", help="Print a new EMAIL_ASSISTANT_SECRET_KEY.")
    subparsers.add_parser("init-db", help="Create database tables.")

    demo = subparsers.add_parser("demo", help="Run a local mock inbox sync and draft.")
    demo.add_argument("--tenant-id", default="demo-tenant")
    demo.add_argument("--email", default="demo@example.com")

    args = parser.parse_args(argv)

    if args.command == "generate-secret":
        print(generate_secret_key())
        return 0

    settings = AppSettings.from_env()
    module = build_module(settings)

    if args.command == "init-db":
        print(f"Database ready at {settings.normalized_db_path}")
        return 0

    if args.command == "demo":
        user = module.register_user(tenant_id=args.tenant_id, email_address=args.email)
        module.connect_mock_provider(tenant_id=args.tenant_id, user_id=user.id)
        sync = module.sync_user(tenant_id=args.tenant_id, user_id=user.id)
        emails = module.list_emails(tenant_id=args.tenant_id, user_id=user.id)
        draft = module.generate_draft(tenant_id=args.tenant_id, user_id=user.id, email_id=emails[0].id)
        pprint(
            {
                "user": asdict(user),
                "sync": asdict(sync),
                "first_email": asdict(emails[0]),
                "draft": asdict(draft),
            }
        )
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2
