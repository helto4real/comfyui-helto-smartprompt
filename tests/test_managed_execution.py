from __future__ import annotations

from contextlib import ExitStack
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import helto_privacy.envelope as shared_envelope
import helto_privacy.execution as shared_execution
import helto_privacy.guard as shared_guard
import helto_privacy.keystore as shared_keystore
import helto_privacy.migration as shared_migration
import helto_privacy.runtime as shared_runtime
import helto_privacy.suite_runtime as shared_suite_runtime
from helto_privacy import (
    ExecutionError,
    protected_envelope_text,
    register_legacy_reader_units,
    smart_prompt_v1_export_reader_unit,
    smart_prompt_v1_reader_unit,
)
from helto_privacy.guard import authorize_privacy_request

from managed_execution import (
    RESOLVE_PROMPT_OPERATION_ID,
    SMART_PROMPT_S3_LOCAL_REMOVAL_INVENTORY,
    SMART_PROMPT_S3_PROFILE_FINGERPRINT,
    SmartPromptCombinedOperationAdapter,
    SmartPromptExecutionDispatchAdapter,
    SmartPromptExecutionProductError,
    SmartPromptResolveOperationContext,
    SmartPromptSemanticProjectionAdapter,
    build_smart_prompt_s3_privacy_profile,
    build_smart_prompt_s3_server_adapters,
)
from managed_import_export import SmartPromptImportExportAdapter
from managed_privacy import (
    PROMPT_LIBRARY_EXECUTION_RESOURCE_ID,
    PROMPT_LIBRARY_FIELD_ID,
    PROMPT_LIBRARY_PROJECTION_ID,
    PROMPT_LIBRARY_SUBJECT_MODE_BINDING_ID,
    PROMPT_LIBRARY_WORKFLOW_RESOURCE_ID,
)
from nodes import SmartPromptManager
from schema import state_to_json


PASSWORD = "synthetic Smart Prompt execution password"


class Request:
    def __init__(self, token: str) -> None:
        self.headers = {"X-Helto-Privacy-Token": token}
        self.cookies = {}


class CountingDispatch(SmartPromptExecutionDispatchAdapter):
    def __init__(self) -> None:
        self.calls = 0

    def dispatch(self, semantic, context, cancellation):
        self.calls += 1
        return super().dispatch(semantic, context, cancellation)


def execution_state(text: str = "A {{mood}} portrait") -> dict[str, object]:
    return {
        "version": 1,
        "selectedFolderId": "all",
        "selectedPromptId": "prompt1",
        "search": "",
        "privacyMode": True,
        "folders": [],
        "prompts": [
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
        ],
        "variables": {
            "mood": {
                "mode": "fixed",
                "values": ["dreamy"],
                "fixedValue": "dreamy",
                "fallback": "",
                "description": "",
            }
        },
        "cycleState": {},
        "ui": {"collapsedSections": {}},
    }


