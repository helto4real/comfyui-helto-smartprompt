from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
TEST_MODULE = ROOT / "tests" / "smart_prompt_privacy_adapters.test.mjs"
IMPORT_EXPORT_TEST_MODULE = (
    ROOT / "tests" / "smart_prompt_import_export_adapters.test.mjs"
)
EXECUTION_TEST_MODULE = ROOT / "tests" / "smart_prompt_execution_adapters.test.mjs"
COORDINATOR_TEST_MODULE = ROOT / "tests" / "smart_prompt_privacy_coordinator.test.mjs"
MANAGED_CONNECTION_MODULE = ROOT / "web" / "js" / "smart_prompt_managed_privacy.js"
LIVE_MANAGER_MODULE = ROOT / "web" / "js" / "smart_prompt_manager.js"


class SmartPromptManagedPrivacyFrontendTests(unittest.TestCase):
    def test_browser_adapter_contract(self):
        result = subprocess.run(
            [
                "node",
                "--test",
                "--experimental-default-type=module",
                str(TEST_MODULE),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_import_export_browser_adapter_contract(self):
        result = subprocess.run(
            ["node", str(IMPORT_EXPORT_TEST_MODULE)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_execution_browser_adapter_contract(self):
        result = subprocess.run(
            ["node", str(EXECUTION_TEST_MODULE)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_product_privacy_coordinator(self):
        result = subprocess.run(
            ["node", str(COORDINATOR_TEST_MODULE)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_live_connection_is_exact_and_has_no_local_fallback(self):
        managed = MANAGED_CONNECTION_MODULE.read_text(encoding="utf-8")
        live = LIVE_MANAGER_MODULE.read_text(encoding="utf-8")
        self.assertIn('export const SMART_PROMPT_PROFILE_ID = "helto.smart-prompt-manager";', managed)
        self.assertIn(
            '"5a352fd3fb086cd3418039368457e7a2fbd8b4ae81aa0deae6151d8bcbd22352"',
            managed,
        )
        self.assertIn('["ready", "activation-required", "active"]', managed)
        self.assertIn("suiteManifestDigest: suite.suiteManifestDigest", managed)
        self.assertIn("adapterFactories:", managed)
        self.assertIn('pack.workflow(WORKFLOW_RESOURCE_ID)', managed)
        self.assertIn('pack.mode(MODE_RESOURCE_ID)', managed)
        self.assertIn('pack.execution(EXECUTION_RESOURCE_ID)', managed)
        self.assertIn("registerSmartPromptManagedOwner(node, managedProductBridge())", live)
        for retired in (
            "/helto_spm/privacy",
            "getStoredPrivacyToken",
            "crypto.subtle",
            "SPM_CACHE_TOKEN_PREFIX",
            "installSpmGraphToPromptPatch",
            "dataWidget.serializeValue = async function",
        ):
            self.assertNotIn(retired, live)


if __name__ == "__main__":
    unittest.main()
