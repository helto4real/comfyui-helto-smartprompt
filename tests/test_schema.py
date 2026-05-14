import json
import unittest

from schema import default_state, merge_library, normalize_state, parse_state, state_to_json


class SchemaTests(unittest.TestCase):
    def test_parse_malformed_json_uses_defaults(self):
        state, warnings = parse_state("{not json")
        self.assertEqual(state["version"], 1)
        self.assertTrue(warnings)
        self.assertTrue(state["prompts"])

    def test_normalize_removes_invalid_variable_names(self):
        state, warnings = normalize_state(
            {
                "variables": {
                    "good-name": {"mode": "random", "values": ["ok"]},
                    "bad name": {"mode": "random", "values": ["no"]},
                }
            }
        )
        self.assertIn("good-name", state["variables"])
        self.assertNotIn("bad name", state["variables"])
        self.assertTrue(any("invalid variable" in warning.lower() for warning in warnings))

    def test_state_round_trip(self):
        state = default_state()
        parsed, warnings = parse_state(state_to_json(state))
        self.assertFalse(warnings)
        self.assertEqual(parsed["version"], 1)
        self.assertEqual(len(parsed["prompts"]), len(state["prompts"]))

    def test_merge_avoids_folder_prompt_and_variable_conflicts(self):
        current = {
            "version": 1,
            "folders": [{"id": "folder1", "name": "Portraits"}],
            "prompts": [
                {
                    "id": "prompt1",
                    "title": "Cinematic portrait",
                    "text": "{{mood}}",
                    "folderId": "folder1",
                    "tags": [],
                    "description": "",
                    "favorite": False,
                    "locked": False,
                    "createdAt": "2026-01-01T00:00:00Z",
                    "updatedAt": "2026-01-01T00:00:00Z",
                }
            ],
            "variables": {"mood": {"mode": "random", "values": ["dreamy"], "fixedValue": None, "fallback": "", "description": ""}},
            "selectedFolderId": "all",
            "selectedPromptId": "prompt1",
        }
        incoming = json.loads(json.dumps(current))
        incoming["variables"]["mood"]["values"] = ["dramatic"]
        merged, warnings = merge_library(current, incoming)
        self.assertEqual(len(merged["folders"]), 2)
        self.assertEqual(len(merged["prompts"]), 2)
        self.assertNotEqual(merged["folders"][0]["id"], merged["folders"][1]["id"])
        self.assertNotEqual(merged["prompts"][0]["id"], merged["prompts"][1]["id"])
        self.assertNotEqual(merged["prompts"][0]["title"], merged["prompts"][1]["title"])
        self.assertTrue(any("not overwritten" in warning for warning in warnings))


if __name__ == "__main__":
    unittest.main()
