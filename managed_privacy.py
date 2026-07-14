"""Shared-privacy declarations and product adapters for Smart Prompt."""

from __future__ import annotations

import base64
import copy
import json
from collections.abc import Mapping
from dataclasses import dataclass, fields
from threading import RLock
from typing import Callable

from helto_privacy import (
    SMART_PROMPT_V1_JSON_KEY_IMPORT_ID,
    SMART_PROMPT_V1_READER_ID,
    AdapterSlot,
    ExternalTransitionPolicy,
    FieldLocation,
    FieldLocationKind,
    LegacyKeyFormat,
    LegacyKeyImportBinding,
    LegacyLocationKind,
    LegacyReaderBinding,
    PrivacyEnvelopeCodec,
    PrivacyProfile,
    PrivacyScope,
    ProfileResource,
    ProtectedField,
    ProtectedStateAuthority,
    ResourceKind,
    SemanticExecutionProjection,
    SubjectModeBinding,
)

try:
    from .schema import normalize_state, state_to_json
except ImportError:  # Allows running tests from the repository root.
    from schema import normalize_state, state_to_json


SMART_PROMPT_PROFILE_ID = "helto.smart-prompt-manager"
SMART_PROMPT_DISTRIBUTION = "comfyui-helto-smartprompt"
SMART_PROMPT_NODE_TYPE = "SmartPromptManager"
SMART_PROMPT_CURRENT_SCHEMA = "helto.smart-prompt-manager"
SMART_PROMPT_S1_PROFILE_FINGERPRINT = (
    "d17be6f60600e9055fd6ed96d4ddef45e5fe0bbd492ae357c00c418e2514d15f"
)

PROMPT_LIBRARY_SCOPE_ID = "prompt-library"
PROMPT_LIBRARY_MODE_RESOURCE_ID = "prompt-library-mode"
PROMPT_LIBRARY_WORKFLOW_RESOURCE_ID = "prompt-library-workflow"
PROMPT_LIBRARY_EXECUTION_RESOURCE_ID = "prompt-library-execution"

PROMPT_LIBRARY_MODE_ADAPTER_ID = "prompt-library-mode-state"
PROMPT_LIBRARY_WORKFLOW_ADAPTER_ID = "prompt-library-workflow-state"
PROMPT_LIBRARY_OPERATION_ADAPTER_ID = "prompt-library-operations"
PROMPT_LIBRARY_PROJECTION_ADAPTER_ID = "prompt-library-execution-projection"
PROMPT_LIBRARY_DISPATCH_ADAPTER_ID = "prompt-library-execution-dispatch"
PROMPT_LIBRARY_MODE_BROWSER_ADAPTER_ID = "prompt-library-mode-browser"
PROMPT_LIBRARY_WORKFLOW_BROWSER_ADAPTER_ID = "prompt-library-workflow-browser"

PROMPT_LIBRARY_FIELD_ID = "prompt-library-state"
PROMPT_LIBRARY_WIDGET_NAME = "spm_data"
PROMPT_LIBRARY_MODE_PROPERTY = "spmPrivacyMode"
PROMPT_LIBRARY_SUBJECT_MODE_BINDING_ID = "prompt-library-mode-reference"
PROMPT_LIBRARY_SUBJECT_MODE_INPUT = "privacy_mode_reference"
PROMPT_LIBRARY_PROJECTION_ID = "resolve-prompt"
PROMPT_LIBRARY_EXECUTION_INPUT = "private_execution"

PROMPT_LIBRARY_LEGACY_BINDING_ID = "prompt-library-state-smart-prompt-v1"
PROMPT_LIBRARY_LEGACY_KEY_BINDING_ID = "prompt-library-state-smart-prompt-json-key-v1"

# S2 owns the declarations that make this slot part of the installed profile.
# Keeping the identity here prevents later slices from inventing another slot.
SMART_PROMPT_DEFERRED_ADAPTER_SLOTS = (PROMPT_LIBRARY_OPERATION_ADAPTER_ID,)

# Auditable inventory of local mechanisms removed by the atomic activation.
SMART_PROMPT_LOCAL_PRIVACY_REMOVAL_INVENTORY = (
    "browser-envelope-memos-and-pending-promises",
    "browser-encryption-sequence-tracking",
    "browser-clear-on-encryption-failure",
    "per-node-serialize-hooks",
    "graph-to-prompt-privacy-wait-patch",
    "local-privacy-toggle-policy",
)


