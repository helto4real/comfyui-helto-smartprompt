from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import helto_privacy.envelope as shared_envelope
import helto_privacy.keystore as shared_keystore

from helto_privacy import (
    EffectivePrivacyMode,
    PrivacyEnvelopeCodec,
    ProtectedOperation,
    ProtectedStateAuthority,
    ProfileResource,
    ResourceKind,
    SMART_PROMPT_V1_JSON_KEY_IMPORT_ID,
    SMART_PROMPT_V1_READER_ID,
    AdapterSlot,
    resolve_privacy_mode,
    smart_prompt_v1_reader_unit,
)

from managed_privacy import (
    PROMPT_LIBRARY_DISPATCH_ADAPTER_ID,
    PROMPT_LIBRARY_EXECUTION_INPUT,
    PROMPT_LIBRARY_EXECUTION_RESOURCE_ID,
    PROMPT_LIBRARY_FIELD_ID,
    PROMPT_LIBRARY_LEGACY_BINDING_ID,
    PROMPT_LIBRARY_LEGACY_KEY_BINDING_ID,
    PROMPT_LIBRARY_MODE_ADAPTER_ID,
    PROMPT_LIBRARY_MODE_BROWSER_ADAPTER_ID,
    PROMPT_LIBRARY_MODE_PROPERTY,
    PROMPT_LIBRARY_MODE_RESOURCE_ID,
    PROMPT_LIBRARY_OPERATION_ADAPTER_ID,
    PROMPT_LIBRARY_PROJECTION_ADAPTER_ID,
    PROMPT_LIBRARY_PROJECTION_ID,
    PROMPT_LIBRARY_SCOPE_ID,
    PROMPT_LIBRARY_SUBJECT_MODE_BINDING_ID,
    PROMPT_LIBRARY_SUBJECT_MODE_INPUT,
    PROMPT_LIBRARY_WIDGET_NAME,
    PROMPT_LIBRARY_WORKFLOW_ADAPTER_ID,
    PROMPT_LIBRARY_WORKFLOW_BROWSER_ADAPTER_ID,
    PROMPT_LIBRARY_WORKFLOW_RESOURCE_ID,
    SMART_PROMPT_CURRENT_SCHEMA,
    SMART_PROMPT_DEFERRED_ADAPTER_SLOTS,
    SMART_PROMPT_DISTRIBUTION,
    SMART_PROMPT_LOCAL_PRIVACY_REMOVAL_INVENTORY,
    SMART_PROMPT_NODE_TYPE,
    SMART_PROMPT_PROFILE_ID,
    SMART_PROMPT_S1_PROFILE_FINGERPRINT,
    SmartPromptExecutionProjectionAdapter,
    SmartPromptModeAdapter,
    SmartPromptPrivacyFragment,
    SmartPromptWorkflowStateAdapter,
    build_smart_prompt_privacy_profile,
    build_smart_prompt_server_adapters,
)


FIXTURE = Path(__file__).with_name("smart_prompt_v1_state.fixture.json")


class ImportedFixtureKey:
    def key_for(self, import_id: str) -> bytes:
        if import_id != SMART_PROMPT_V1_JSON_KEY_IMPORT_ID:
            raise ValueError("Unexpected historical key identity.")
        return hashlib.sha256(
            b"helto-smart-prompt-v1-historical-fixture-key"
        ).digest()


