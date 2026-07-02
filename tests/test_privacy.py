import json
import os
import tempfile
import unittest
from unittest.mock import patch

import helto_privacy.keystore as hp_keystore
from helto_privacy.guard import PRIVACY_TOKEN_HEADER, check_privacy_token

from privacy import (
    ALGORITHM,
    CRYPTO_AVAILABLE,
    ENVELOPE_SCHEMA,
    LEGACY_ENVELOPE_SCHEMA,
    PrivacyError,
    crypto_status,
    decrypt_state,
    encrypt_state,
    is_encrypted_payload,
    is_unsupported_encrypted_payload,
)
from schema import default_state


PASSWORD = "privacy-password"


class PrivacyTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = self._tmp.name
        self._env = patch.dict(
            os.environ,
            {
                hp_keystore.KEYSTORE_ENV: os.path.join(root, "privacy_keystore.json"),
                hp_keystore.SESSION_DIR_ENV: os.path.join(root, "session"),
            },
        )
        self._scrypt = patch.object(hp_keystore, "SCRYPT_N", 2**12)
        self._env.start()
        self._scrypt.start()
        self.addCleanup(self._scrypt.stop)
        self.addCleanup(self._env.stop)
        self.addCleanup(self._tmp.cleanup)

    @unittest.skipUnless(CRYPTO_AVAILABLE, "cryptography package is required for privacy encryption tests")
    def test_status_uses_shared_keystore_without_local_key_file(self):
        status = crypto_status()
        self.assertEqual(ENVELOPE_SCHEMA, "helto.smart-prompt-manager")
        self.assertTrue(status["available"])
        self.assertEqual(status["algorithm"], ALGORITHM)
        self.assertFalse(status["keyExists"])
        self.assertEqual(status["keyPath"], "")
        self.assertFalse(status["keystoreInitialized"])

    @unittest.skipUnless(CRYPTO_AVAILABLE, "cryptography package is required for privacy encryption tests")
    def test_encrypt_requires_initialized_keystore(self):
        with self.assertRaises(PrivacyError) as ctx:
            encrypt_state(default_state())
        self.assertIn("PRIVACY_KEYSTORE_UNINITIALIZED", str(ctx.exception))

    @unittest.skipUnless(CRYPTO_AVAILABLE, "cryptography package is required for privacy encryption tests")
    def test_encrypt_decrypt_round_trip_through_shared_keystore(self):
        hp_keystore.initialize_keystore(PASSWORD)
        state = default_state()
        state["privacyMode"] = True

        envelope = encrypt_state(state)
        text = json.dumps(envelope)
        self.assertTrue(is_encrypted_payload(envelope))
        self.assertEqual(envelope["schema"], ENVELOPE_SCHEMA)
        self.assertNotIn("Cinematic portrait", text)
        self.assertNotIn("cyberpunk detective", text)
        self.assertNotIn("{{mood}}", text)

        decrypted, warnings = decrypt_state(envelope)
        self.assertFalse(warnings)
        self.assertTrue(decrypted["privacyMode"])
        self.assertEqual(decrypted["prompts"][0]["title"], state["prompts"][0]["title"])

    @unittest.skipUnless(CRYPTO_AVAILABLE, "cryptography package is required for privacy encryption tests")
    def test_locked_keystore_fails_readably(self):
        hp_keystore.initialize_keystore(PASSWORD)
        envelope = encrypt_state(default_state())
        hp_keystore.lock_keystore()

        with self.assertRaises(PrivacyError) as decrypt_ctx:
            decrypt_state(envelope)
        self.assertIn("PRIVACY_LOCKED", str(decrypt_ctx.exception))

        with self.assertRaises(PrivacyError) as encrypt_ctx:
            encrypt_state(default_state())
        self.assertIn("PRIVACY_LOCKED", str(encrypt_ctx.exception))

    @unittest.skipUnless(CRYPTO_AVAILABLE, "cryptography package is required for privacy encryption tests")
    def test_privacy_token_guard_accepts_only_unlocked_session_token(self):
        class Request:
            def __init__(self, headers=None, cookies=None):
                self.headers = headers or {}
                self.cookies = cookies or {}

        self.assertIsNone(check_privacy_token(Request()))

        result = hp_keystore.initialize_keystore(PASSWORD)
        token = result["token"]

        denied = check_privacy_token(Request())
        self.assertEqual(denied["status"], 401)
        self.assertIn("PRIVACY_TOKEN_REQUIRED", denied["error"])

        denied = check_privacy_token(Request(headers={PRIVACY_TOKEN_HEADER: "wrong"}))
        self.assertEqual(denied["status"], 401)
        self.assertIn("PRIVACY_TOKEN_REQUIRED", denied["error"])

        self.assertIsNone(check_privacy_token(Request(headers={PRIVACY_TOKEN_HEADER: token})))

        hp_keystore.lock_keystore()
        denied = check_privacy_token(Request(headers={PRIVACY_TOKEN_HEADER: token}))
        self.assertEqual(denied["status"], 401)
        self.assertIn("PRIVACY_LOCKED", denied["error"])

    @unittest.skipUnless(CRYPTO_AVAILABLE, "cryptography package is required for privacy encryption tests")
    def test_old_encrypted_schema_is_rejected(self):
        payload = {
            "version": 1,
            "schema": LEGACY_ENVELOPE_SCHEMA,
            "encrypted": True,
            "algorithm": ALGORITHM,
            "keyId": "legacy-key",
            "nonce": "nonce",
            "ciphertext": "ciphertext",
        }

        self.assertFalse(is_encrypted_payload(payload))
        self.assertTrue(is_unsupported_encrypted_payload(payload))
        with self.assertRaises(PrivacyError) as ctx:
            decrypt_state(payload)
        self.assertIn("unsupported legacy privacy schema", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