@dataclass(frozen=True, slots=True)
class SmartPromptPrivacyFragment:
    """Composable declarations for later Smart Prompt privacy slices."""

    resources: tuple[ProfileResource, ...] = ()
    server_adapters: tuple[AdapterSlot, ...] = ()
    browser_adapters: tuple[AdapterSlot, ...] = ()
    scopes: tuple[PrivacyScope, ...] = ()
    protected_fields: tuple[ProtectedField, ...] = ()
    subject_mode_bindings: tuple[SubjectModeBinding, ...] = ()
    execution_projections: tuple[SemanticExecutionProjection, ...] = ()
    legacy_bindings: tuple[LegacyReaderBinding, ...] = ()
    legacy_key_imports: tuple[LegacyKeyImportBinding, ...] = ()
    protected_operations: tuple[object, ...] = ()
    records: tuple[object, ...] = ()
    singletons: tuple[object, ...] = ()
    artifacts: tuple[object, ...] = ()
    record_reference_migrations: tuple[object, ...] = ()
    opaque_reference_kinds: tuple[object, ...] = ()
    safe_payload_projections: tuple[object, ...] = ()


def smart_prompt_s1_privacy_fragment() -> SmartPromptPrivacyFragment:
    """Return the S1 workflow/editor declaration."""

    return SmartPromptPrivacyFragment(
        resources=(
            ProfileResource(
                PROMPT_LIBRARY_MODE_RESOURCE_ID,
                ResourceKind.MODE,
                (
                    PROMPT_LIBRARY_MODE_ADAPTER_ID,
                    PROMPT_LIBRARY_MODE_BROWSER_ADAPTER_ID,
                ),
            ),
            ProfileResource(
                PROMPT_LIBRARY_WORKFLOW_RESOURCE_ID,
                ResourceKind.WORKFLOW,
                (
                    PROMPT_LIBRARY_WORKFLOW_ADAPTER_ID,
                    PROMPT_LIBRARY_WORKFLOW_BROWSER_ADAPTER_ID,
                ),
            ),
            ProfileResource(
                PROMPT_LIBRARY_EXECUTION_RESOURCE_ID,
                ResourceKind.EXECUTION,
                (
                    PROMPT_LIBRARY_PROJECTION_ADAPTER_ID,
                    PROMPT_LIBRARY_DISPATCH_ADAPTER_ID,
                ),
            ),
        ),
        server_adapters=(
            AdapterSlot(
                PROMPT_LIBRARY_MODE_ADAPTER_ID,
                ResourceKind.MODE,
                PROMPT_LIBRARY_MODE_RESOURCE_ID,
            ),
            AdapterSlot(
                PROMPT_LIBRARY_WORKFLOW_ADAPTER_ID,
                ResourceKind.WORKFLOW,
                PROMPT_LIBRARY_WORKFLOW_RESOURCE_ID,
            ),
            AdapterSlot(
                PROMPT_LIBRARY_PROJECTION_ADAPTER_ID,
                ResourceKind.EXECUTION,
                PROMPT_LIBRARY_EXECUTION_RESOURCE_ID,
            ),
            AdapterSlot(
                PROMPT_LIBRARY_DISPATCH_ADAPTER_ID,
                ResourceKind.EXECUTION,
                PROMPT_LIBRARY_EXECUTION_RESOURCE_ID,
            ),
        ),
        browser_adapters=(
            AdapterSlot(
                PROMPT_LIBRARY_MODE_BROWSER_ADAPTER_ID,
                ResourceKind.MODE,
                PROMPT_LIBRARY_MODE_RESOURCE_ID,
                (SMART_PROMPT_NODE_TYPE,),
            ),
            AdapterSlot(
                PROMPT_LIBRARY_WORKFLOW_BROWSER_ADAPTER_ID,
                ResourceKind.WORKFLOW,
                PROMPT_LIBRARY_WORKFLOW_RESOURCE_ID,
                (SMART_PROMPT_NODE_TYPE,),
            ),
        ),
        scopes=(
            PrivacyScope(
                PROMPT_LIBRARY_SCOPE_ID,
                PROMPT_LIBRARY_MODE_RESOURCE_ID,
                PROMPT_LIBRARY_MODE_ADAPTER_ID,
                PROMPT_LIBRARY_MODE_BROWSER_ADAPTER_ID,
            ),
        ),
        protected_fields=(
            ProtectedField(
                PROMPT_LIBRARY_FIELD_ID,
                PROMPT_LIBRARY_WORKFLOW_RESOURCE_ID,
                PROMPT_LIBRARY_SCOPE_ID,
                PROMPT_LIBRARY_WORKFLOW_ADAPTER_ID,
                PROMPT_LIBRARY_WORKFLOW_BROWSER_ADAPTER_ID,
                (SMART_PROMPT_NODE_TYPE,),
                FieldLocation(FieldLocationKind.WIDGET, PROMPT_LIBRARY_WIDGET_NAME),
                SMART_PROMPT_CURRENT_SCHEMA,
                PROMPT_LIBRARY_FIELD_ID,
                ProtectedStateAuthority.EXTERNAL_BROWSER_WORKFLOW,
                ExternalTransitionPolicy(
                    max_original_bytes_per_owner=16 * 1024 * 1024,
                    max_target_bytes_per_owner=16 * 1024 * 1024,
                ),
                legacy_reader_ids=(SMART_PROMPT_V1_READER_ID,),
                execution=True,
            ),
        ),
        subject_mode_bindings=(
            SubjectModeBinding(
                PROMPT_LIBRARY_SUBJECT_MODE_BINDING_ID,
                PROMPT_LIBRARY_SCOPE_ID,
                PROMPT_LIBRARY_SUBJECT_MODE_INPUT,
                (SMART_PROMPT_NODE_TYPE,),
            ),
        ),
        execution_projections=(
            SemanticExecutionProjection(
                PROMPT_LIBRARY_PROJECTION_ID,
                PROMPT_LIBRARY_EXECUTION_RESOURCE_ID,
                PROMPT_LIBRARY_WORKFLOW_RESOURCE_ID,
                PROMPT_LIBRARY_PROJECTION_ADAPTER_ID,
                PROMPT_LIBRARY_DISPATCH_ADAPTER_ID,
                PROMPT_LIBRARY_SUBJECT_MODE_BINDING_ID,
                PROMPT_LIBRARY_EXECUTION_INPUT,
            ),
        ),
        legacy_bindings=(
            LegacyReaderBinding(
                PROMPT_LIBRARY_LEGACY_BINDING_ID,
                SMART_PROMPT_V1_READER_ID,
                PROMPT_LIBRARY_WORKFLOW_RESOURCE_ID,
                LegacyLocationKind.WORKFLOW_FIELD,
                PROMPT_LIBRARY_FIELD_ID,
            ),
        ),
        legacy_key_imports=(
            LegacyKeyImportBinding(
                PROMPT_LIBRARY_LEGACY_KEY_BINDING_ID,
                SMART_PROMPT_V1_JSON_KEY_IMPORT_ID,
                PROMPT_LIBRARY_WORKFLOW_RESOURCE_ID,
                LegacyLocationKind.WORKFLOW_FIELD,
                PROMPT_LIBRARY_FIELD_ID,
                LegacyKeyFormat.JSON,
            ),
        ),
    )


