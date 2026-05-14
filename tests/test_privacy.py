import json
import tempfile
import unittest
from pathlib import Path

from privacy import CRYPTO_AVAILABLE, PrivacyError, crypto_status, decrypt_state, encrypt_state, is_encrypted_payload, key_path
from schema import default_state


class PrivacyTests(unittest.TestCase):
    @unittest.skipUnless(CRYPTO_AVAILABLE, "cryptography package is required for privacy encryption tests")
    def test_key_generation_creates_stable_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = default_state()
            envelope = encrypt_state(state, tmp)
            path = key_path(tmp)
            self.assertTrue(path.exists())
            key_data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(key_data["algorithm"], "AES-256-GCM")
            self.assertEqual(envelope["keyId"], key_data["keyId"])
            self.assertTrue(crypto_status(tmp)["keyExists"])

    @unittest.skipUnless(CRYPTO_AVAILABLE, "cryptography package is required for privacy encryption tests")
    def test_encrypt_decrypt_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = default_state()
            state["privacyMode"] = True
            envelope = encrypt_state(state, tmp)
            decrypted, warnings = decrypt_state(envelope, tmp)
            self.assertFalse(warnings)
            self.assertTrue(decrypted["privacyMode"])
            self.assertEqual(decrypted["prompts"][0]["title"], state["prompts"][0]["title"])

    @unittest.skipUnless(CRYPTO_AVAILABLE, "cryptography package is required for privacy encryption tests")
    def test_envelope_does_not_contain_prompt_plaintext(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = default_state()
            envelope = encrypt_state(state, tmp)
            text = json.dumps(envelope)
            self.assertTrue(is_encrypted_payload(envelope))
            self.assertNotIn("Cinematic portrait", text)
            self.assertNotIn("cyberpunk detective", text)
            self.assertNotIn("{{mood}}", text)

    @unittest.skipUnless(CRYPTO_AVAILABLE, "cryptography package is required for privacy encryption tests")
    def test_wrong_key_fails_readably(self):
        with tempfile.TemporaryDirectory() as one, tempfile.TemporaryDirectory() as two:
            envelope = encrypt_state(default_state(), one)
            encrypt_state(default_state(), two)
            with self.assertRaises(PrivacyError) as ctx:
                decrypt_state(envelope, two)
            self.assertIn("different local privacy key", str(ctx.exception))

    @unittest.skipUnless(CRYPTO_AVAILABLE, "cryptography package is required for privacy encryption tests")
    def test_missing_key_fails_readably(self):
        with tempfile.TemporaryDirectory() as tmp:
            envelope = encrypt_state(default_state(), tmp)
            Path(key_path(tmp)).unlink()
            with self.assertRaises(PrivacyError) as ctx:
                decrypt_state(envelope, tmp)
            self.assertIn("missing", str(ctx.exception).lower())


if __name__ == "__main__":
    unittest.main()
