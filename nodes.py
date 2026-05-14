"""ComfyUI backend node for Smart Prompt Manager."""

from __future__ import annotations

import hashlib
import json
from typing import Any

try:
    from .resolver import needed_variable_definitions, resolve_prompt
    from .schema import default_state, parse_state, selected_prompt, state_to_json
    from .validation import validate_state
except ImportError:  # Allows running tests from the repository root.
    from resolver import needed_variable_definitions, resolve_prompt
    from schema import default_state, parse_state, selected_prompt, state_to_json
    from validation import validate_state


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


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
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFFFFFFFFFF}),
                "reroll": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFF}),
            }
        }

    @classmethod
    def IS_CHANGED(cls, spm_data: str, seed: int = 0, reroll: int = 0):
        payload = f"{spm_data}\n{seed}\n{reroll}".encode("utf-8", errors="replace")
        return hashlib.sha256(payload).hexdigest()

    def resolve(self, spm_data: str, seed: int = 0, reroll: int = 0):
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