def build_smart_prompt_privacy_profile(
    *fragments: SmartPromptPrivacyFragment,
) -> PrivacyProfile:
    """Compose S1 with later disjoint slices into one immutable profile."""

    declarations = (smart_prompt_s1_privacy_fragment(), *fragments)
    values: dict[str, tuple[object, ...]] = {}
    for field in fields(SmartPromptPrivacyFragment):
        values[field.name] = tuple(
            item
            for fragment in declarations
            for item in getattr(fragment, field.name)
        )
    values["resources"] = _merge_resources(values["resources"])
    profile = PrivacyProfile(
        id=SMART_PROMPT_PROFILE_ID,
        distribution=SMART_PROMPT_DISTRIBUTION,
        **values,
    )
    if (
        not fragments
        and SMART_PROMPT_S1_PROFILE_FINGERPRINT
        and profile.fingerprint != SMART_PROMPT_S1_PROFILE_FINGERPRINT
    ):
        raise RuntimeError("Smart Prompt S1 privacy profile fingerprint changed unexpectedly.")
    return profile


def _merge_resources(resources: tuple[object, ...]) -> tuple[ProfileResource, ...]:
    merged: dict[str, ProfileResource] = {}
    for candidate in resources:
        if not isinstance(candidate, ProfileResource):
            raise TypeError("Smart Prompt privacy fragment resource is invalid.")
        existing = merged.get(candidate.id)
        if existing is not None and existing.kind is not candidate.kind:
            raise ValueError("Smart Prompt privacy resource kind changed across fragments.")
        slots = candidate.adapter_slots if existing is None else (
            *existing.adapter_slots,
            *candidate.adapter_slots,
        )
        merged[candidate.id] = ProfileResource(
            candidate.id,
            candidate.kind,
            tuple(dict.fromkeys(slots)),
        )
    return tuple(merged.values())


