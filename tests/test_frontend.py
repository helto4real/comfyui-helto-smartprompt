from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SmartPromptManagerFrontendTests(unittest.TestCase):
    def test_seed_frontend_randomizes_live_seed_before_queue(self):
        source = (ROOT / "web/js/smart_prompt_manager.js").read_text(encoding="utf-8")

        self.assertIn("const SEED_MAX = Number.MAX_SAFE_INTEGER;", source)
        self.assertIn("function randomizeSpmSeedsBeforeQueue()", source)
        self.assertIn('liveSeedControlMode(node) !== "randomize"', source)
        self.assertIn("writeSpmSeedValue(node, seed)", source)
        self.assertIn("suspendSeedControlCallbacks(controlWidget)", source)
        self.assertIn("restoreQueuedSpmSeeds(queuedSeeds)", source)
        self.assertIn("app.queuePrompt = wrappedQueuePrompt", source)
        self.assertIn('scheduleSpmSeedQueuePatch("setup")', source)


if __name__ == "__main__":
    unittest.main()
