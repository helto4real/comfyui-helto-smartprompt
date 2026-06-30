import json
import unittest
from unittest.mock import patch

from nodes import SmartPromptManager
from privacy import ALGORITHM, ENVELOPE_SCHEMA
from schema import default_state, state_to_json


class SmartPromptManagerNodeTests(unittest.TestCase):
    def _state_with_prompt(self, text="A {{mood}} portrait"):
        state = default_state()
        state["selectedPromptId"] = "prompt1"
        state["prompts"] = [
            {
                "id": "prompt1",
                "title": "Cache test",
                "text": text,
                "folderId": "",
                "tags": [],
                "description": "",
                "favorite": False,
                "locked": False,
                "hidden": False,
                "createdAt": "2026-01-01T00:00:00Z",
                "updatedAt": "2026-01-01T00:00:00Z",
            }
        ]
        state["variables"] = {
            "mood": {
                "mode": "fixed",
                "values": ["dreamy"],
                "fixedValue": "dreamy",
                "fallback": "",
                "description": "",
            }
        }
        return state

    def _extra_pnginfo(self, node_id, spm_data):
        return {
            "workflow": {
                "nodes": [
                    {
                        "id": node_id,
                        "type": "SmartPromptManager",
                        "widgets_values": [spm_data, 123, 0],
                    }
                ]
            }
        }

    def test_seed_input_exposes_comfy_seed_control(self):
        required = SmartPromptManager.INPUT_TYPES()["required"]
        self.assertEqual(required["seed"][1]["control_after_generate"], "fixed")

    def test_legacy_spm_data_still_resolves_directly(self):
        state = self._state_with_prompt()
        result = SmartPromptManager().resolve(state_to_json(state), seed=1, reroll=0)
        self.assertEqual(result[0], "A dreamy portrait")

    def test_cache_token_resolves_saved_workflow_spm_data(self):
        state = self._state_with_prompt()
        token = "spm-cache-v1:" + "a" * 64
        result = SmartPromptManager().resolve(
            token,
            seed=1,
            reroll=0,
            unique_id="7",
            extra_pnginfo=self._extra_pnginfo(7, state_to_json(state)),
        )
        self.assertEqual(result[0], "A dreamy portrait")

    def test_cache_token_resolves_encrypted_workflow_spm_data(self):
        state = self._state_with_prompt()
        envelope = {
            "version": 1,
            "schema": ENVELOPE_SCHEMA,
            "encrypted": True,
            "algorithm": ALGORITHM,
            "keyId": "test-key",
            "nonce": "nonce",
            "ciphertext": "ciphertext",
        }
        token = "spm-cache-v1:" + "b" * 64
        with patch("nodes.decrypt_state", return_value=(state, [])) as decrypt_state:
            result = SmartPromptManager().resolve(
                token,
                seed=1,
                reroll=0,
                unique_id="7",
                extra_pnginfo=self._extra_pnginfo("7", envelope),
            )
        decrypt_state.assert_called_once_with(envelope)
        self.assertEqual(result[0], "A dreamy portrait")

    def test_cache_token_without_workflow_metadata_warns_readably(self):
        token = "spm-cache-v1:" + "c" * 64
        result = SmartPromptManager().resolve(token, seed=1, reroll=0, unique_id="7", extra_pnginfo={})
        warnings = json.loads(result[5])["warnings"]
        self.assertTrue(any("cache token" in warning.lower() for warning in warnings))
        self.assertEqual(result[0], "")


if __name__ == "__main__":
    unittest.main()
