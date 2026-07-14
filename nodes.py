"""ComfyUI backend node for Smart Prompt Manager."""

from __future__ import annotations

import hashlib
import json
from typing import Any

try:
    from .managed_execution import (
        consume_smart_prompt_subject_mode,
        dispatch_smart_prompt_managed_execution,
        smart_prompt_subject_requires_private_execution,
    )
    from .resolver import needed_variable_definitions, resolve_prompt
    from .schema import default_state, parse_state, selected_prompt, state_to_json
    from .validation import validate_state
except ImportError:  # Allows running tests from the repository root.
    from managed_execution import (
        consume_smart_prompt_subject_mode,
        dispatch_smart_prompt_managed_execution,
        smart_prompt_subject_requires_private_execution,
    )
    from resolver import needed_variable_definitions, resolve_prompt
    from schema import default_state, parse_state, selected_prompt, state_to_json
    from validation import validate_state


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def _reject_protected_public_input(value: object) -> None:
    try:
        payload = json.loads(value) if isinstance(value, str) else value
    except (TypeError, ValueError):
        return
    if isinstance(payload, dict) and (
        payload.get("encrypted") is True or "ciphertext" in payload
    ):
        raise ValueError("PRIVACY_EXECUTION_REFERENCE_INVALID")


class SmartPromptManager:
    """Reusable prompt library with deterministic variable resolution."""

    CATEGORY = "Helto/Prompt"
    FUNCTION = "resolve"
    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = (
        "resolved_prompt",
        "raw_prompt",
        "prompt_name",
        "variables_json",
        "selected_values_json",
        "warnings_json",
    )
    SEARCH_ALIASES = ["prompt manager", "smart prompt", "random prompt variables"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "spm_data": (
                    "STRING",
                    {
                        "default": state_to_json(default_state()),
                        "multiline": True,
                        "dynamicPrompts": False,
                    },
                ),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFFFFFFFFFF, "control_after_generate": "fixed"}),
                "reroll": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFF}),
            },
            "optional": {
                "privacy_mode_reference": (
                    "STRING",
                    {"default": "", "socketless": True, "hidden": True},
                ),
                "private_execution": (
                    "STRING",
                    {"default": "", "socketless": True, "hidden": True},
                ),
            },
            "hidden": {"unique_id": "UNIQUE_ID"},
        }

    @classmethod
    def IS_CHANGED(
        cls,
        spm_data: str,
        seed: int = 0,
        reroll: int = 0,
        private_execution: str = "",
        **_kwargs: object,
    ):
        if private_execution:
            return float("nan")
        payload = f"{spm_data}\n{seed}\n{reroll}".encode("utf-8", errors="replace")
        return hashlib.sha256(payload).hexdigest()

    def resolve(
        self,
        spm_data: str,
        seed: int = 0,
        reroll: int = 0,
        unique_id=None,
        privacy_mode_reference: str = "",
        private_execution: str = "",
        _subject_mode_lease: object = None,
    ):
        if _subject_mode_lease is None and privacy_mode_reference:
            if unique_id is None:
                raise ValueError("PRIVACY_SUBJECT_MODE_REFERENCE_INVALID")
            with consume_smart_prompt_subject_mode(
                privacy_mode_reference,
                unique_id,
            ) as lease:
                return self.resolve(
                    spm_data,
                    seed,
                    reroll,
                    unique_id,
                    "",
                    private_execution,
                    lease,
                )
        if unique_id is not None and _subject_mode_lease is None:
            raise ValueError("PRIVACY_SUBJECT_MODE_REFERENCE_INVALID")
        private_required = (
            _subject_mode_lease is not None
            and smart_prompt_subject_requires_private_execution(
                _subject_mode_lease
            )
        )
        if private_required and not private_execution:
            raise ValueError("PRIVACY_EXECUTION_REFERENCE_INVALID")
        if private_execution:
            return dispatch_smart_prompt_managed_execution(
                private_execution,
                subject_id=unique_id,
                seed=seed,
                reroll=reroll,
            )

        _reject_protected_public_input(spm_data)
        state, parse_warnings = parse_state(spm_data)
        prompt = selected_prompt(state)
        raw_prompt = str(prompt.get("text", "")) if prompt else ""
        prompt_name = str(prompt.get("title", "")) if prompt else ""

        resolution = resolve_prompt(
            raw_prompt,
            state.get("variables", {}),
            seed=seed,
            reroll=reroll,
            cycle_state=state.get("cycleState", {}),
        )

        validation_warnings = validate_state(state)
        warning_messages = list(parse_warnings)
        warning_messages.extend(resolution.get("warnings", []))
        warning_messages.extend(item.get("message", str(item)) for item in validation_warnings)
        if not prompt:
            warning_messages.append("No selected prompt is available.")

        variables_json = _json(
            {
                "all": state.get("variables", {}),
                "used": needed_variable_definitions(raw_prompt, state.get("variables", {})),
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


NODE_CLASS_MAPPINGS = {"SmartPromptManager": SmartPromptManager}
NODE_DISPLAY_NAME_MAPPINGS = {"SmartPromptManager": "Smart Prompt Manager"}
