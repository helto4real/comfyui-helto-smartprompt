import unittest

from nodes import SmartPromptManager


class SmartPromptManagerNodeTests(unittest.TestCase):
    def test_seed_input_exposes_comfy_seed_control(self):
        required = SmartPromptManager.INPUT_TYPES()["required"]
        self.assertEqual(required["seed"][1]["control_after_generate"], "fixed")


if __name__ == "__main__":
    unittest.main()