def _require_scope(scope_id: str) -> None:
    if scope_id != PROMPT_LIBRARY_SCOPE_ID:
        raise ValueError("Unknown Smart Prompt privacy scope.")


def _declared_mode(value: object) -> str:
    if value is False:
        return "public"
    if value is True:
        return "private"
    return "inherit"


class SmartPromptModeAdapter:
    """Revisioned CAS facade over the legacy Smart Prompt mode mirror."""

    def __init__(self, declarations: Mapping[str, object] | None = None) -> None:
        self._declarations = dict(declarations or {})
        self._revision = 0
        self._mode_lock = RLock()

    def read_declared_mode(self, scope_id: str) -> str:
        return str(self.read_mode_source(scope_id)["declared"])

    def write_declared_mode(self, scope_id: str, mode: object) -> None:
        target = _declared_mode_value(mode)
        with self._mode_lock:
            _require_scope(scope_id)
            if _declared_mode(self._declarations.get(scope_id)) == target:
                return
            self._write_mode(target)
            self._revision += 1

    def read_mode_source(self, scope_id: str) -> dict[str, object]:
        with self._mode_lock:
            _require_scope(scope_id)
            return self._snapshot()

    def compare_and_set_mode_source(
        self,
        scope_id: str,
        expected_revision: object,
        expected_declared: object,
        target_declared: object,
    ) -> dict[str, object]:
        expected = _mode_source_snapshot(
            {"revision": expected_revision, "declared": expected_declared}
        )
        target = _declared_mode_value(target_declared)
        with self._mode_lock:
            _require_scope(scope_id)
            if self._snapshot() != expected:
                raise RuntimeError("Smart Prompt privacy mode source changed concurrently.")
            self._write_mode(target)
            self._revision = int(expected["revision"]) + 1
            return self._snapshot()

    def classify_mode_source(
        self,
        scope_id: str,
        prior: object,
        target: object,
    ) -> str:
        current = self.read_mode_source(scope_id)
        normalized_prior = _mode_source_snapshot(prior)
        normalized_target = _mode_source_snapshot(target)
        if current == normalized_prior:
            return "prior"
        if current == normalized_target:
            return "target"
        return "diverged"

    def rollback_mode_source(
        self,
        scope_id: str,
        target: object,
        prior: object,
    ) -> dict[str, object]:
        normalized_target = _mode_source_snapshot(target)
        normalized_prior = _mode_source_snapshot(prior)
        restored = {
            "revision": int(normalized_target["revision"]) + 1,
            "declared": normalized_prior["declared"],
        }
        with self._mode_lock:
            _require_scope(scope_id)
            current = self._snapshot()
            if current == restored:
                return current
            if current != normalized_target:
                raise RuntimeError("Smart Prompt privacy mode source changed concurrently.")
            self._write_mode(str(restored["declared"]))
            self._revision = int(restored["revision"])
            return self._snapshot()

    def _snapshot(self) -> dict[str, object]:
        return {
            "revision": self._revision,
            "declared": _declared_mode(
                self._declarations.get(PROMPT_LIBRARY_SCOPE_ID)
            ),
        }

    def _write_mode(self, mode: str) -> None:
        if mode == "inherit":
            self._declarations.pop(PROMPT_LIBRARY_SCOPE_ID, None)
        else:
            self._declarations[PROMPT_LIBRARY_SCOPE_ID] = mode == "private"


def _declared_mode_value(value: object) -> str:
    candidate = getattr(value, "value", value)
    if candidate is True:
        candidate = "private"
    elif candidate is False:
        candidate = "public"
    if candidate not in {"inherit", "private", "public"}:
        raise ValueError("Invalid Smart Prompt privacy declaration.")
    return str(candidate)


