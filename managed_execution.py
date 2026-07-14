"""Shared protected-execution slice for Smart Prompt Manager."""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator

from helto_privacy import ProtectedOperation

try:
    from .managed_import_export import (
        SmartPromptImportExportAdapter,
        build_smart_prompt_s2_server_adapters,
        smart_prompt_s2_privacy_fragment,
    )
    from .managed_privacy import (
        PROMPT_LIBRARY_DISPATCH_ADAPTER_ID,
        PROMPT_LIBRARY_FIELD_ID,
        PROMPT_LIBRARY_OPERATION_ADAPTER_ID,
        PROMPT_LIBRARY_PROJECTION_ADAPTER_ID,
        PROMPT_LIBRARY_PROJECTION_ID,
        PROMPT_LIBRARY_WORKFLOW_RESOURCE_ID,
        SmartPromptPrivacyFragment,
        build_smart_prompt_privacy_profile,
        normalize_prompt_library_state,
    )
    from .resolver import needed_variable_definitions, resolve_prompt
    from .schema import selected_prompt
    from .validation import validate_state
except ImportError:  # Allows running tests from the repository root.
    from managed_import_export import (
        SmartPromptImportExportAdapter,
        build_smart_prompt_s2_server_adapters,
        smart_prompt_s2_privacy_fragment,
    )
    from managed_privacy import (
        PROMPT_LIBRARY_DISPATCH_ADAPTER_ID,
        PROMPT_LIBRARY_FIELD_ID,
        PROMPT_LIBRARY_OPERATION_ADAPTER_ID,
        PROMPT_LIBRARY_PROJECTION_ADAPTER_ID,
        PROMPT_LIBRARY_PROJECTION_ID,
        PROMPT_LIBRARY_WORKFLOW_RESOURCE_ID,
        SmartPromptPrivacyFragment,
        build_smart_prompt_privacy_profile,
        normalize_prompt_library_state,
    )
    from resolver import needed_variable_definitions, resolve_prompt
    from schema import selected_prompt
    from validation import validate_state


RESOLVE_PROMPT_OPERATION_ID = "resolve-prompt"
RESOLVE_PROMPT_ROUTE = "/helto_spm/privacy/resolve-prompt"
SMART_PROMPT_S3_PROFILE_FINGERPRINT = (
    "5a352fd3fb086cd3418039368457e7a2fbd8b4ae81aa0deae6151d8bcbd22352"
)

SMART_PROMPT_S3_LOCAL_REMOVAL_INVENTORY = (
    "browser-unkeyed-spm-cache-token",
    "browser-plaintext-semantic-sha256",
    "browser-graph-prompt-token-substitution",
    "backend-cache-token-workflow-lookup",
    "backend-missing-reference-empty-library-fallback",
    "backend-decrypt-failure-empty-library-fallback",
)


def _managed_reference(value: object, error_code: str) -> Mapping[str, object]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            raise ValueError(error_code) from None
    if not isinstance(value, Mapping):
        raise ValueError(error_code)
    return value


@contextmanager
def consume_smart_prompt_subject_mode(
    reference: object,
    subject_id: object,
) -> Iterator[object]:
    """Consume one server-issued mode reference for the exact node owner."""

    parsed = _managed_reference(
        reference,
        "PRIVACY_SUBJECT_MODE_REFERENCE_INVALID",
    )
    from helto_privacy.runtime import bound_privacy_pack

    pack = bound_privacy_pack("helto.smart-prompt-manager")
    with pack.subject_modes("prompt-library-mode-reference").consume(
        parsed,
        subject_id,
    ) as lease:
        yield lease


def smart_prompt_subject_requires_private_execution(lease: object) -> bool:
    """Return the server-attested effective mode for an active owner lease."""

    from helto_privacy.runtime import bound_privacy_pack

    pack = bound_privacy_pack("helto.smart-prompt-manager")
    check = getattr(lease, "requires_private_execution", None)
    if not callable(check):
        raise ValueError("PRIVACY_SUBJECT_MODE_REFERENCE_INVALID")
    return bool(
        check(
            profile=pack.profile,
            binding_id="prompt-library-mode-reference",
        )
    )


def dispatch_smart_prompt_managed_execution(
    reference: object,
    *,
    subject_id: object,
    seed: int,
    reroll: int,
) -> tuple[str, str, str, str, str, str]:
    """Resolve one protected prompt-library snapshot through shared RAM only."""

    parsed = _managed_reference(reference, "PRIVACY_EXECUTION_REFERENCE_INVALID")
    from helto_privacy.runtime import bound_privacy_pack

    result = bound_privacy_pack("helto.smart-prompt-manager").execution(
        "prompt-library-execution"
    ).dispatch(
        parsed,
        {"seed": seed, "reroll": reroll},
        subject_id=subject_id,
        cache_discriminator={"seed": seed, "reroll": reroll},
    )
    value = result.value
    if not isinstance(value, tuple) or len(value) != 6 or any(
        not isinstance(item, str) for item in value
    ):
        raise SmartPromptExecutionProductError(
            "Smart Prompt managed execution returned an invalid product result."
        )
    return value


