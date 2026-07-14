import math
import unittest
from unittest.mock import patch

from nodes import SmartPromptManager
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

    def test_seed_input_exposes_comfy_seed_control(self):
        inputs = SmartPromptManager.INPUT_TYPES()
        required = inputs["required"]
        self.assertEqual(required["seed"][1]["control_after_generate"], "fixed")
        self.assertEqual(
            set(inputs["optional"]),
            {"privacy_mode_reference", "private_execution"},
        )
        self.assertTrue(inputs["optional"]["privacy_mode_reference"][1]["hidden"])
        self.assertTrue(inputs["optional"]["private_execution"][1]["hidden"])

    def test_legacy_spm_data_still_resolves_directly(self):
        state = self._state_with_prompt()
        result = SmartPromptManager().resolve(state_to_json(state), seed=1, reroll=0)
        self.assertEqual(result[0], "A dreamy portrait")

    def test_live_execution_requires_managed_subject_reference(self):
        state = self._state_with_prompt()
        with self.assertRaisesRegex(
            ValueError,
            "PRIVACY_SUBJECT_MODE_REFERENCE_INVALID",
        ):
            SmartPromptManager().resolve(
                state_to_json(state),
                seed=1,
                reroll=0,
                unique_id="7",
            )

    def test_private_subject_requires_managed_execution_reference(self):
        state = self._state_with_prompt()
        lease = object()
        context = unittest.mock.MagicMock()
        context.__enter__.return_value = lease
        context.__exit__.return_value = False
        with (
            patch("nodes.consume_smart_prompt_subject_mode", return_value=context),
            patch(
                "nodes.smart_prompt_subject_requires_private_execution",
                return_value=True,
            ),
        ):
            with self.assertRaisesRegex(
                ValueError,
                "PRIVACY_EXECUTION_REFERENCE_INVALID",
            ):
                SmartPromptManager().resolve(
                    state_to_json(state),
                    seed=1,
                    reroll=0,
                    unique_id="7",
                    privacy_mode_reference="{}",
                )

    def test_private_subject_dispatches_only_the_managed_reference(self):
        state = self._state_with_prompt()
        expected = ("resolved", "raw", "name", "variables", "selected", "warnings")
        lease = object()
        context = unittest.mock.MagicMock()
        context.__enter__.return_value = lease
        context.__exit__.return_value = False
        with (
            patch("nodes.consume_smart_prompt_subject_mode", return_value=context),
            patch(
                "nodes.smart_prompt_subject_requires_private_execution",
                return_value=True,
            ),
            patch(
                "nodes.dispatch_smart_prompt_managed_execution",
                return_value=expected,
            ) as dispatch,
        ):
            actual = SmartPromptManager().resolve(
                state_to_json(state),
                seed=9,
                reroll=2,
                unique_id="7",
                privacy_mode_reference="{}",
                private_execution='{"reference":"opaque"}',
            )
        self.assertEqual(actual, expected)
        dispatch.assert_called_once_with(
            '{"reference":"opaque"}',
            subject_id="7",
            seed=9,
            reroll=2,
        )

    def test_protected_state_never_falls_back_to_public_parsing(self):
        envelope = {
            "encrypted": True,
            "ciphertext": "ciphertext",
        }
        with self.assertRaisesRegex(
            ValueError,
            "PRIVACY_EXECUTION_REFERENCE_INVALID",
        ):
            SmartPromptManager().resolve(
                state_to_json(envelope),
                seed=1,
                reroll=0,
            )

    def test_private_execution_disables_comfy_cache(self):
        changed = SmartPromptManager.IS_CHANGED(
            state_to_json(self._state_with_prompt()),
            seed=1,
            reroll=0,
            private_execution='{"reference":"opaque"}',
        )
        self.assertTrue(math.isnan(changed))


if __name__ == "__main__":
    unittest.main()
