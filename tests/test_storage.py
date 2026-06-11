import tempfile
import unittest
from pathlib import Path

from email_assistant.exceptions import TenantAccessError
from email_assistant.models import ProviderMessage, TriageResult
from email_assistant.storage import SqliteStore, utcnow


class SqliteStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.store = SqliteStore(str(Path(self.tmpdir.name) / "assistant.db"))
        self.store.init_db()

    def test_user_and_email_are_tenant_scoped(self):
        user = self.store.create_user("tenant-a", "alex@example.com")
        message = ProviderMessage(
            provider="mock",
            provider_message_id="msg-1",
            sender="sender@example.com",
            recipient="alex@example.com",
            subject="Question",
            body="Could you help?",
            snippet="Could you help?",
            received_at=utcnow(),
        )
        triage = TriageResult(
            category="personal",
            priority="medium",
            summary="Could you help?",
            needs_reply=True,
            detected_intents=["reply_needed"],
            injection_detected=False,
            confidence=0.8,
        )

        email, created = self.store.upsert_email("tenant-a", user.id, message, triage)

        self.assertTrue(created)
        self.assertEqual(self.store.get_email("tenant-a", user.id, email.id).id, email.id)
        with self.assertRaises(TenantAccessError):
            self.store.get_email("tenant-b", user.id, email.id)


if __name__ == "__main__":
    unittest.main()
