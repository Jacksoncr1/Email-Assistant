import tempfile
import unittest
from pathlib import Path

from email_assistant import AppSettings, build_module
from email_assistant.exceptions import TenantAccessError


class AssistantWorkflowTests(unittest.TestCase):
    def build_test_module(self):
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        settings = AppSettings(
            db_path=str(Path(tmpdir.name) / "assistant.db"),
            secret_key="test-secret-key-that-is-long-enough",
            environment="development",
            llm_provider="local",
        )
        return build_module(settings)

    def test_mock_sync_triages_and_drafts(self):
        module = self.build_test_module()
        user = module.register_user(tenant_id="tenant-a", email_address="alex@example.com")
        module.connect_mock_provider(tenant_id="tenant-a", user_id=user.id)

        sync = module.sync_user(tenant_id="tenant-a", user_id=user.id)
        self.assertEqual(sync.messages_seen, 4)
        self.assertEqual(sync.messages_stored, 4)

        second_sync = module.sync_user(tenant_id="tenant-a", user_id=user.id)
        self.assertEqual(second_sync.messages_stored, 0)

        emails = module.list_emails(tenant_id="tenant-a", user_id=user.id)
        self.assertEqual(len(emails), 4)
        self.assertTrue(any(email.injection_detected for email in emails))
        self.assertTrue(any(email.category == "billing" for email in emails))

        draft = module.generate_draft(tenant_id="tenant-a", user_id=user.id, email_id=emails[0].id)
        self.assertEqual(draft.status, "drafted")
        self.assertTrue(draft.subject.startswith("Re:"))
        self.assertIsNotNone(draft.provider_draft_id)

    def test_tenant_isolation_blocks_cross_tenant_access(self):
        module = self.build_test_module()
        user = module.register_user(tenant_id="tenant-a", email_address="alex@example.com")

        with self.assertRaises(TenantAccessError):
            module.list_emails(tenant_id="tenant-b", user_id=user.id)


if __name__ == "__main__":
    unittest.main()