class SmartPromptExecutionProductError(RuntimeError):
    """Sanitized product failure that never substitutes a default library."""


@dataclass(frozen=True, slots=True)
class SmartPromptResolveOperationContext:
    execution_handle: object = field(repr=False)
    subject_id: str
    seed: int
    reroll: int

    @property
    def operation_id(self) -> str:
        return RESOLVE_PROMPT_OPERATION_ID


def smart_prompt_s3_privacy_fragment() -> SmartPromptPrivacyFragment:
    """Declare the protected resolve route over the S1 execution projection."""

    return SmartPromptPrivacyFragment(
        protected_operations=(
            ProtectedOperation(
                RESOLVE_PROMPT_OPERATION_ID,
                PROMPT_LIBRARY_WORKFLOW_RESOURCE_ID,
                PROMPT_LIBRARY_OPERATION_ADAPTER_ID,
                RESOLVE_PROMPT_ROUTE,
            ),
        ),
    )


def build_smart_prompt_s3_privacy_profile():
    profile = build_smart_prompt_privacy_profile(
        smart_prompt_s2_privacy_fragment(),
        smart_prompt_s3_privacy_fragment(),
    )
    if (
        SMART_PROMPT_S3_PROFILE_FINGERPRINT
        and profile.fingerprint != SMART_PROMPT_S3_PROFILE_FINGERPRINT
    ):
        raise RuntimeError("Smart Prompt S3 privacy profile fingerprint changed unexpectedly.")
    return profile


class SmartPromptSemanticProjectionAdapter:
    """Project exactly the state that determines prompt resolution semantics."""

    def project(self, values: Mapping[str, object], declaration: object) -> dict[str, object]:
        if (
            getattr(declaration, "id", None) != PROMPT_LIBRARY_PROJECTION_ID
            or set(values) != {PROMPT_LIBRARY_FIELD_ID}
        ):
            raise SmartPromptExecutionProductError(
                "Smart Prompt execution snapshot is incomplete."
            )
        state = normalize_prompt_library_state(values[PROMPT_LIBRARY_FIELD_ID])
        prompt = selected_prompt(state)
        if not prompt or prompt.get("id") != state.get("selectedPromptId"):
            raise SmartPromptExecutionProductError(
                "Smart Prompt execution has no selected prompt."
            )
        return {
            "selectedPromptId": str(state["selectedPromptId"]),
            "selectedFolderId": str(state["selectedFolderId"]),
            "folderIds": [str(item["id"]) for item in state["folders"]],
            "prompts": [
                {
                    "id": str(item["id"]),
                    "title": str(item["title"]),
                    "text": str(item["text"]),
                }
                for item in state["prompts"]
            ],
            "variables": copy.deepcopy(state["variables"]),
            "cycleState": copy.deepcopy(state["cycleState"]),
        }


class SmartPromptExecutionDispatchAdapter:
    """Run unchanged product resolution after shared grant validation/reveal."""

    def dispatch(self, semantic: object, context: object, cancellation: object):
        checkpoint = getattr(cancellation, "checkpoint", None)
        if callable(checkpoint):
            checkpoint()
        if not isinstance(context, Mapping):
            raise SmartPromptExecutionProductError(
                "Smart Prompt execution context is unavailable."
            )
        if set(context) != {"seed", "reroll"}:
            raise SmartPromptExecutionProductError(
                "Smart Prompt execution context is incomplete."
            )
        seed = context["seed"]
        reroll = context["reroll"]
        if (
            not isinstance(seed, int)
            or isinstance(seed, bool)
            or not isinstance(reroll, int)
            or isinstance(reroll, bool)
        ):
            raise SmartPromptExecutionProductError(
                "Smart Prompt execution context is invalid."
            )
        return resolve_smart_prompt_semantic(semantic, seed=seed, reroll=reroll)


def resolve_smart_prompt_semantic(
    semantic: object,
    *,
    seed: int,
    reroll: int,
) -> tuple[str, str, str, str, str, str]:
    """Return the exact six existing Smart Prompt node outputs."""

    state = _semantic_state(semantic)
    prompt = selected_prompt(state)
    if not prompt:
        raise SmartPromptExecutionProductError(
            "Smart Prompt execution has no selected prompt."
        )
    raw_prompt = str(prompt.get("text", ""))
    prompt_name = str(prompt.get("title", ""))
    resolution = resolve_prompt(
        raw_prompt,
        state["variables"],
        seed=seed,
        reroll=reroll,
        cycle_state=state["cycleState"],
    )
    warning_messages = list(resolution.get("warnings", []))
    warning_messages.extend(
        item.get("message", str(item)) for item in validate_state(state)
    )
    variables_json = _json(
        {
            "all": state["variables"],
            "used": needed_variable_definitions(raw_prompt, state["variables"]),
            "variablesUsed": resolution.get("variables_used", []),
        }
    )
    selected_values_json = _json(resolution.get("selected_values", {}))
    warnings_json = _json(
        {
            "warnings": warning_messages,
            "missingVariables": resolution.get("missing_variables", []),
            "variablesUsed": resolution.get("variables_used", []),
        }
    )
    return (
        str(resolution.get("resolved_prompt", raw_prompt)),
        raw_prompt,
        prompt_name,
        variables_json,
        selected_values_json,
        warnings_json,
    )