class SmartPromptManagedExecutionTests(unittest.TestCase):
    def test_s3_profile_and_semantic_projection_are_exact(self):
        profile = build_smart_prompt_s3_privacy_profile()
        self.assertEqual(profile.fingerprint, SMART_PROMPT_S3_PROFILE_FINGERPRINT)
        operation = next(
            item for item in profile.protected_operations
            if item.id == RESOLVE_PROMPT_OPERATION_ID
        )
        projection = profile.execution_projections[0]
        self.assertEqual(operation.resource_id, PROMPT_LIBRARY_WORKFLOW_RESOURCE_ID)
        self.assertEqual(projection.id, PROMPT_LIBRARY_PROJECTION_ID)
        self.assertEqual(
            projection.subject_mode_binding_id,
            PROMPT_LIBRARY_SUBJECT_MODE_BINDING_ID,
        )
        semantic = SmartPromptSemanticProjectionAdapter().project(
            {PROMPT_LIBRARY_FIELD_ID: execution_state()},
            projection,
        )
        self.assertEqual(
            set(semantic),
            {
                "selectedPromptId",
                "selectedFolderId",
                "folderIds",
                "prompts",
                "variables",
                "cycleState",
            },
        )
        self.assertEqual(set(semantic["prompts"][0]), {"id", "title", "text"})
        self.assertNotIn("privacyMode", semantic)
        self.assertEqual(len(SMART_PROMPT_S3_LOCAL_REMOVAL_INVENTORY), 6)
        adapters = build_smart_prompt_s3_server_adapters()
        self.assertEqual(set(adapters), set(profile.server_adapter_contracts))

    def test_cycle_missing_variable_and_warning_json_match_existing_product(self):
        profile = build_smart_prompt_s3_privacy_profile()
        state = execution_state("{{mood}} {{missing}}")
        state["variables"]["mood"].update(
            {
                "mode": "cycle",
                "values": ["one", "two", "three"],
                "fixedValue": None,
            }
        )
        state["cycleState"] = {"mood": 1}
        semantic = SmartPromptSemanticProjectionAdapter().project(
            {PROMPT_LIBRARY_FIELD_ID: state},
            profile.execution_projections[0],
        )
        actual = SmartPromptExecutionDispatchAdapter().dispatch(
            semantic,
            {"seed": 9, "reroll": 1},
            type("Cancellation", (), {"checkpoint": lambda self: None})(),
        )
        expected = SmartPromptManager().resolve(
            state_to_json(state),
            seed=9,
            reroll=1,
        )
        self.assertEqual(actual, expected)

    def test_shared_dispatch_is_byte_for_byte_product_parity(self):
        with self._installed() as installed:
            pack, token, dispatch = installed
            state = execution_state()
            expected = SmartPromptManager().resolve(
                state_to_json(state),
                seed=17,
                reroll=3,
            )
            protected = self._protect(pack, token, state)
            prepared = self._prepare(pack, token, protected, "node-1")
            result = pack.execution(PROMPT_LIBRARY_EXECUTION_RESOURCE_ID).dispatch(
                prepared.reference,
                {"seed": 17, "reroll": 3},
                subject_id="node-1",
            )
            self.assertEqual(result.value, expected)
            self.assertEqual(dispatch.calls, 1)
            with self.assertRaises(ExecutionError):
                pack.execution(PROMPT_LIBRARY_EXECUTION_RESOURCE_ID).dispatch(
                    prepared.reference,
                    {"seed": 17, "reroll": 3},
                    subject_id="node-1",
                )

    def test_seed_reroll_cache_identity_isolated_and_cleared_on_lock(self):
        with self._installed() as installed:
            pack, token, dispatch = installed
            execution = pack.execution(PROMPT_LIBRARY_EXECUTION_RESOURCE_ID)
            state = execution_state()
            first = execution.dispatch(
                self._prepare(pack, token, self._protect(pack, token, state), "node-2").reference,
                {"seed": 1, "reroll": 0},
                subject_id="node-2",
                cache_discriminator={"seed": 1, "reroll": 0},
            )
            cached_value = {"private": "seed-one-reroll-zero"}
            execution.cache_store(first.cache_identity, cached_value)

            same_context = execution.dispatch(
                self._prepare(pack, token, self._protect(pack, token, state), "node-2").reference,
                {"seed": 1, "reroll": 0},
                subject_id="node-2",
                cache_discriminator={"seed": 1, "reroll": 0},
            )
            self.assertEqual(same_context.cache_identity, first.cache_identity)
            self.assertEqual(same_context.value, cached_value)
            self.assertEqual(dispatch.calls, 1)

            different_seed = execution.dispatch(
                self._prepare(pack, token, self._protect(pack, token, state), "node-2").reference,
                {"seed": 2, "reroll": 0},
                subject_id="node-2",
                cache_discriminator={"seed": 2, "reroll": 0},
            )
            self.assertNotEqual(different_seed.cache_identity, first.cache_identity)
            self.assertNotEqual(different_seed.value, cached_value)
            self.assertEqual(dispatch.calls, 2)

            different_reroll = execution.dispatch(
                self._prepare(pack, token, self._protect(pack, token, state), "node-2").reference,
                {"seed": 1, "reroll": 1},
                subject_id="node-2",
                cache_discriminator={"seed": 1, "reroll": 1},
            )
            self.assertNotEqual(different_reroll.cache_identity, first.cache_identity)
            self.assertNotEqual(
                different_reroll.cache_identity,
                different_seed.cache_identity,
            )
            self.assertNotEqual(different_reroll.value, cached_value)
            self.assertEqual(dispatch.calls, 3)

            shared_keystore.lock_keystore()
            token = shared_keystore.unlock_keystore(PASSWORD)["token"]
            self.assertIsNone(execution.cache_load(first.cache_identity))
            fresh_session = execution.dispatch(
                self._prepare(pack, token, self._protect(pack, token, state), "node-2").reference,
                {"seed": 1, "reroll": 0},
                subject_id="node-2",
                cache_discriminator={"seed": 1, "reroll": 0},
            )
            self.assertNotEqual(fresh_session.cache_identity, first.cache_identity)
            self.assertNotEqual(fresh_session.value, cached_value)
            self.assertEqual(dispatch.calls, 4)

    def test_revocation_lock_and_subject_mismatch_reject_grants(self):
        with self._installed() as installed:
            pack, token, _dispatch = installed
            execution = pack.execution(PROMPT_LIBRARY_EXECUTION_RESOURCE_ID)
            protected = self._protect(pack, token, execution_state())
            revoked = self._prepare(pack, token, protected, "node-3")
            self.assertTrue(
                execution.revoke(
                    revoked.reference,
                    self._authorization(pack, token, "submission-grants.revoke"),
                )
            )
            with self.assertRaises(ExecutionError):
                execution.dispatch(
                    revoked.reference,
                    {"seed": 1, "reroll": 0},
                    subject_id="node-3",
                )

            mismatched = self._prepare(pack, token, protected, "node-4")
            with self.assertRaises(ExecutionError):
                execution.dispatch(
                    mismatched.reference,
                    {"seed": 1, "reroll": 0},
                    subject_id="other-node",
                )

            locked = self._prepare(pack, token, protected, "node-5")
            shared_keystore.lock_keystore()
            token = shared_keystore.unlock_keystore(PASSWORD)["token"]
            with self.assertRaises(ExecutionError):
                execution.dispatch(
                    locked.reference,
                    {"seed": 1, "reroll": 0},
                    subject_id="node-5",
                )

    def test_missing_reference_context_or_prompt_never_executes_defaults(self):
        with self._installed() as installed:
            pack, token, dispatch = installed
            execution = pack.execution(PROMPT_LIBRARY_EXECUTION_RESOURCE_ID)
            with self.assertRaises(ExecutionError):
                execution.prepare(
                    PROMPT_LIBRARY_PROJECTION_ID,
                    {},
                    self._authorization(pack, token, "execution.prepare"),
                    subject_id="node-6",
                )

            protected = self._protect(pack, token, execution_state())
            incomplete = self._prepare(pack, token, protected, "node-6")
            with self.assertRaises(ExecutionError):
                execution.dispatch(
                    incomplete.reference,
                    {"seed": 1},
                    subject_id="node-6",
                )

            empty = execution_state()
            empty["prompts"] = []
            empty["selectedPromptId"] = ""
            no_prompt = self._prepare(pack, token, self._protect(pack, token, empty), "node-7")
            with self.assertRaises(ExecutionError):
                execution.dispatch(
                    no_prompt.reference,
                    {"seed": 1, "reroll": 0},
                    subject_id="node-7",
                )
            self.assertEqual(dispatch.calls, 1)

    def test_protected_resolve_operation_requires_reference_and_exact_context(self):
        class Execution:
            def __init__(self):
                self.calls = []

            def dispatch(self, *args, **kwargs):
                self.calls.append((args, kwargs))
                return "resolved"

        execution = Execution()
        adapter = SmartPromptCombinedOperationAdapter(SmartPromptImportExportAdapter())
        context = SmartPromptResolveOperationContext(execution, "node-8", 9, 2)
        self.assertEqual(
            adapter.invoke({"private_execution": {"grant": "opaque"}}, context),
            "resolved",
        )
        self.assertEqual(
            execution.calls,
            [
                (
                    ({"grant": "opaque"}, {"seed": 9, "reroll": 2}),
                    {
                        "subject_id": "node-8",
                        "cache_discriminator": {"seed": 9, "reroll": 2},
                    },
                )
            ],
        )
        with self.assertRaises(SmartPromptExecutionProductError):
            adapter.invoke({}, context)

    def _authorization(self, pack, token: str, operation: str):
        return authorize_privacy_request(
            Request(token),
            operation,
            pack_id=pack.profile.id,
        )

    def _protect(self, pack, token: str, state: object) -> str:
        return protected_envelope_text(
            pack.workflow(PROMPT_LIBRARY_WORKFLOW_RESOURCE_ID).protect(
                PROMPT_LIBRARY_FIELD_ID,
                state,
                self._authorization(pack, token, "snapshot.protect"),
            )
        )

    def _prepare(self, pack, token: str, protected: str, subject_id: str):
        return pack.execution(PROMPT_LIBRARY_EXECUTION_RESOURCE_ID).prepare(
            PROMPT_LIBRARY_PROJECTION_ID,
            {PROMPT_LIBRARY_FIELD_ID: protected},
            self._authorization(pack, token, "execution.prepare"),
            subject_id=subject_id,
        )

    class _installed:
        def __init__(self) -> None:
            self.stack = None

        def __enter__(self):
            stack = self.stack = ExitStack()
            root = Path(stack.enter_context(tempfile.TemporaryDirectory()))
            stack.enter_context(
                patch.dict(
                    os.environ,
                    {
                        shared_keystore.KEYSTORE_ENV: str(root / "keystore.json"),
                        shared_keystore.SESSION_DIR_ENV: str(root / "session"),
                        shared_migration.MIGRATION_STATE_ENV: str(root / "migration.json"),
                    },
                )
            )
            for module in (
                shared_envelope,
                shared_guard,
                shared_keystore,
                shared_suite_runtime,
            ):
                stack.enter_context(
                    patch.object(module, "require_active_process_suite", lambda: object())
                )
            stack.enter_context(patch.object(shared_keystore, "SCRYPT_N", 2**12))
            stack.enter_context(patch.object(shared_runtime, "_INSTALLATIONS", {}))
            stack.enter_context(
                patch.object(shared_runtime, "register_helto_privacy_ui", lambda **_kwargs: True)
            )
            shared_migration.reset_migration_runtime_for_tests()
            register_legacy_reader_units(
                (smart_prompt_v1_reader_unit(), smart_prompt_v1_export_reader_unit())
            )
            shared_execution.invalidate_execution_session("test-reset")
            dispatch = CountingDispatch()
            adapters = build_smart_prompt_s3_server_adapters()
            adapters["prompt-library-execution-dispatch"] = dispatch
            pack = shared_runtime.install(
                build_smart_prompt_s3_privacy_profile(),
                adapters,
            )
            token = shared_keystore.initialize_keystore(PASSWORD)["token"]
            return pack, token, dispatch

        def __exit__(self, exc_type, exc, traceback):
            try:
                shared_keystore.lock_keystore()
            except Exception:
                pass
            shared_execution.invalidate_execution_session("test-cleanup")
            self.stack.close()


if __name__ == "__main__":
    unittest.main()