def _mode_source_snapshot(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping) or set(value) != {"revision", "declared"}:
        raise ValueError("Invalid Smart Prompt privacy mode source snapshot.")
    revision = value["revision"]
    if type(revision) is not int or revision < 0:
        raise ValueError("Invalid Smart Prompt privacy mode source snapshot.")
    return {
        "revision": revision,
        "declared": _declared_mode_value(value["declared"]),
    }


def _declaration_id(declaration: object) -> str:
    field_id = getattr(declaration, "id", None)
    if field_id != PROMPT_LIBRARY_FIELD_ID:
        raise ValueError("Unknown Smart Prompt protected field.")
    return field_id


def _raw_state(value: object) -> tuple[Mapping[str, object], bool]:
    candidate = value
    if isinstance(candidate, str):
        try:
            candidate = json.loads(candidate)
        except (TypeError, ValueError):
            return {}, False
    if not isinstance(candidate, Mapping):
        return {}, False
    if candidate.get("encrypted") is True:
        raise ValueError("Protected Smart Prompt state cannot be normalized as plaintext.")
    return candidate, "privacyMode" in candidate


def normalize_prompt_library_state(value: object) -> dict[str, object]:
    """Preserve explicit legacy public state; make missing/malformed state private."""

    candidate, has_explicit_mode = _raw_state(value)
    normalized, _warnings = normalize_state(candidate)
    if not has_explicit_mode:
        normalized["privacyMode"] = True
    return normalized


class SmartPromptWorkflowStateAdapter:
    """Normalize and locate the full hidden prompt-library workflow field."""

    def capture(self, source: object, declaration: object) -> object:
        _declaration_id(declaration)
        if isinstance(source, Mapping):
            if PROMPT_LIBRARY_WIDGET_NAME not in source:
                raise ValueError("Smart Prompt workflow state is unavailable.")
            value = source[PROMPT_LIBRARY_WIDGET_NAME]
        else:
            value = getattr(source, PROMPT_LIBRARY_WIDGET_NAME)
        return copy.deepcopy(value)

    def normalize(self, value: object, declaration: object) -> dict[str, object]:
        _declaration_id(declaration)
        return normalize_prompt_library_state(value)

    def apply_revealed(self, target: object, value: object, declaration: object) -> None:
        normalized = self.normalize(value, declaration)
        serialized = state_to_json(normalized)
        if isinstance(target, dict):
            target[PROMPT_LIBRARY_WIDGET_NAME] = serialized
        else:
            setattr(target, PROMPT_LIBRARY_WIDGET_NAME, serialized)

    def clear_plaintext(self, target: object, declaration: object) -> None:
        _declaration_id(declaration)
        if isinstance(target, dict):
            target[PROMPT_LIBRARY_WIDGET_NAME] = ""
        else:
            setattr(target, PROMPT_LIBRARY_WIDGET_NAME, "")

    def classify_mode_transition_representation(
        self,
        value: object,
        _context: object,
    ) -> str:
        payload = _decode_exact_transition_json(value)
        if _is_exact_current_envelope(payload):
            return "private"
        if _PROTECTED_MARKERS.intersection(payload):
            raise ValueError("Smart Prompt mode transition representation is invalid.")
        self.normalize_mode_transition_value(payload, _context)
        return "public"

    def decode_mode_transition_representation(
        self,
        value: object,
        context: object,
    ) -> object:
        payload = _decode_exact_transition_json(value)
        if self.classify_mode_transition_representation(value, context) == "private":
            return PrivacyEnvelopeCodec(SMART_PROMPT_CURRENT_SCHEMA).decrypt_state(payload)
        return payload

    def normalize_mode_transition_value(
        self,
        value: object,
        _context: object,
    ) -> dict[str, object]:
        return normalize_prompt_library_state(value)

    def encode_public_mode_transition(
        self,
        value: object,
        context: object,
    ) -> bytes:
        try:
            return json.dumps(
                self.normalize_mode_transition_value(value, context),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError, UnicodeError, RecursionError):
            raise ValueError(
                "Smart Prompt mode transition representation is invalid."
            ) from None