def _semantic_state(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping) or set(value) != {
        "selectedPromptId",
        "selectedFolderId",
        "folderIds",
        "prompts",
        "variables",
        "cycleState",
    }:
        raise SmartPromptExecutionProductError(
            "Smart Prompt execution semantics are invalid."
        )
    folder_ids = value["folderIds"]
    prompts = value["prompts"]
    if (
        not isinstance(folder_ids, list)
        or any(not isinstance(item, str) or not item for item in folder_ids)
        or not isinstance(prompts, list)
        or not prompts
        or not isinstance(value["variables"], Mapping)
        or not isinstance(value["cycleState"], Mapping)
    ):
        raise SmartPromptExecutionProductError(
            "Smart Prompt execution semantics are invalid."
        )
    normalized_prompts = []
    for item in prompts:
        if (
            not isinstance(item, Mapping)
            or set(item) != {"id", "title", "text"}
            or not isinstance(item["id"], str)
            or not item["id"]
            or not isinstance(item["title"], str)
            or not isinstance(item["text"], str)
        ):
            raise SmartPromptExecutionProductError(
                "Smart Prompt execution semantics are invalid."
            )
        normalized_prompts.append(
            {
                "id": item["id"],
                "title": item["title"],
                "text": item["text"],
                "description": "",
                "folderId": "",
                "tags": [],
                "favorite": False,
                "locked": False,
                "hidden": False,
                "createdAt": "",
                "updatedAt": "",
            }
        )
    selected_prompt_id = value["selectedPromptId"]
    if (
        not isinstance(selected_prompt_id, str)
        or selected_prompt_id not in {item["id"] for item in normalized_prompts}
    ):
        raise SmartPromptExecutionProductError(
            "Smart Prompt execution has no selected prompt."
        )
    selected_folder_id = value["selectedFolderId"]
    if not isinstance(selected_folder_id, str):
        raise SmartPromptExecutionProductError(
            "Smart Prompt execution semantics are invalid."
        )
    return {
        "version": 1,
        "selectedFolderId": selected_folder_id,
        "selectedPromptId": selected_prompt_id,
        "search": "",
        "privacyMode": True,
        "folders": [
            {"id": folder_id, "name": "", "hidden": False}
            for folder_id in folder_ids
        ],
        "prompts": normalized_prompts,
        "variables": copy.deepcopy(dict(value["variables"])),
        "cycleState": copy.deepcopy(dict(value["cycleState"])),
        "ui": {"collapsedSections": {}},
    }


class SmartPromptCombinedOperationAdapter:
    """Keep S2 operations and S3 execution routing behind their one profile slot."""

    def __init__(self, import_export: SmartPromptImportExportAdapter) -> None:
        self._import_export = import_export

    def invoke(self, payload: object, context: object, declaration: object = None):
        operation_id = getattr(declaration, "id", None) or getattr(
            context, "operation_id", None
        )
        if operation_id != RESOLVE_PROMPT_OPERATION_ID:
            return self._import_export.invoke(payload, context, declaration)
        if not isinstance(context, SmartPromptResolveOperationContext):
            raise SmartPromptExecutionProductError(
                "Smart Prompt resolve operation context is unavailable."
            )
        if not isinstance(payload, Mapping) or set(payload) != {"private_execution"}:
            raise SmartPromptExecutionProductError(
                "Smart Prompt protected execution reference is required."
            )
        return context.execution_handle.dispatch(
            payload["private_execution"],
            {"seed": context.seed, "reroll": context.reroll},
            subject_id=context.subject_id,
            cache_discriminator={"seed": context.seed, "reroll": context.reroll},
        )


def build_smart_prompt_s3_server_adapters(
    *,
    import_export: SmartPromptImportExportAdapter | None = None,
) -> dict[str, object]:
    import_export = import_export or SmartPromptImportExportAdapter()
    adapters = build_smart_prompt_s2_server_adapters()
    adapters[PROMPT_LIBRARY_PROJECTION_ADAPTER_ID] = (
        SmartPromptSemanticProjectionAdapter()
    )
    adapters[PROMPT_LIBRARY_DISPATCH_ADAPTER_ID] = (
        SmartPromptExecutionDispatchAdapter()
    )
    adapters[PROMPT_LIBRARY_OPERATION_ADAPTER_ID] = (
        SmartPromptCombinedOperationAdapter(import_export)
    )
    return adapters


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
