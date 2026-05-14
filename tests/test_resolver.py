import unittest

from resolver import resolve_prompt, variables_used


VARIABLES = {
    "mood": {
        "mode": "random",
        "values": ["dreamy", "melancholic", "dramatic"],
        "fixedValue": None,
        "fallback": "dreamy",
        "description": "",
    },
    "character": {
        "mode": "random",
        "values": ["detective", "astronaut", "knight"],
        "fixedValue": None,
        "fallback": "",
        "description": "",
    },
    "lighting": {
        "mode": "fixed",
        "values": ["soft light", "golden hour"],
        "fixedValue": "golden hour",
        "fallback": "soft light",
        "description": "",
    },
    "empty": {
        "mode": "random",
        "values": [],
        "fixedValue": None,
        "fallback": "fallback value",
        "description": "",
    },
    "cycle": {
        "mode": "cycle",
        "values": ["one", "two", "three"],
        "fixedValue": None,
        "fallback": "",
        "description": "",
    },
}


class ResolverTests(unittest.TestCase):
    def test_seeded_random_is_deterministic(self):
        prompt = "A {{mood}} {{character}}"
        first = resolve_prompt(prompt, VARIABLES, seed=123, reroll=0)
        second = resolve_prompt(prompt, VARIABLES, seed=123, reroll=0)
        self.assertEqual(first["resolved_prompt"], second["resolved_prompt"])
        self.assertEqual(first["selected_values"], second["selected_values"])

    def test_reroll_changes_random_selection(self):
        prompt = "{{mood}}"
        values = {
            resolve_prompt(prompt, VARIABLES, seed=123, reroll=reroll)["resolved_prompt"]
            for reroll in range(10)
        }
        self.assertGreater(len(values), 1)

    def test_repeated_variable_is_consistent(self):
        result = resolve_prompt("{{mood}} and {{mood}}", VARIABLES, seed=7, reroll=2)
        left, right = result["resolved_prompt"].split(" and ")
        self.assertEqual(left, right)

    def test_fixed_value_wins(self):
        result = resolve_prompt("Light: {{lighting}}", VARIABLES, seed=1, reroll=99)
        self.assertEqual(result["resolved_prompt"], "Light: golden hour")

    def test_empty_values_can_use_fallback_and_warn(self):
        result = resolve_prompt("Use {{empty}}", VARIABLES, seed=1, reroll=0)
        self.assertEqual(result["resolved_prompt"], "Use fallback value")
        self.assertTrue(any("no values" in warning for warning in result["warnings"]))

    def test_missing_variable_is_preserved(self):
        result = resolve_prompt("A {{missing}} prompt", VARIABLES, seed=1, reroll=0)
        self.assertEqual(result["resolved_prompt"], "A {{missing}} prompt")
        self.assertEqual(result["missing_variables"], ["missing"])

    def test_invalid_variable_name_is_preserved(self):
        result = resolve_prompt("A {{bad name}} prompt", VARIABLES, seed=1, reroll=0)
        self.assertEqual(result["resolved_prompt"], "A {{bad name}} prompt")
        self.assertTrue(any("invalid" in warning for warning in result["warnings"]))

    def test_cycle_uses_cycle_state_and_reroll(self):
        result = resolve_prompt("{{cycle}}", VARIABLES, seed=0, reroll=1, cycle_state={"cycle": 1})
        self.assertEqual(result["resolved_prompt"], "three")

    def test_variables_used_keeps_order(self):
        self.assertEqual(variables_used("{{b}} {{a}} {{b}} {{bad name}}"), ["b", "a"])


if __name__ == "__main__":
    unittest.main()
