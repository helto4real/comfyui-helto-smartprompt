"""Shared-privacy import/export slice for Smart Prompt Manager."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from helto_privacy import (
    SMART_PROMPT_V1_EXPORT_READER_ID,
    SMART_PROMPT_V1_JSON_KEY_IMPORT_ID,
    SMART_PROMPT_V1_READER_ID,
    AdapterSlot,
    LegacyKeyFormat,
    LegacyKeyImportBinding,
    LegacyLocationKind,
    LegacyReaderBinding,
    ExternalMigrationContext,
    ExternalMigrationMode,
    ExternalMigrationVerification,
    ExternalRollbackVerification,
    PrivacyEnvelopeCodec,
    ProfileResource,
    ProtectedOperation,
    ResourceKind,
)
from helto_privacy.migration import discover_bound_legacy

try:
    from .managed_privacy import (
        PROMPT_LIBRARY_FIELD_ID,
        PROMPT_LIBRARY_OPERATION_ADAPTER_ID,
        PROMPT_LIBRARY_WORKFLOW_RESOURCE_ID,
        SMART_PROMPT_CURRENT_SCHEMA,
        SmartPromptPrivacyFragment,
        build_smart_prompt_privacy_profile,
        build_smart_prompt_server_adapters,
        normalize_prompt_library_state,
    )
    from .schema import VIRTUAL_FOLDER_IDS, make_id, suffix_name
except ImportError:  # Allows running tests from the repository root.
    from managed_privacy import (
        PROMPT_LIBRARY_FIELD_ID,
        PROMPT_LIBRARY_OPERATION_ADAPTER_ID,
        PROMPT_LIBRARY_WORKFLOW_RESOURCE_ID,
        SMART_PROMPT_CURRENT_SCHEMA,
        SmartPromptPrivacyFragment,
        build_smart_prompt_privacy_profile,
        build_smart_prompt_server_adapters,
        normalize_prompt_library_state,
    )
    from schema import VIRTUAL_FOLDER_IDS, make_id, suffix_name


SMART_PROMPT_EXPORT_FORMAT = "comfyui-helto-prompts.smart-prompt-manager.export"
SMART_PROMPT_EXPORT_VERSION = 1

IMPORT_REPLACE_OPERATION_ID = "import-replace"
IMPORT_MERGE_OPERATION_ID = "import-merge"
EXPORT_OPERATION_ID = "export"

IMPORT_REPLACE_ROUTE = "/helto_spm/privacy/import-replace"
IMPORT_MERGE_ROUTE = "/helto_spm/privacy/import-merge"
EXPORT_ROUTE = "/helto_spm/privacy/export"

PROMPT_LIBRARY_BARE_V1_BINDING_IDS = {
    IMPORT_REPLACE_OPERATION_ID: "prompt-library-import-replace-bare-smart-prompt-v1",
    IMPORT_MERGE_OPERATION_ID: "prompt-library-import-merge-bare-smart-prompt-v1",
}
PROMPT_LIBRARY_EXPORT_V1_BINDING_IDS = {
    IMPORT_REPLACE_OPERATION_ID: "prompt-library-import-replace-export-smart-prompt-v1",
    IMPORT_MERGE_OPERATION_ID: "prompt-library-import-merge-export-smart-prompt-v1",
}
PROMPT_LIBRARY_BARE_KEY_BINDING_IDS = {
    IMPORT_REPLACE_OPERATION_ID: "prompt-library-import-replace-bare-smart-prompt-json-key-v1",
    IMPORT_MERGE_OPERATION_ID: "prompt-library-import-merge-bare-smart-prompt-json-key-v1",
}
PROMPT_LIBRARY_EXPORT_KEY_BINDING_IDS = {
    IMPORT_REPLACE_OPERATION_ID: "prompt-library-import-replace-export-smart-prompt-json-key-v1",
    IMPORT_MERGE_OPERATION_ID: "prompt-library-import-merge-export-smart-prompt-json-key-v1",
}

SMART_PROMPT_S2_PROFILE_FINGERPRINT = (
    "71eee848aeb87611b835cd872021715fd73f1335653e521df5a740ff5aa0ea62"
)

SMART_PROMPT_S2_LOCAL_REMOVAL_INVENTORY = (
    "import-direct-privacy-decrypt",
    "export-direct-privacy-encrypt",
    "import-locked-state-transition",
    "import-envelope-memo-transition",
)


class SmartPromptImportExportError(RuntimeError):
    """Product-data-free failure for the managed S2 adapter."""


@dataclass(frozen=True, slots=True)
class SmartPromptImportCandidate:
    kind: str
    state: dict[str, object] | None = field(default=None, repr=False)
    protected_value: str | None = field(default=None, repr=False)
    legacy_binding_id: str | None = None
    legacy_source: object = field(default=None, repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class SmartPromptImportExportAuthorizations:
    operation: object = field(repr=False)
    snapshot_reveal: object = field(repr=False)


@dataclass(frozen=True, slots=True)
class SmartPromptImportExportOperationContext:
    operation_id: str
    authorizations: SmartPromptImportExportAuthorizations = field(repr=False)


@dataclass(frozen=True, slots=True)
class SmartPromptImportResult:
    state: dict[str, object] = field(repr=False)
    protected_value: str | None = field(default=None, repr=False)
    receipt_id: str | None = None
    reexport_text: str | None = field(default=None, repr=False)
    warnings: tuple[str, ...] = ()
    transaction_id: str | None = None
    resume_token: str | None = field(default=None, repr=False)
    binding_id: str | None = None
    disposition: str = "prepared"
    exported_at: str = "1970-01-01T00:00:00Z"


@dataclass(frozen=True, slots=True)
class SmartPromptExportResult:
    filename: str
    text: str = field(repr=False)
    snapshot: object = field(repr=False, compare=False)
    digest: str | None = None


def smart_prompt_s2_privacy_fragment() -> SmartPromptPrivacyFragment:
    """Declare import/merge/export without changing the live product routes."""

    return SmartPromptPrivacyFragment(
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
                IMPORT_REPLACE_OPERATION_ID,
                PROMPT_LIBRARY_WORKFLOW_RESOURCE_ID,
                PROMPT_LIBRARY_OPERATION_ADAPTER_ID,
                IMPORT_REPLACE_ROUTE,
            ),
            ProtectedOperation(
                IMPORT_MERGE_OPERATION_ID,
                PROMPT_LIBRARY_WORKFLOW_RESOURCE_ID,
                PROMPT_LIBRARY_OPERATION_ADAPTER_ID,
                IMPORT_MERGE_ROUTE,
            ),
            ProtectedOperation(
                EXPORT_OPERATION_ID,
                PROMPT_LIBRARY_WORKFLOW_RESOURCE_ID,
                PROMPT_LIBRARY_OPERATION_ADAPTER_ID,
                EXPORT_ROUTE,
            ),
        ),
        legacy_bindings=tuple(
            binding
            for operation_id in (IMPORT_REPLACE_OPERATION_ID, IMPORT_MERGE_OPERATION_ID)
            for binding in (
                LegacyReaderBinding(
                    PROMPT_LIBRARY_BARE_V1_BINDING_IDS[operation_id],
                    SMART_PROMPT_V1_READER_ID,
                    PROMPT_LIBRARY_WORKFLOW_RESOURCE_ID,
                    LegacyLocationKind.EXPORT,
                    operation_id,
                ),
                LegacyReaderBinding(
                    PROMPT_LIBRARY_EXPORT_V1_BINDING_IDS[operation_id],
                    SMART_PROMPT_V1_EXPORT_READER_ID,
                    PROMPT_LIBRARY_WORKFLOW_RESOURCE_ID,
                    LegacyLocationKind.EXPORT,
                    operation_id,
                ),
            )
        ),
        legacy_key_imports=tuple(
            binding
            for operation_id in (IMPORT_REPLACE_OPERATION_ID, IMPORT_MERGE_OPERATION_ID)
            for binding in (
                LegacyKeyImportBinding(
                    PROMPT_LIBRARY_BARE_KEY_BINDING_IDS[operation_id],
                    SMART_PROMPT_V1_JSON_KEY_IMPORT_ID,
                    PROMPT_LIBRARY_WORKFLOW_RESOURCE_ID,
                    LegacyLocationKind.EXPORT,
                    operation_id,
                    LegacyKeyFormat.JSON,
                ),
                LegacyKeyImportBinding(
                    PROMPT_LIBRARY_EXPORT_KEY_BINDING_IDS[operation_id],
                    SMART_PROMPT_V1_JSON_KEY_IMPORT_ID,
                    PROMPT_LIBRARY_WORKFLOW_RESOURCE_ID,
                    LegacyLocationKind.EXPORT,
                    operation_id,
                    LegacyKeyFormat.JSON,
                ),
            )
        ),
    )


def build_smart_prompt_s2_privacy_profile():
    profile = build_smart_prompt_privacy_profile(smart_prompt_s2_privacy_fragment())
    if (
        SMART_PROMPT_S2_PROFILE_FINGERPRINT
        and profile.fingerprint != SMART_PROMPT_S2_PROFILE_FINGERPRINT
    ):
        raise RuntimeError("Smart Prompt S2 privacy profile fingerprint changed unexpectedly.")
    return profile


def parse_smart_prompt_import(raw: object) -> SmartPromptImportCandidate:
    """Parse product containers while leaving protected bytes opaque."""

    try:
        raw_text = raw if isinstance(raw, str) else json.dumps(raw)
        parsed = json.loads(raw_text)
    except (TypeError, ValueError):
        raise SmartPromptImportExportError("Smart Prompt library import is invalid.") from None
    if not isinstance(parsed, dict):
        raise SmartPromptImportExportError("Smart Prompt library import is invalid.")

    if _is_export_package(parsed):
        _validate_export_package(parsed)
        source = parsed.get("spm_data")
        if _is_current_envelope(source):
            if parsed.get("encrypted") is not True:
                raise SmartPromptImportExportError(
                    "Smart Prompt export privacy flag is inconsistent."
                )
            return SmartPromptImportCandidate(
                "current",
                protected_value=_exact_protected_text(source),
            )
        if parsed.get("encrypted") is True:
            return SmartPromptImportCandidate(
                "legacy",
                legacy_binding_id="export-wrapper",
                legacy_source=raw_text,
            )
        return SmartPromptImportCandidate(
            "plaintext",
            state=_normalize_plain_import(source),
        )

    if parsed.get("encrypted") is True:
        if _is_current_envelope(parsed):
            return SmartPromptImportCandidate("current", protected_value=raw_text)
        return SmartPromptImportCandidate(
            "legacy",
            legacy_binding_id="bare-envelope",
            legacy_source=raw_text,
        )
    if "prompt" in parsed and not isinstance(parsed.get("prompts"), list):
        raise SmartPromptImportExportError("Single-prompt JSON is not a library import.")
    return SmartPromptImportCandidate(
        "plaintext",
        state=_normalize_plain_import(parsed),
    )


def _is_export_package(value: dict[str, object]) -> bool:
    return (
        value.get("format") == SMART_PROMPT_EXPORT_FORMAT
        and value.get("version") == SMART_PROMPT_EXPORT_VERSION
    )


def _validate_export_package(value: dict[str, object]) -> None:
    if (
        set(value) != {"format", "version", "encrypted", "spm_data", "exportedAt"}
        or not isinstance(value.get("encrypted"), bool)
        or not isinstance(value.get("exportedAt"), str)
        or not str(value.get("exportedAt") or "").strip()
    ):
        raise SmartPromptImportExportError("Smart Prompt export wrapper is invalid.")
    source = value.get("spm_data")
    if value["encrypted"] is False and not isinstance(source, dict):
        raise SmartPromptImportExportError(
            "Smart Prompt export privacy flag is inconsistent."
        )


def _is_current_envelope(value: object) -> bool:
    return PrivacyEnvelopeCodec(SMART_PROMPT_CURRENT_SCHEMA).is_encrypted_payload(value)


def _exact_protected_text(value: object) -> str:
    return value if isinstance(value, str) else json.dumps(value, sort_keys=True, separators=(",", ":"))


def _normalize_plain_import(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or not isinstance(value.get("prompts"), list):
        raise SmartPromptImportExportError("Smart Prompt library import requires prompts.")
    return normalize_prompt_library_state(value)


def merge_smart_prompt_library_states(
    current: object,
    incoming: object,
    *,
    id_factory: Callable[[str], str] = make_id,
) -> tuple[dict[str, object], tuple[str, ...]]:
    """Port the current browser merge behavior without changing its domain rules."""

    result = copy.deepcopy(normalize_prompt_library_state(current))
    imported = normalize_prompt_library_state(incoming)
    warnings: list[str] = []
    folder_map: dict[str, str] = {}
    existing_folder_ids = {str(item["id"]) for item in result["folders"]}
    for folder in imported["folders"]:
        copied = copy.deepcopy(folder)
        old_id = str(copied["id"])
        existing_names = [str(item["name"]) for item in result["folders"]]
        if copied["id"] in existing_folder_ids or copied["id"] in VIRTUAL_FOLDER_IDS:
            copied["id"] = id_factory("folder")
        if any(name.lower() == str(copied["name"]).lower() for name in existing_names):
            copied["name"] = suffix_name(str(copied["name"]), existing_names)
        folder_map[old_id] = str(copied["id"])
        existing_folder_ids.add(str(copied["id"]))
        result["folders"].append(copied)

    first_imported_prompt_id = ""
    for prompt in imported["prompts"]:
        existing_titles = [str(item["title"]) for item in result["prompts"]]
        copied = copy.deepcopy(prompt)
        copied["id"] = id_factory("prompt")
        copied["folderId"] = folder_map.get(str(prompt.get("folderId") or ""), "")
        if any(title.lower() == str(copied["title"]).lower() for title in existing_titles):
            copied["title"] = suffix_name(
                str(copied["title"]),
                existing_titles,
                "- imported",
            )
        if not first_imported_prompt_id:
            first_imported_prompt_id = str(copied["id"])
        result["prompts"].append(copied)

    for name, definition in imported["variables"].items():
        if name not in result["variables"]:
            result["variables"][name] = copy.deepcopy(definition)
            if name in imported["cycleState"]:
                result["cycleState"][name] = copy.deepcopy(imported["cycleState"][name])
        elif result["variables"][name] != definition:
            warnings.append(f"Variable '{name}' already exists and was not overwritten.")
    if not result["selectedPromptId"] and first_imported_prompt_id:
        result["selectedPromptId"] = first_imported_prompt_id
    return result, tuple(warnings)


def smart_prompt_export_filename(exported_at: str) -> str:
    suffix = re.sub(r"[^0-9A-Za-z]+", "-", str(exported_at)).strip("-")
    return f"smart-prompt-manager-library-{suffix}.json"


def build_smart_prompt_export(
    snapshot: object,
    *,
    private: bool,
    exported_at: str,
) -> SmartPromptExportResult:
    value = snapshot if private else normalize_prompt_library_state(snapshot)
    package = {
        "format": SMART_PROMPT_EXPORT_FORMAT,
        "version": SMART_PROMPT_EXPORT_VERSION,
        "encrypted": private,
        "spm_data": value,
        "exportedAt": exported_at,
    }
    return SmartPromptExportResult(
        smart_prompt_export_filename(exported_at),
        json.dumps(package, ensure_ascii=False, indent=2),
        snapshot,
    )


class SmartPromptImportExportAdapter:
    """Request-scoped S2 phases; the browser remains the external state owner."""

    def __init__(
        self,
        *,
        workflow=None,
        migration=None,
        profile=None,
        now: Callable[[], str] | None = None,
    ) -> None:
        self._workflow = workflow
        self._migration = migration
        self._profile = profile
        self._now = now or _utc_now

    def bind(self, *, workflow, migration, profile) -> None:
        if self._workflow is not None or self._migration is not None or self._profile is not None:
            raise SmartPromptImportExportError("Smart Prompt import/export is already bound.")
        self._workflow = workflow
        self._migration = migration
        self._profile = profile

    def invoke(self, payload: object, context: object, declaration: object = None):
        operation_id = getattr(declaration, "id", None)
        if operation_id is None:
            operation_id = (
                context.get("operation_id")
                if isinstance(context, dict)
                else getattr(context, "operation_id", None)
            )
        authorizations = (
            context.get("authorizations")
            if isinstance(context, dict)
            else getattr(context, "authorizations", None)
        )
        if not isinstance(payload, dict):
            raise SmartPromptImportExportError("Smart Prompt operation payload is invalid.")
        if operation_id == EXPORT_OPERATION_ID:
            return self.export(
                payload.get("settled_snapshot"),
                private=payload.get("private") is not False,
                exported_at=str(payload.get("exported_at") or self._now()),
            )
        if operation_id in {IMPORT_REPLACE_OPERATION_ID, IMPORT_MERGE_OPERATION_ID}:
            phase = payload.get("phase")
            if phase != "prepare":
                raise SmartPromptImportExportError("Smart Prompt import phase is invalid.")
            return self.prepare(
                str(payload.get("owner_id") or ""),
                str(payload.get("idempotency_key") or ""),
                payload.get("raw"),
                payload.get("explicit_reexport") is True,
                payload.get("destination_snapshot"),
                payload.get("destination_private"),
                operation_id=operation_id,
                authorizations=authorizations,
            )
        raise SmartPromptImportExportError("Unknown Smart Prompt import/export operation.")

    def export(self, settled_snapshot: object, *, private: bool, exported_at: str):
        if settled_snapshot is None:
            raise SmartPromptImportExportError("Settled Smart Prompt snapshot is required.")
        return build_smart_prompt_export(
            settled_snapshot,
            private=private,
            exported_at=exported_at,
        )

    def prepare(
        self,
        owner_id: str,
        idempotency_key: str,
        raw: object,
        explicit_reexport: bool,
        destination_snapshot: object,
        destination_private: object,
        *,
        operation_id: str,
        authorizations: SmartPromptImportExportAuthorizations,
    ) -> SmartPromptImportResult:
        self._require_bound()
        operation_id = _import_operation(operation_id)
        _external_identity(owner_id, idempotency_key)
        if (
            not isinstance(raw, str)
            or not raw.strip()
            or not isinstance(explicit_reexport, bool)
            or not isinstance(destination_private, bool)
        ):
            raise SmartPromptImportExportError("Smart Prompt destination mode is invalid.")
        destination_exact = _exact_snapshot(destination_snapshot)
        if not isinstance(authorizations, SmartPromptImportExportAuthorizations):
            raise SmartPromptImportExportError("Smart Prompt import authorization is unavailable.")
        current = self._normalize_exact_snapshot(
            destination_exact,
            destination_private,
            authorizations.snapshot_reveal,
        )
        candidate = parse_smart_prompt_import(raw)
        warnings: tuple[str, ...] = ()
        discovered = None
        binding_id = None
        exported_at = _candidate_exported_at(raw)

        if candidate.kind == "plaintext":
            incoming = copy.deepcopy(candidate.state)
        elif candidate.kind == "current":
            revealed = self._workflow.reveal(
                PROMPT_LIBRARY_FIELD_ID,
                candidate.protected_value,
                authorizations.snapshot_reveal,
            )
            incoming = dict(revealed.value)
        else:
            if not explicit_reexport:
                raise SmartPromptImportExportError(
                    "Historical Smart Prompt import requires explicit re-export."
                )
            binding_id = _legacy_binding(operation_id, candidate.legacy_binding_id)
            discovered = discover_bound_legacy(
                self._profile,
                binding_id,
                candidate.legacy_source,
                authorizations.operation,
                operation_id=operation_id,
            )
            if discovered is None:
                raise SmartPromptImportExportError("Historical Smart Prompt import is unsupported.")
            incoming = dict(discovered.value)

        if operation_id == IMPORT_REPLACE_OPERATION_ID:
            final_state = normalize_prompt_library_state(incoming)
        else:
            final_state, warnings = merge_smart_prompt_library_states(
                current,
                incoming,
                id_factory=_deterministic_id_factory(owner_id, idempotency_key),
            )
        final_state["privacyMode"] = destination_private

        if (
            candidate.kind == "current"
            and operation_id == IMPORT_REPLACE_OPERATION_ID
            and destination_private
        ):
            protected_value = candidate.protected_value
        elif destination_private:
            # The shared browser settlement owns the destination encryption.
            # Keeping prepare as a pure semantic plan makes retry bytes stable.
            protected_value = None
        else:
            protected_value = json.dumps(
                final_state,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )

        transaction_id = resume_token = disposition = None
        if discovered is not None and binding_id is not None:
            mode = (
                ExternalMigrationMode.REPLACE
                if operation_id == IMPORT_REPLACE_OPERATION_ID
                else ExternalMigrationMode.MERGE
            )
            prepared = self._migration.external(binding_id, operation_id).prepare(
                discovered.obligation.id,
                final_state,
                destination_exact.encode("utf-8"),
                ExternalMigrationContext(mode, exported_at),
                owner_id,
                idempotency_key,
                authorizations.operation,
            )
            transaction_id = prepared.status.id
            resume_token = prepared.resume_token
            disposition = prepared.status.disposition

        return SmartPromptImportResult(
            final_state,
            protected_value,
            warnings=warnings,
            transaction_id=transaction_id,
            resume_token=resume_token,
            binding_id=binding_id,
            disposition=disposition or "not-required",
            exported_at=exported_at,
        )

    def reexport(
        self,
        owner_id: str,
        transaction_id: str,
        resume_token: str,
        binding_id: str,
        committed_snapshot: object,
        destination_private: object,
        *,
        operation_id: str,
        authorizations: SmartPromptImportExportAuthorizations,
    ) -> SmartPromptExportResult:
        self._require_bound()
        operation_id = _import_operation(operation_id)
        if not isinstance(destination_private, bool):
            raise SmartPromptImportExportError("Smart Prompt destination mode is invalid.")
        external = self._external(binding_id, operation_id)
        resumed = external.resume(
            transaction_id,
            owner_id,
            resume_token,
            authorizations.operation,
        )
        exact = _exact_snapshot(committed_snapshot)
        normalized = self._normalize_exact_snapshot(
            exact,
            destination_private,
            authorizations.snapshot_reveal,
        )
        if normalized != resumed.expected_normalized:
            raise SmartPromptImportExportError("Smart Prompt committed snapshot does not match.")
        expected_mode = _external_mode(operation_id)
        if resumed.context.mode is not expected_mode:
            raise SmartPromptImportExportError("Smart Prompt import context does not match.")
        result = build_smart_prompt_export(
            exact if destination_private else normalized,
            private=destination_private,
            exported_at=resumed.context.exported_at,
        )
        return SmartPromptExportResult(
            result.filename,
            result.text,
            result.snapshot,
            hashlib.sha256(result.text.encode("utf-8")).hexdigest(),
        )

    def finalize(
        self,
        owner_id: str,
        transaction_id: str,
        resume_token: str,
        binding_id: str,
        committed_snapshot: object,
        reexport_digest: str,
        destination_private: object,
        *,
        operation_id: str,
        authorizations: SmartPromptImportExportAuthorizations,
    ):
        reexport = self.reexport(
            owner_id,
            transaction_id,
            resume_token,
            binding_id,
            committed_snapshot,
            destination_private,
            operation_id=operation_id,
            authorizations=authorizations,
        )
        if not isinstance(reexport_digest, str) or not hashlib.sha256(
            reexport.text.encode("utf-8")
        ).hexdigest() == reexport_digest:
            raise SmartPromptImportExportError("Smart Prompt re-export digest does not match.")
        resumed = self._external(binding_id, operation_id).resume(
            transaction_id,
            owner_id,
            resume_token,
            authorizations.operation,
        )
        exact = _exact_snapshot(committed_snapshot)
        normalized = self._normalize_exact_snapshot(
            exact,
            bool(destination_private),
            authorizations.snapshot_reveal,
        )
        return self._external(binding_id, operation_id).finalize(
            transaction_id,
            owner_id,
            resume_token,
            ExternalMigrationVerification(
                normalized=normalized,
                current_exact=exact.encode("utf-8"),
                reexported_exact=reexport.text.encode("utf-8"),
                context=resumed.context,
                current_format=True,
                durable_artifacts_current=True,
            ),
            authorizations.operation,
        )

    def status(self, owner_id, transaction_id, resume_token, binding_id, *, operation_id, authorization):
        return self._external(binding_id, _import_operation(operation_id)).status(
            transaction_id, owner_id, resume_token, authorization
        )

    def resume(self, owner_id, transaction_id, resume_token, binding_id, *, operation_id, authorization):
        return self._external(binding_id, _import_operation(operation_id)).resume(
            transaction_id, owner_id, resume_token, authorization
        )

    def cancel(self, owner_id, transaction_id, resume_token, binding_id, *, operation_id, authorization):
        external = self._external(binding_id, _import_operation(operation_id))
        private = external.resume(transaction_id, owner_id, resume_token, authorization)
        status = external.cancel(transaction_id, owner_id, resume_token, authorization)
        return status, private.original_exact.decode("utf-8")

    def confirm_rollback(
        self,
        owner_id,
        transaction_id,
        resume_token,
        binding_id,
        restored_snapshot,
        *,
        operation_id,
        authorization,
    ):
        exact = _exact_snapshot(restored_snapshot)
        return self._external(binding_id, _import_operation(operation_id)).confirm_rollback(
            transaction_id,
            owner_id,
            resume_token,
            authorization,
            verification=ExternalRollbackVerification(exact.encode("utf-8")),
        )

    def _normalize_exact_snapshot(self, exact: str, private: bool, reveal_authorization):
        if private:
            revealed = self._workflow.reveal(
                PROMPT_LIBRARY_FIELD_ID,
                exact,
                reveal_authorization,
            )
            value = revealed.value
        else:
            try:
                value = json.loads(exact)
            except (TypeError, ValueError):
                raise SmartPromptImportExportError("Smart Prompt destination snapshot is invalid.") from None
        normalized = normalize_prompt_library_state(value)
        normalized["privacyMode"] = private
        return normalized

    def _external(self, binding_id: str, operation_id: str):
        if binding_id not in {
            PROMPT_LIBRARY_BARE_V1_BINDING_IDS[operation_id],
            PROMPT_LIBRARY_EXPORT_V1_BINDING_IDS[operation_id],
        }:
            raise SmartPromptImportExportError("Smart Prompt migration binding is invalid.")
        return self._migration.external(binding_id, operation_id)

    def _require_bound(self) -> None:
        if self._workflow is None or self._migration is None or self._profile is None:
            raise SmartPromptImportExportError("Smart Prompt import/export handles are unavailable.")


def _import_operation(operation_id: object) -> str:
    if operation_id not in {IMPORT_REPLACE_OPERATION_ID, IMPORT_MERGE_OPERATION_ID}:
        raise SmartPromptImportExportError("Smart Prompt import operation is invalid.")
    return str(operation_id)


def _external_mode(operation_id: str) -> ExternalMigrationMode:
    return (
        ExternalMigrationMode.REPLACE
        if operation_id == IMPORT_REPLACE_OPERATION_ID
        else ExternalMigrationMode.MERGE
    )


def _legacy_binding(operation_id: str, candidate_binding: object) -> str:
    if candidate_binding == "export-wrapper":
        return PROMPT_LIBRARY_EXPORT_V1_BINDING_IDS[operation_id]
    if candidate_binding == "bare-envelope":
        return PROMPT_LIBRARY_BARE_V1_BINDING_IDS[operation_id]
    raise SmartPromptImportExportError("Smart Prompt historical import binding is invalid.")


def _exact_snapshot(value: object) -> str:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 16 * 1024 * 1024:
        raise SmartPromptImportExportError("Smart Prompt exact snapshot is invalid.")
    return value


def _external_identity(owner_id: object, idempotency_key: object) -> None:
    pattern = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
    if not isinstance(owner_id, str) or pattern.fullmatch(owner_id) is None:
        raise SmartPromptImportExportError("Smart Prompt import owner is invalid.")
    if not isinstance(idempotency_key, str) or pattern.fullmatch(idempotency_key) is None:
        raise SmartPromptImportExportError("Smart Prompt import idempotency key is invalid.")


def _deterministic_id_factory(owner_id: str, idempotency_key: str):
    counter = 0

    def create(prefix: str) -> str:
        nonlocal counter
        counter += 1
        digest = hashlib.sha256(
            f"{owner_id}\0{idempotency_key}\0{prefix}\0{counter}".encode("utf-8")
        ).hexdigest()[:12]
        return f"{prefix}_{digest}"

    return create


def _candidate_exported_at(raw: object) -> str:
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        return "1970-01-01T00:00:00Z"
    if isinstance(parsed, dict) and _is_export_package(parsed):
        value = parsed.get("exportedAt")
        if isinstance(value, str):
            return value
    return "1970-01-01T00:00:00Z"


def build_smart_prompt_s2_server_adapters(**kwargs) -> dict[str, object]:
    adapters = build_smart_prompt_server_adapters()
    adapters[PROMPT_LIBRARY_OPERATION_ADAPTER_ID] = SmartPromptImportExportAdapter(
        **kwargs
    )
    return adapters


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
