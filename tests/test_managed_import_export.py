from __future__ import annotations

import asyncio
import base64
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import helto_privacy.envelope as shared_envelope
import helto_privacy.guard as shared_guard
import helto_privacy.keystore as shared_keystore
import helto_privacy.migration as shared_migration
import helto_privacy.runtime as shared_runtime
import helto_privacy.suite_runtime as shared_suite_runtime
from helto_privacy import (
    LegacyKeyFormat,
    MigrationError,
    SMART_PROMPT_V1_JSON_KEY_IMPORT_ID,
    protected_envelope_text,
    register_legacy_reader_units,
    smart_prompt_v1_export_reader_unit,
    smart_prompt_v1_reader_unit,
)
from helto_privacy.guard import authorize_privacy_request

from managed_import_export import (
    IMPORT_MERGE_OPERATION_ID,
    IMPORT_REPLACE_OPERATION_ID,
    PROMPT_LIBRARY_OPERATION_ADAPTER_ID,
    SMART_PROMPT_S2_PROFILE_FINGERPRINT,
    SmartPromptImportExportAdapter,
    SmartPromptImportExportAuthorizations,
    SmartPromptImportExportError,
    build_smart_prompt_s2_privacy_profile,
    build_smart_prompt_s2_server_adapters,
    parse_smart_prompt_import,
)
from managed_import_export_routes import (
    SMART_PROMPT_MANAGED_IMPORT_ROUTES,
    SmartPromptImportExportRoutes,
)
from managed_privacy import PROMPT_LIBRARY_FIELD_ID, PROMPT_LIBRARY_WORKFLOW_RESOURCE_ID


BARE_FIXTURE = Path(__file__).with_name("smart_prompt_v1_state.fixture.json")
EXPORT_FIXTURE = Path(__file__).with_name("smart_prompt_v1_export.fixture.json")


class Request:
    def __init__(self, token: str, payload=None) -> None:
        self.headers = {"X-Helto-Privacy-Token": token}
        self.cookies = {}
        self._payload = payload

    async def json(self):
        return self._payload


def library_state(*, private: bool, title: str = "Current") -> dict[str, object]:
    return {
        "version": 1,
        "selectedFolderId": "all",
        "selectedPromptId": "prompt_current",
        "search": "",
        "privacyMode": private,
        "folders": [{"id": "folder_current", "name": "Portraits", "hidden": False}],
        "prompts": [{
            "id": "prompt_current", "title": title, "text": f"Prompt {title}",
            "description": "", "folderId": "folder_current", "tags": [],
            "favorite": False, "locked": False, "hidden": False,
            "createdAt": "2026-07-01T00:00:00Z",
            "updatedAt": "2026-07-01T00:00:00Z",
        }],
        "variables": {}, "cycleState": {}, "ui": {"collapsedSections": {}},
    }