_ENVELOPE_KEYS = frozenset(
    {"version", "schema", "encrypted", "algorithm", "keyId", "nonce", "ciphertext"}
)
_PROTECTED_MARKERS = frozenset(
    {"algorithm", "ciphertext", "encrypted", "keyId", "nonce", "private", "schema"}
)


def _decode_exact_transition_json(value: object) -> dict[str, object]:
    if not isinstance(value, (bytes, bytearray, memoryview)):
        raise ValueError("Smart Prompt mode transition representation is invalid.")

    def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, item in pairs:
            if key in result:
                raise ValueError
            result[key] = item
        return result

    def reject_constant(_value: str) -> object:
        raise ValueError

    try:
        text = bytes(value).decode("utf-8", errors="strict")
        if not text.strip():
            raise ValueError
        payload = json.loads(
            text,
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
    except (TypeError, ValueError, UnicodeError, json.JSONDecodeError, RecursionError):
        raise ValueError(
            "Smart Prompt mode transition representation is invalid."
        ) from None
    if not isinstance(payload, dict):
        raise ValueError("Smart Prompt mode transition representation is invalid.")
    return payload


def _is_exact_current_envelope(value: Mapping[str, object]) -> bool:
    return (
        set(value) == _ENVELOPE_KEYS
        and value.get("version") == 1
        and value.get("schema") == SMART_PROMPT_CURRENT_SCHEMA
        and value.get("encrypted") is True
        and value.get("algorithm") == "AES-256-GCM"
        and isinstance(value.get("keyId"), str)
        and bool(value.get("keyId"))
        and _valid_base64url(value.get("nonce"), exact_bytes=12)
        and _valid_base64url(value.get("ciphertext"), minimum_bytes=16)
    )


def _valid_base64url(
    value: object,
    *,
    exact_bytes: int | None = None,
    minimum_bytes: int | None = None,
) -> bool:
    if not isinstance(value, str) or not value or "=" in value:
        return False
    try:
        decoded = base64.b64decode(
            value + "=" * (-len(value) % 4),
            altchars=b"-_",
            validate=True,
        )
    except (ValueError, UnicodeError):
        return False
    return (
        base64.urlsafe_b64encode(decoded).rstrip(b"=").decode("ascii") == value
        and (exact_bytes is None or len(decoded) == exact_bytes)
        and (minimum_bytes is None or len(decoded) >= minimum_bytes)
    )


class SmartPromptExecutionProjectionAdapter:
    """Project exactly one settled library generation into product semantics."""

    def project(self, values: Mapping[str, object], declaration: object) -> dict[str, object]:
        if (
            getattr(declaration, "id", None) != PROMPT_LIBRARY_PROJECTION_ID
            or set(values) != {PROMPT_LIBRARY_FIELD_ID}
        ):
            raise ValueError("Smart Prompt execution snapshot is incomplete or unknown.")
        return normalize_prompt_library_state(values[PROMPT_LIBRARY_FIELD_ID])


class SmartPromptExecutionDispatchAdapter:
    """Invoke product resolution only after shared execution has revealed state."""

    def __init__(
        self,
        resolver: Callable[[object, object], object] | None = None,
    ) -> None:
        self._resolver = resolver

    def dispatch(self, value: object, context: object, cancellation: object) -> object:
        resolver = self._resolver
        if resolver is None and isinstance(context, Mapping):
            candidate = context.get("resolve_prompt")
            resolver = candidate if callable(candidate) else None
        if resolver is None:
            raise ValueError("Smart Prompt execution resolver is unavailable.")
        checkpoint = getattr(cancellation, "checkpoint", None)
        if callable(checkpoint):
            checkpoint()
        return resolver(value, context)


def build_smart_prompt_server_adapters(
    *,
    declarations: Mapping[str, object] | None = None,
    resolver: Callable[[object, object], object] | None = None,
) -> dict[str, object]:
    """Build only the truthful S1 server adapters; nothing is installed here."""

    return {
        PROMPT_LIBRARY_MODE_ADAPTER_ID: SmartPromptModeAdapter(declarations),
        PROMPT_LIBRARY_WORKFLOW_ADAPTER_ID: SmartPromptWorkflowStateAdapter(),
        PROMPT_LIBRARY_PROJECTION_ADAPTER_ID: SmartPromptExecutionProjectionAdapter(),
        PROMPT_LIBRARY_DISPATCH_ADAPTER_ID: SmartPromptExecutionDispatchAdapter(resolver),
    }
