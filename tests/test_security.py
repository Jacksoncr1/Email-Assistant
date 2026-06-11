import unittest

from email_assistant.exceptions import CryptoError
from email_assistant.security import TokenCipher


class TokenCipherTests(unittest.TestCase):
    def test_roundtrip_hides_plaintext(self):
        cipher = TokenCipher("test-secret-key-that-is-long-enough", environment="development")

        encrypted = cipher.encrypt("refresh-token-123")

        self.assertNotIn("refresh-token-123", encrypted)
        self.assertEqual(cipher.decrypt(encrypted), "refresh-token-123")

    def test_tampering_is_rejected(self):
        cipher = TokenCipher("test-secret-key-that-is-long-enough", environment="development", backend="dev")
        encrypted = cipher.encrypt("refresh-token-123")
        tampered = encrypted[:-2] + "aa"

        with self.assertRaises(CryptoError):
            cipher.decrypt(tampered)


if __name__ == "__main__":
    unittest.main()