class SmartPromptExternalMigrationTests(unittest.TestCase):
    def test_profile_fingerprint_contract_and_managed_routes_are_exact(self):
        profile = build_smart_prompt_s2_privacy_profile()
        self.assertEqual(profile.fingerprint, SMART_PROMPT_S2_PROFILE_FINGERPRINT)
        self.assertEqual(
            set(build_smart_prompt_s2_server_adapters()),
            set(profile.server_adapter_contracts),
        )
        self.assertEqual(len(SMART_PROMPT_MANAGED_IMPORT_ROUTES), 2)
        source = Path("managed_import_export_routes.py").read_text(encoding="utf-8")
        self.assertNotIn("PromptServer", source)
        self.assertNotIn("migration.read", source)
        self.assertNotIn("migration.complete", source)

    def test_genuine_bare_and_export_fixtures_are_exactly_classified(self):
        bare = json.loads(BARE_FIXTURE.read_text(encoding="utf-8"))
        export = json.loads(EXPORT_FIXTURE.read_text(encoding="utf-8"))
        bare_raw = json.dumps(bare["envelope"], separators=(",", ":"))
        export_raw = json.dumps(export["package"], separators=(",", ":"))
        self.assertEqual(parse_smart_prompt_import(bare_raw).legacy_binding_id, "bare-envelope")
        self.assertEqual(parse_smart_prompt_import(export_raw).legacy_binding_id, "export-wrapper")
        self.assertEqual(bare_raw, json.dumps(bare["envelope"], separators=(",", ":")))
        self.assertEqual(export_raw, json.dumps(export["package"], separators=(",", ":")))

    def test_plaintext_and_current_prepare_have_no_receipt_or_external_transaction(self):
        with self._installed() as (pack, adapter, token, _root):
            public = json.dumps(library_state(private=False), sort_keys=True, separators=(",", ":"))
            plain = adapter.prepare(
                "node-1", "request-plain", json.dumps(library_state(private=True, title="Imported")),
                False, public, False, operation_id=IMPORT_REPLACE_OPERATION_ID,
                authorizations=self._authorizations(pack, token, IMPORT_REPLACE_OPERATION_ID),
            )
            self.assertFalse(plain.state["privacyMode"])
            self.assertIsNone(plain.transaction_id)
            self.assertIsNone(plain.receipt_id)
            self.assertEqual(shared_migration._load_state()["externalTransactions"], {})

            auth = self._authorizations(pack, token, IMPORT_REPLACE_OPERATION_ID)
            protect = self._snapshot_protect(pack, token)
            exact = protected_envelope_text(pack.workflow(PROMPT_LIBRARY_WORKFLOW_RESOURCE_ID).protect(
                PROMPT_LIBRARY_FIELD_ID, library_state(private=True, title="Current import"),
                protect,
            )) + "\n"
            destination = protected_envelope_text(pack.workflow(PROMPT_LIBRARY_WORKFLOW_RESOURCE_ID).protect(
                PROMPT_LIBRARY_FIELD_ID, library_state(private=True), protect,
            ))
            current = adapter.prepare(
                "node-2", "request-current", exact, False, destination, True,
                operation_id=IMPORT_REPLACE_OPERATION_ID, authorizations=auth,
            )
            self.assertEqual(current.protected_value, exact)
            self.assertIsNone(current.transaction_id)
            private_plain_first = adapter.prepare(
                "node-plain-private", "request-plain-private",
                json.dumps(library_state(private=False, title="Plain private")),
                False, destination, True,
                operation_id=IMPORT_REPLACE_OPERATION_ID, authorizations=auth,
            )
            private_plain_second = adapter.prepare(
                "node-plain-private", "request-plain-private",
                json.dumps(library_state(private=False, title="Plain private")),
                False, destination, True,
                operation_id=IMPORT_REPLACE_OPERATION_ID, authorizations=auth,
            )
            self.assertEqual(private_plain_first.state, private_plain_second.state)
            self.assertIsNone(private_plain_first.protected_value)
            self.assertIsNone(private_plain_second.protected_value)

    def test_legacy_prepare_reexport_finalize_issues_no_early_receipt(self):
        with self._installed() as (pack, adapter, token, root):
            token = self._import_fixture_key(pack, token, root)
            raw = json.dumps(json.loads(BARE_FIXTURE.read_text())["envelope"], separators=(",", ":"))
            destination = self._private_snapshot(pack, token, IMPORT_REPLACE_OPERATION_ID)
            auth = self._authorizations(pack, token, IMPORT_REPLACE_OPERATION_ID)
            prepared = adapter.prepare(
                "node-3", "request-legacy", raw, True, destination, True,
                operation_id=IMPORT_REPLACE_OPERATION_ID, authorizations=auth,
            )
            self.assertIsNone(prepared.receipt_id)
            self.assertEqual(prepared.disposition, "prepared")
            self.assertEqual(
                pack.migration.obligation(
                    adapter.resume(
                        "node-3", prepared.transaction_id, prepared.resume_token,
                        prepared.binding_id, operation_id=IMPORT_REPLACE_OPERATION_ID,
                        authorization=auth.operation,
                    ).status.obligation_id
                ).disposition,
                "unresolved",
            )
            committed = protected_envelope_text(
                pack.workflow(PROMPT_LIBRARY_WORKFLOW_RESOURCE_ID).protect(
                    PROMPT_LIBRARY_FIELD_ID,
                    prepared.state,
                    self._snapshot_protect(pack, token),
                )
            )
            reexport = adapter.reexport(
                "node-3", prepared.transaction_id, prepared.resume_token,
                prepared.binding_id, committed, True,
                operation_id=IMPORT_REPLACE_OPERATION_ID, authorizations=auth,
            )
            self.assertEqual(len(reexport.digest), 64)
            self.assertNotIn("receipt", reexport.text.lower())
            receipt = adapter.finalize(
                "node-3", prepared.transaction_id, prepared.resume_token,
                prepared.binding_id, committed, reexport.digest, True,
                operation_id=IMPORT_REPLACE_OPERATION_ID, authorizations=auth,
            )
            self.assertTrue(receipt.id.startswith("hp-receipt-"))
            completed = adapter.status(
                "node-3", prepared.transaction_id, prepared.resume_token,
                prepared.binding_id, operation_id=IMPORT_REPLACE_OPERATION_ID,
                authorization=auth.operation,
            )
            self.assertEqual(completed.disposition, "migrated")
            self.assertEqual(completed.receipt_id, receipt.id)

    def test_export_wrapper_public_merge_preserves_destination_mode(self):
        with self._installed() as (pack, adapter, token, root):
            token = self._import_fixture_key(pack, token, root)
            raw = json.dumps(json.loads(EXPORT_FIXTURE.read_text())["package"], separators=(",", ":"))
            destination = json.dumps(library_state(private=False), sort_keys=True, separators=(",", ":"))
            auth = self._authorizations(pack, token, IMPORT_MERGE_OPERATION_ID)
            prepared = adapter.prepare(
                "node-4", "request-merge", raw, True, destination, False,
                operation_id=IMPORT_MERGE_OPERATION_ID, authorizations=auth,
            )
            self.assertFalse(prepared.state["privacyMode"])
            self.assertEqual(len(prepared.state["prompts"]), 2)
            reexport = adapter.reexport(
                "node-4", prepared.transaction_id, prepared.resume_token,
                prepared.binding_id, prepared.protected_value, False,
                operation_id=IMPORT_MERGE_OPERATION_ID, authorizations=auth,
            )
            package = json.loads(reexport.text)
            self.assertFalse(package["encrypted"])
            self.assertFalse(package["spm_data"]["privacyMode"])

    def test_bare_and_export_fixtures_cover_public_private_replace_merge(self):
        with self._installed() as (pack, adapter, token, root):
            token = self._import_fixture_key(pack, token, root)
            fixtures = {
                "bare": json.dumps(
                    json.loads(BARE_FIXTURE.read_text())["envelope"],
                    separators=(",", ":"),
                ),
                "export": json.dumps(
                    json.loads(EXPORT_FIXTURE.read_text())["package"],
                    separators=(",", ":"),
                ),
            }
            index = 0
            for fixture_name, raw in fixtures.items():
                for operation_id in (IMPORT_REPLACE_OPERATION_ID, IMPORT_MERGE_OPERATION_ID):
                    for private in (False, True):
                        index += 1
                        with self.subTest(
                            fixture=fixture_name,
                            operation=operation_id,
                            private=private,
                        ):
                            auth = self._authorizations(pack, token, operation_id)
                            original = (
                                self._private_snapshot(pack, token, operation_id)
                                if private
                                else json.dumps(
                                    library_state(private=False),
                                    sort_keys=True,
                                    separators=(",", ":"),
                                )
                            )
                            prepared = adapter.prepare(
                                f"node-matrix-{index}", f"request-matrix-{index}",
                                raw, True, original, private,
                                operation_id=operation_id, authorizations=auth,
                            )
                            self.assertIs(prepared.state["privacyMode"], private)
                            committed = (
                                protected_envelope_text(
                                    pack.workflow(PROMPT_LIBRARY_WORKFLOW_RESOURCE_ID).protect(
                                        PROMPT_LIBRARY_FIELD_ID,
                                        prepared.state,
                                        self._snapshot_protect(pack, token),
                                    )
                                )
                                if private
                                else prepared.protected_value
                            )
                            reexport = adapter.reexport(
                                f"node-matrix-{index}", prepared.transaction_id,
                                prepared.resume_token, prepared.binding_id, committed,
                                private, operation_id=operation_id, authorizations=auth,
                            )
                            self.assertIs(json.loads(reexport.text)["encrypted"], private)
                            _status, recovered = adapter.cancel(
                                f"node-matrix-{index}", prepared.transaction_id,
                                prepared.resume_token, prepared.binding_id,
                                operation_id=operation_id, authorization=auth.operation,
                            )
                            self.assertEqual(recovered, original)
                            adapter.confirm_rollback(
                                f"node-matrix-{index}", prepared.transaction_id,
                                prepared.resume_token, prepared.binding_id, original,
                                operation_id=operation_id, authorization=auth.operation,
                            )

    def test_cancel_uses_private_original_and_requires_exact_rollback_ack(self):
        with self._installed() as (pack, adapter, token, root):
            token = self._import_fixture_key(pack, token, root)
            raw = json.dumps(json.loads(BARE_FIXTURE.read_text())["envelope"], separators=(",", ":"))
            original = self._private_snapshot(pack, token, IMPORT_REPLACE_OPERATION_ID)
            auth = self._authorizations(pack, token, IMPORT_REPLACE_OPERATION_ID)
            prepared = adapter.prepare(
                "node-5", "request-cancel", raw, True, original, True,
                operation_id=IMPORT_REPLACE_OPERATION_ID, authorizations=auth,
            )
            status, recovered = adapter.cancel(
                "node-5", prepared.transaction_id, prepared.resume_token, prepared.binding_id,
                operation_id=IMPORT_REPLACE_OPERATION_ID, authorization=auth.operation,
            )
            self.assertEqual(status.disposition, "rollback-required")
            self.assertEqual(recovered, original)
            with self.assertRaises(MigrationError):
                adapter.confirm_rollback(
                    "node-5", prepared.transaction_id, prepared.resume_token,
                    prepared.binding_id, original + "x", operation_id=IMPORT_REPLACE_OPERATION_ID,
                    authorization=auth.operation,
                )
            rolled = adapter.confirm_rollback(
                "node-5", prepared.transaction_id, prepared.resume_token,
                prepared.binding_id, original, operation_id=IMPORT_REPLACE_OPERATION_ID,
                authorization=auth.operation,
            )
            self.assertEqual(rolled.disposition, "rolled-back")

    def test_restart_status_resume_and_finalize_failure_are_recoverable(self):
        with self._installed() as (pack, adapter, token, root):
            token = self._import_fixture_key(pack, token, root)
            raw = json.dumps(json.loads(BARE_FIXTURE.read_text())["envelope"], separators=(",", ":"))
            original = self._private_snapshot(pack, token, IMPORT_REPLACE_OPERATION_ID)
            auth = self._authorizations(pack, token, IMPORT_REPLACE_OPERATION_ID)
            prepared = adapter.prepare(
                "node-6", "request-restart", raw, True, original, True,
                operation_id=IMPORT_REPLACE_OPERATION_ID, authorizations=auth,
            )
            committed = protected_envelope_text(
                pack.workflow(PROMPT_LIBRARY_WORKFLOW_RESOURCE_ID).protect(
                    PROMPT_LIBRARY_FIELD_ID,
                    prepared.state,
                    self._snapshot_protect(pack, token),
                )
            )
            restarted = SmartPromptImportExportAdapter()
            restarted.bind(
                workflow=pack.workflow(PROMPT_LIBRARY_WORKFLOW_RESOURCE_ID),
                migration=pack.migration, profile=pack.profile,
            )
            self.assertEqual(restarted.status(
                "node-6", prepared.transaction_id, prepared.resume_token, prepared.binding_id,
                operation_id=IMPORT_REPLACE_OPERATION_ID, authorization=auth.operation,
            ).disposition, "prepared")
            self.assertEqual(restarted.resume(
                "node-6", prepared.transaction_id, prepared.resume_token, prepared.binding_id,
                operation_id=IMPORT_REPLACE_OPERATION_ID, authorization=auth.operation,
            ).original_exact.decode(), original)
            reexport = restarted.reexport(
                "node-6", prepared.transaction_id, prepared.resume_token,
                prepared.binding_id, committed, True,
                operation_id=IMPORT_REPLACE_OPERATION_ID, authorizations=auth,
            )
            with self.assertRaises(SmartPromptImportExportError):
                restarted.finalize(
                    "node-6", prepared.transaction_id, prepared.resume_token,
                    prepared.binding_id, committed, "0" * 64, True,
                    operation_id=IMPORT_REPLACE_OPERATION_ID, authorizations=auth,
                )
            self.assertEqual(restarted.status(
                "node-6", prepared.transaction_id, prepared.resume_token, prepared.binding_id,
                operation_id=IMPORT_REPLACE_OPERATION_ID, authorization=auth.operation,
            ).disposition, "prepared")
            self.assertEqual(len(reexport.digest), 64)

    def test_route_parser_rejects_extra_fields_and_returns_private_cancel_original(self):
        with self._installed() as (pack, adapter, token, _root):
            routes = SmartPromptImportExportRoutes(pack, adapter)
            request = Request(token, {"phase": "status", "extra": True})
            with self.assertRaises(SmartPromptImportExportError):
                asyncio.run(routes.dispatch(request, IMPORT_REPLACE_OPERATION_ID))

    def test_route_plaintext_prepare_uses_exact_operation_and_returns_no_receipt(self):
        with self._installed() as (pack, adapter, token, _root):
            routes = SmartPromptImportExportRoutes(pack, adapter)
            destination = json.dumps(library_state(private=False), sort_keys=True, separators=(",", ":"))
            payload = {
                "phase": "prepare", "owner_id": "node-route",
                "idempotency_key": "request-route", "raw": destination,
                "explicit_reexport": False, "destination_snapshot": destination,
                "destination_private": False,
            }
            result = asyncio.run(routes.dispatch(
                Request(token, payload), IMPORT_REPLACE_OPERATION_ID,
            ))
            self.assertIsNone(result["transactionId"])
            self.assertNotIn("receiptId", result)
            self.assertFalse(result["state"]["privacyMode"])

    def test_legacy_prepare_is_idempotent_for_same_owner_request(self):
        with self._installed() as (pack, adapter, token, root):
            token = self._import_fixture_key(pack, token, root)
            raw = json.dumps(json.loads(BARE_FIXTURE.read_text())["envelope"], separators=(",", ":"))
            original = self._private_snapshot(pack, token, IMPORT_MERGE_OPERATION_ID)
            auth = self._authorizations(pack, token, IMPORT_MERGE_OPERATION_ID)
            first = adapter.prepare(
                "node-idempotent", "request-idempotent", raw, True, original, True,
                operation_id=IMPORT_MERGE_OPERATION_ID, authorizations=auth,
            )
            second = adapter.prepare(
                "node-idempotent", "request-idempotent", raw, True, original, True,
                operation_id=IMPORT_MERGE_OPERATION_ID, authorizations=auth,
            )
            self.assertEqual(first.transaction_id, second.transaction_id)
            self.assertEqual(first.resume_token, second.resume_token)
            self.assertEqual(first.state, second.state)

    def test_s2_integration_does_not_change_s3_fingerprint(self):
        from managed_execution import (
            SMART_PROMPT_S3_PROFILE_FINGERPRINT,
            build_smart_prompt_s3_privacy_profile,
        )

        self.assertEqual(
            build_smart_prompt_s3_privacy_profile().fingerprint,
            SMART_PROMPT_S3_PROFILE_FINGERPRINT,
        )

    def _authorizations(self, pack, token, operation_id):
        request = Request(token)
        return SmartPromptImportExportAuthorizations(
            authorize_privacy_request(request, operation_id, pack_id=pack.profile.id),
            authorize_privacy_request(request, "snapshot.reveal", pack_id=pack.profile.id),
        )

    def _snapshot_protect(self, pack, token):
        return authorize_privacy_request(
            Request(token), "snapshot.protect", pack_id=pack.profile.id,
        )

    def _private_snapshot(self, pack, token, operation_id):
        return protected_envelope_text(pack.workflow(PROMPT_LIBRARY_WORKFLOW_RESOURCE_ID).protect(
            PROMPT_LIBRARY_FIELD_ID, library_state(private=True),
            self._snapshot_protect(pack, token),
        ))

    def _import_fixture_key(self, pack, token: str, root: Path) -> str:
        key = hashlib.sha256(b"helto-smart-prompt-v1-historical-fixture-key").digest()
        encode = lambda value: base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")
        source = root / "privacy_key.json"
        source.write_text(json.dumps({
            "version": 1, "algorithm": "AES-256-GCM",
            "keyId": encode(hashlib.sha256(key).digest()[:12]), "key": encode(key),
        }), encoding="utf-8")
        pack.migration.import_legacy_key_source(
            SMART_PROMPT_V1_JSON_KEY_IMPORT_ID, source, "synthetic Smart Prompt password",
            LegacyKeyFormat.JSON,
            authorize_privacy_request(Request(token), "migration.key-import", pack_id=pack.profile.id),
        )
        return shared_keystore.session_token()

    class _installed:
        def __enter__(self):
            self.stack = stack = ExitStack()
            root = Path(stack.enter_context(tempfile.TemporaryDirectory()))
            stack.enter_context(patch.dict(os.environ, {
                shared_keystore.KEYSTORE_ENV: str(root / "keystore.json"),
                shared_keystore.SESSION_DIR_ENV: str(root / "session"),
                shared_migration.MIGRATION_STATE_ENV: str(root / "migration.json"),
            }))
            for module in (shared_envelope, shared_guard, shared_keystore, shared_suite_runtime):
                stack.enter_context(patch.object(module, "require_active_process_suite", lambda: object()))
            stack.enter_context(patch.object(shared_keystore, "SCRYPT_N", 2**12))
            stack.enter_context(patch.object(shared_runtime, "_INSTALLATIONS", {}))
            stack.enter_context(patch.object(shared_runtime, "register_helto_privacy_ui", lambda **_: True))
            shared_migration.reset_migration_runtime_for_tests()
            register_legacy_reader_units((smart_prompt_v1_reader_unit(), smart_prompt_v1_export_reader_unit()))
            adapter = SmartPromptImportExportAdapter()
            adapters = build_smart_prompt_s2_server_adapters()
            adapters[PROMPT_LIBRARY_OPERATION_ADAPTER_ID] = adapter
            pack = shared_runtime.install(build_smart_prompt_s2_privacy_profile(), adapters)
            adapter.bind(
                workflow=pack.workflow(PROMPT_LIBRARY_WORKFLOW_RESOURCE_ID),
                migration=pack.migration, profile=pack.profile,
            )
            token = shared_keystore.initialize_keystore("synthetic Smart Prompt password")["token"]
            return pack, adapter, token, root

        def __exit__(self, *_args):
            try: shared_keystore.lock_keystore()
            except Exception: pass
            self.stack.close()


if __name__ == "__main__":
    unittest.main()
