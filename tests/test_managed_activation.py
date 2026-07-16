from __future__ import annotations

import tomllib
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import managed_install
from managed_execution import (
    SMART_PROMPT_S3_PROFILE_FINGERPRINT,
    build_smart_prompt_s3_privacy_profile,
    build_smart_prompt_s3_server_adapters,
)


class SmartPromptManagedActivationTests(unittest.TestCase):
    def test_registry_metadata_matches_requirements_and_packages_browser_assets(self):
        root = Path(__file__).resolve().parents[1]
        project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
        requirements = [
            line.strip()
            for line in (root / "requirements.txt").read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]

        self.assertEqual(project["project"]["dependencies"], requirements)
        self.assertEqual(requirements[0], "helto-privacy==0.4.5")
        self.assertTrue(
            all(
                marker not in "\n".join(requirements)
                for marker in ("file:", "/home/", "@main", "@master", "git+")
            )
        )
        self.assertEqual(
            project["project"]["urls"]["Repository"],
            "https://github.com/helto4real/comfyui-helto-smartprompt",
        )
        self.assertEqual(
            project["tool"]["comfy"],
            {
                "PublisherId": "helto",
                "DisplayName": "Smart Prompt Manager",
                "Icon": "",
                "web": "web",
            },
        )
        self.assertTrue((root / "web/js/smart_prompt_managed_privacy.js").is_file())

    def test_complete_profile_and_server_adapter_set_match_exactly(self):
        profile = build_smart_prompt_s3_privacy_profile()
        adapters = build_smart_prompt_s3_server_adapters()
        self.assertEqual(profile.fingerprint, SMART_PROMPT_S3_PROFILE_FINGERPRINT)
        self.assertEqual(set(adapters), {slot.id for slot in profile.server_adapters})

    def test_atomic_install_registers_readers_binds_import_adapter_and_is_idempotent(self):
        profile = build_smart_prompt_s3_privacy_profile()
        pack = MagicMock()
        pack.profile = profile
        workflow = pack.workflow.return_value
        migration = pack.migration
        import_export = MagicMock()
        adapters = build_smart_prompt_s3_server_adapters(import_export=import_export)

        with (
            patch.object(managed_install, "_PACK", None),
            patch.object(managed_install, "_ADAPTERS", None),
            patch.object(managed_install, "_IMPORT_EXPORT", None),
            patch.object(
                managed_install,
                "register_legacy_reader_units",
            ) as register_readers,
            patch.object(
                managed_install,
                "build_smart_prompt_s3_privacy_profile",
                return_value=profile,
            ),
            patch.object(
                managed_install,
                "build_smart_prompt_s3_server_adapters",
                return_value=adapters,
            ),
            patch.object(
                managed_install,
                "SmartPromptImportExportAdapter",
                return_value=import_export,
            ),
            patch.object(managed_install, "install", return_value=pack) as install,
        ):
            first = managed_install.install_smart_prompt_privacy()
            second = managed_install.install_smart_prompt_privacy()

        self.assertIs(first, pack)
        self.assertIs(second, pack)
        register_readers.assert_called_once()
        install.assert_called_once_with(profile, adapters)
        import_export.bind.assert_called_once_with(
            workflow=workflow,
            migration=migration,
            profile=profile,
        )

    def test_route_registration_fails_closed_when_comfy_server_is_unavailable(self):
        with patch.object(managed_install, "_ROUTES_REGISTERED", False):
            self.assertFalse(managed_install.register_smart_prompt_managed_routes())


if __name__ == "__main__":
    unittest.main()