class SmartPromptManagedPrivacyTests(unittest.TestCase):
    def test_s1_profile_has_exact_immutable_identity_and_contracts(self):
        profile = build_smart_prompt_privacy_profile()
        resources = {resource.id: resource for resource in profile.resources}
        field = profile.protected_fields[0]
        scope = profile.scopes[0]
        binding = profile.subject_mode_bindings[0]
        projection = profile.execution_projections[0]

        self.assertEqual(profile.id, SMART_PROMPT_PROFILE_ID)
        self.assertEqual(profile.distribution, SMART_PROMPT_DISTRIBUTION)
        self.assertEqual(profile.fingerprint, SMART_PROMPT_S1_PROFILE_FINGERPRINT)
        self.assertEqual(
            set(resources),
            {
                PROMPT_LIBRARY_MODE_RESOURCE_ID,
                PROMPT_LIBRARY_WORKFLOW_RESOURCE_ID,
                PROMPT_LIBRARY_EXECUTION_RESOURCE_ID,
            },
        )
        self.assertEqual(scope.id, PROMPT_LIBRARY_SCOPE_ID)
        self.assertEqual(scope.mode_resource_id, PROMPT_LIBRARY_MODE_RESOURCE_ID)
        self.assertEqual(scope.mode_source_adapter, PROMPT_LIBRARY_MODE_ADAPTER_ID)
        self.assertEqual(scope.mode_editor_adapter, PROMPT_LIBRARY_MODE_BROWSER_ADAPTER_ID)

        self.assertEqual(field.id, PROMPT_LIBRARY_FIELD_ID)
        self.assertEqual(field.workflow_resource_id, PROMPT_LIBRARY_WORKFLOW_RESOURCE_ID)
        self.assertEqual(field.scope_id, PROMPT_LIBRARY_SCOPE_ID)
        self.assertEqual(field.state_adapter, PROMPT_LIBRARY_WORKFLOW_ADAPTER_ID)
        self.assertEqual(field.browser_adapter, PROMPT_LIBRARY_WORKFLOW_BROWSER_ADAPTER_ID)
        self.assertEqual(field.node_types, (SMART_PROMPT_NODE_TYPE,))
        self.assertEqual(field.location.name, PROMPT_LIBRARY_WIDGET_NAME)
        self.assertEqual(field.current_schema, SMART_PROMPT_CURRENT_SCHEMA)
        self.assertEqual(field.legacy_reader_ids, (SMART_PROMPT_V1_READER_ID,))
        self.assertIs(
            field.state_authority,
            ProtectedStateAuthority.EXTERNAL_BROWSER_WORKFLOW,
        )
        self.assertEqual(
            field.external_transition_policy.max_original_bytes_per_owner,
            16 * 1024 * 1024,
        )
        self.assertEqual(
            field.external_transition_policy.max_target_bytes_per_owner,
            16 * 1024 * 1024,
        )
        self.assertTrue(field.execution)
        self.assertEqual(field.mirror_locations, ())
        self.assertEqual(PROMPT_LIBRARY_MODE_PROPERTY, "spmPrivacyMode")

        self.assertEqual(binding.id, PROMPT_LIBRARY_SUBJECT_MODE_BINDING_ID)
        self.assertEqual(binding.input_name, PROMPT_LIBRARY_SUBJECT_MODE_INPUT)
        self.assertEqual(projection.id, PROMPT_LIBRARY_PROJECTION_ID)
        self.assertEqual(projection.input_name, PROMPT_LIBRARY_EXECUTION_INPUT)
        self.assertEqual(
            profile.server_adapter_contracts,
            {
                PROMPT_LIBRARY_MODE_ADAPTER_ID: (
                    "classify_mode_source",
                    "compare_and_set_mode_source",
                    "read_declared_mode",
                    "read_mode_source",
                    "rollback_mode_source",
                ),
                PROMPT_LIBRARY_WORKFLOW_ADAPTER_ID: (
                    "apply_revealed",
                    "capture",
                    "classify_mode_transition_representation",
                    "clear_plaintext",
                    "decode_mode_transition_representation",
                    "encode_public_mode_transition",
                    "normalize",
                    "normalize_mode_transition_value",
                ),
                PROMPT_LIBRARY_PROJECTION_ADAPTER_ID: ("project",),
                PROMPT_LIBRARY_DISPATCH_ADAPTER_ID: ("dispatch",),
            },
        )
        self.assertEqual(
            profile.browser_adapter_contracts[PROMPT_LIBRARY_MODE_BROWSER_ADAPTER_ID],
            (
                "onPrivacySessionChange",
                "readDeclaredMode",
                "reconcileNode",
                "reconcileNodeDefinition",
                "writeDeclaredMode",
            ),
        )
        self.assertEqual(
            profile.browser_adapter_contracts[PROMPT_LIBRARY_WORKFLOW_BROWSER_ADAPTER_ID],
            (
                "apply",
                "applyModeTransitionOwnerExact",
                "clear",
                "extractDetachedModeTransitionOwnerExact",
                "inventoryModeTransitionOwners",
                "normalize",
                "onPrivacySessionChange",
                "readModeTransitionOwnerExact",
                "readProtected",
                "reconcileModeTransitionRuntime",
                "reconcileNode",
                "reconcileNodeDefinition",
                "reloadModeTransitionRuntime",
                "restoreModeTransitionOwnerExact",
                "settleModeTransition",
                "writeProtected",
                "writeWorkflowProjection",
            ),
        )
        adapters = build_smart_prompt_server_adapters()
        self.assertEqual(set(adapters), set(profile.server_adapter_contracts))
        for adapter_id, methods in profile.server_adapter_contracts.items():
            self.assertTrue(
                all(callable(getattr(adapters[adapter_id], method, None)) for method in methods)
            )

    def test_s2_can_extend_existing_resource_without_a_fake_s1_operation(self):
        self.assertEqual(
            SMART_PROMPT_DEFERRED_ADAPTER_SLOTS,
            (PROMPT_LIBRARY_OPERATION_ADAPTER_ID,),
        )
        base = build_smart_prompt_privacy_profile()
        self.assertNotIn(
            PROMPT_LIBRARY_OPERATION_ADAPTER_ID,
            {slot.id for slot in base.server_adapters},
        )
        extension = SmartPromptPrivacyFragment(
            resources=(
                ProfileResource(
                    PROMPT_LIBRARY_WORKFLOW_RESOURCE_ID,
                    ResourceKind.WORKFLOW,
                    (PROMPT_LIBRARY_OPERATION_ADAPTER_ID,),
                ),
            ),
            server_adapters=(
                AdapterSlot(
                    PROMPT_LIBRARY_OPERATION_ADAPTER_ID,
                    ResourceKind.WORKFLOW,
                    PROMPT_LIBRARY_WORKFLOW_RESOURCE_ID,
                ),
            ),
            protected_operations=(
                ProtectedOperation(
                    "synthetic-later-operation",
                    PROMPT_LIBRARY_WORKFLOW_RESOURCE_ID,
                    PROMPT_LIBRARY_OPERATION_ADAPTER_ID,
                    "/synthetic/later-operation",
                ),
            ),
        )
        composed = build_smart_prompt_privacy_profile(extension)
        workflow = next(
            item
            for item in composed.resources
            if item.id == PROMPT_LIBRARY_WORKFLOW_RESOURCE_ID
        )
        self.assertIn(PROMPT_LIBRARY_OPERATION_ADAPTER_ID, workflow.adapter_slots)
        self.assertEqual(
            composed.server_adapter_contracts[PROMPT_LIBRARY_OPERATION_ADAPTER_ID],
            ("invoke",),
        )

    def test_mode_is_private_by_default_and_only_explicit_false_is_public(self):
        missing = SmartPromptModeAdapter()
        malformed = SmartPromptModeAdapter({PROMPT_LIBRARY_SCOPE_ID: "malformed"})
        public = SmartPromptModeAdapter({PROMPT_LIBRARY_SCOPE_ID: False})
        private = SmartPromptModeAdapter({PROMPT_LIBRARY_SCOPE_ID: True})

        self.assertEqual(missing.read_declared_mode(PROMPT_LIBRARY_SCOPE_ID), "inherit")
        self.assertEqual(malformed.read_declared_mode(PROMPT_LIBRARY_SCOPE_ID), "inherit")
        self.assertIs(
            resolve_privacy_mode(missing.read_declared_mode(PROMPT_LIBRARY_SCOPE_ID)).effective,
            EffectivePrivacyMode.PRIVATE,
        )
        self.assertIs(
            resolve_privacy_mode(malformed.read_declared_mode(PROMPT_LIBRARY_SCOPE_ID)).effective,
            EffectivePrivacyMode.PRIVATE,
        )
        self.assertEqual(public.read_declared_mode(PROMPT_LIBRARY_SCOPE_ID), "public")
        self.assertEqual(private.read_declared_mode(PROMPT_LIBRARY_SCOPE_ID), "private")

        for malformed_value in ("public", "private", 0, 1):
            adapter = SmartPromptModeAdapter(
                {PROMPT_LIBRARY_SCOPE_ID: malformed_value}
            )
            self.assertEqual(
                adapter.read_declared_mode(PROMPT_LIBRARY_SCOPE_ID),
                "inherit",
            )
            self.assertIs(
                resolve_privacy_mode(
                    adapter.read_declared_mode(PROMPT_LIBRARY_SCOPE_ID)
                ).effective,
                EffectivePrivacyMode.PRIVATE,
            )

        written = SmartPromptModeAdapter()
        written.write_declared_mode(PROMPT_LIBRARY_SCOPE_ID, "public")
        self.assertIs(written._declarations[PROMPT_LIBRARY_SCOPE_ID], False)
        written.write_declared_mode(PROMPT_LIBRARY_SCOPE_ID, "private")
        self.assertIs(written._declarations[PROMPT_LIBRARY_SCOPE_ID], True)
        written.write_declared_mode(PROMPT_LIBRARY_SCOPE_ID, "inherit")
        self.assertNotIn(PROMPT_LIBRARY_SCOPE_ID, written._declarations)
        self.assertEqual(
            written.read_declared_mode(PROMPT_LIBRARY_SCOPE_ID),
            "inherit",
        )

    def test_mode_source_uses_revisioned_cas_and_exact_rollback(self):
        adapter = SmartPromptModeAdapter()
        prior = adapter.read_mode_source(PROMPT_LIBRARY_SCOPE_ID)
        target = adapter.compare_and_set_mode_source(
            PROMPT_LIBRARY_SCOPE_ID,
            prior["revision"],
            prior["declared"],
            "public",
        )

        self.assertEqual(target, {"revision": 1, "declared": "public"})
        self.assertEqual(
            adapter.classify_mode_source(PROMPT_LIBRARY_SCOPE_ID, prior, target),
            "target",
        )
        with self.assertRaisesRegex(RuntimeError, "concurrently"):
            adapter.compare_and_set_mode_source(
                PROMPT_LIBRARY_SCOPE_ID,
                prior["revision"],
                prior["declared"],
                "private",
            )
        restored = adapter.rollback_mode_source(
            PROMPT_LIBRARY_SCOPE_ID,
            target,
            prior,
        )
        self.assertEqual(restored, {"revision": 2, "declared": "inherit"})
        self.assertEqual(
            adapter.rollback_mode_source(
                PROMPT_LIBRARY_SCOPE_ID,
                target,
                prior,
            ),
            restored,
        )

    def test_workflow_transition_codec_rejects_ambiguous_exact_json(self):
        adapter = SmartPromptWorkflowStateAdapter()
        public = adapter.encode_public_mode_transition(
            {"version": 1, "folders": [], "prompts": [], "variables": {}},
            None,
        )
        self.assertEqual(
            adapter.classify_mode_transition_representation(public, None),
            "public",
        )
        self.assertEqual(
            adapter.decode_mode_transition_representation(public, None),
            adapter.normalize_mode_transition_value(
                {"version": 1, "folders": [], "prompts": [], "variables": {}},
                None,
            ),
        )
        for invalid in (
            b"",
            b"[]",
            b'{"version":1,"version":2}',
            b'{"schema":"protected-marker","prompts":[]}',
        ):
            with self.assertRaisesRegex(ValueError, "representation is invalid"):
                adapter.classify_mode_transition_representation(invalid, None)

    def test_workflow_adapter_preserves_schema_normalization_apply_and_clear(self):
        declaration = build_smart_prompt_privacy_profile().protected_fields[0]
        adapter = SmartPromptWorkflowStateAdapter()
        explicit_public = {
            "version": 1,
            "privacyMode": False,
            "folders": [],
            "prompts": [],
            "variables": {},
        }
        missing_mode = {
            "version": 1,
            "folders": [],
            "prompts": [],
            "variables": {},
        }

        public = adapter.normalize(explicit_public, declaration)
        private = adapter.normalize(missing_mode, declaration)
        malformed = adapter.normalize("{not-json", declaration)
        self.assertFalse(public["privacyMode"])
        self.assertTrue(private["privacyMode"])
        self.assertTrue(malformed["privacyMode"])
        self.assertEqual(set(public), set(private))
        with self.assertRaises(ValueError):
            adapter.normalize(
                {"encrypted": True, "schema": SMART_PROMPT_CURRENT_SCHEMA},
                declaration,
            )

        target = {PROMPT_LIBRARY_WIDGET_NAME: "old"}
        adapter.apply_revealed(target, explicit_public, declaration)
        self.assertEqual(json.loads(target[PROMPT_LIBRARY_WIDGET_NAME]), public)
        self.assertEqual(adapter.capture(target, declaration), target[PROMPT_LIBRARY_WIDGET_NAME])
        adapter.clear_plaintext(target, declaration)
        self.assertEqual(target[PROMPT_LIBRARY_WIDGET_NAME], "")

    def test_projection_requires_one_complete_normalized_generation(self):
        profile = build_smart_prompt_privacy_profile()
        projection = profile.execution_projections[0]
        adapter = SmartPromptExecutionProjectionAdapter()
        value = {
            "version": 1,
            "folders": [],
            "prompts": [],
            "variables": {},
        }
        projected = adapter.project({PROMPT_LIBRARY_FIELD_ID: value}, projection)
        self.assertTrue(projected["privacyMode"])
        with self.assertRaises(ValueError):
            adapter.project({}, projection)

    def test_genuine_v1_fixture_and_exact_json_key_binding_remain_continuous(self):
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        canonical = json.dumps(
            fixture["envelope"],
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        self.assertEqual(hashlib.sha256(canonical).hexdigest(), fixture["envelopeSha256"])

        reader = smart_prompt_v1_reader_unit()
        self.assertEqual(reader.id, SMART_PROMPT_V1_READER_ID)
        self.assertEqual(reader.key_import_ids, (SMART_PROMPT_V1_JSON_KEY_IMPORT_ID,))
        self.assertTrue(reader.reader.probe(fixture["envelope"], ImportedFixtureKey()))
        revealed = reader.reader.read(fixture["envelope"], ImportedFixtureKey())

        profile = build_smart_prompt_privacy_profile()
        legacy = profile.legacy_bindings[0]
        key = profile.legacy_key_imports[0]
        self.assertEqual(legacy.id, PROMPT_LIBRARY_LEGACY_BINDING_ID)
        self.assertEqual(legacy.reader_id, SMART_PROMPT_V1_READER_ID)
        self.assertEqual(legacy.location_id, PROMPT_LIBRARY_FIELD_ID)
        self.assertEqual(key.id, PROMPT_LIBRARY_LEGACY_KEY_BINDING_ID)
        self.assertEqual(key.import_id, SMART_PROMPT_V1_JSON_KEY_IMPORT_ID)
        self.assertEqual(key.location_id, PROMPT_LIBRARY_FIELD_ID)

        normalized = SmartPromptWorkflowStateAdapter().normalize(
            revealed,
            profile.protected_fields[0],
        )
        self.assertEqual(normalized, fixture["expectedNormalized"])

        with tempfile.TemporaryDirectory() as temporary:
            with (
                patch.dict(
                    os.environ,
                    {
                        shared_keystore.KEYSTORE_ENV: str(
                            Path(temporary) / "privacy_keystore.json"
                        ),
                        shared_keystore.SESSION_DIR_ENV: str(
                            Path(temporary) / "session"
                        ),
                    },
                ),
                patch.object(shared_keystore, "SCRYPT_N", 2**12),
                patch.object(
                    shared_keystore,
                    "require_active_process_suite",
                    lambda: None,
                ),
                patch.object(
                    shared_envelope,
                    "require_active_process_suite",
                    lambda: None,
                ),
            ):
                shared_keystore.initialize_keystore("synthetic fixture password")
                codec = PrivacyEnvelopeCodec(SMART_PROMPT_CURRENT_SCHEMA)
                current = codec.encrypt_state(normalized)
                self.assertEqual(current["schema"], SMART_PROMPT_CURRENT_SCHEMA)
                current_readback = codec.decrypt_state(current)
                self.assertEqual(current_readback, fixture["expectedNormalized"])
                exact = json.dumps(
                    current,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
                state_adapter = SmartPromptWorkflowStateAdapter()
                self.assertEqual(
                    state_adapter.classify_mode_transition_representation(exact, None),
                    "private",
                )
                self.assertEqual(
                    state_adapter.decode_mode_transition_representation(exact, None),
                    fixture["expectedNormalized"],
                )

                product_target = {PROMPT_LIBRARY_WIDGET_NAME: ""}
                state_adapter.apply_revealed(
                    product_target,
                    current_readback,
                    profile.protected_fields[0],
                )
                product_readback = state_adapter.normalize(
                    state_adapter.capture(product_target, profile.protected_fields[0]),
                    profile.protected_fields[0],
                )
                self.assertEqual(product_readback, fixture["expectedNormalized"])
                shared_keystore.lock_keystore()

    def test_removal_inventory_is_applied_to_live_code(self):
        self.assertEqual(len(SMART_PROMPT_LOCAL_PRIVACY_REMOVAL_INVENTORY), 6)
        source = Path(__file__).parents[1] / "web/js/smart_prompt_manager.js"
        live = source.read_text(encoding="utf-8")
        self.assertNotIn("SPM_PRIVACY_MEMOS", live)
        self.assertNotIn("installSpmGraphToPromptPatch", live)
        self.assertNotIn("dataWidget.serializeValue", live)
        self.assertIn("smartPromptManagedPrivacy", live)


if __name__ == "__main__":
    unittest.main()
