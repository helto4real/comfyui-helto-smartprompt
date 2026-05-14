"""Validation helpers for Smart Prompt Manager state."""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Mapping

try:
    from .resolver import TOKEN_RE, is_valid_variable_name, variables_used
    from .schema import VIRTUAL_FOLDER_IDS
except ImportError:  # Allows running tests from the repository root.
    from resolver import TOKEN_RE, is_valid_variable_name, variables_used
    from schema import VIRTUAL_FOLDER_IDS


def validate_state(state: Mapping[str, Any]) -> List[Dict[str, str]]:
    warnings: List[Dict[str, str]] = []
    folders = state.get("folders", [])
    prompts = state.get("prompts", [])
    variables = state.get("variables", {})

    folder_ids = {folder.get("id") for folder in folders if isinstance(folder, Mapping)}
    prompt_ids = {prompt.get("id") for prompt in prompts if isinstance(prompt, Mapping)}

    selected_prompt = state.get("selectedPromptId")
    if selected_prompt and selected_prompt not in prompt_ids:
        warnings.append({"code": "selected_prompt_missing", "message": "Selected prompt is missing."})

    selected_folder = state.get("selectedFolderId")
    if selected_folder and selected_folder not in VIRTUAL_FOLDER_IDS and selected_folder not in folder_ids:
        warnings.append({"code": "selected_folder_missing", "message": "Selected folder is missing."})

    titles = [str(prompt.get("title", "")).strip().lower() for prompt in prompts if isinstance(prompt, Mapping)]
    for title, count in Counter(title for title in titles if title).items():
        if count > 1:
            warnings.append({"code": "duplicate_prompt_name", "message": f"Duplicate prompt name: {title}."})

    used_variables = set()
    for prompt in prompts:
        if not isinstance(prompt, Mapping):
            continue
        text = str(prompt.get("text", ""))
        for match in TOKEN_RE.finditer(text):
            name = match.group(1).strip()
            if not is_valid_variable_name(name):
                warnings.append(
                    {
                        "code": "invalid_variable_token",
                        "message": f"Prompt '{prompt.get('title', 'Untitled')}' contains invalid token {match.group(0)}.",
                    }
                )
        for name in variables_used(text):
            used_variables.add(name)
            if name not in variables:
                warnings.append(
                    {
                        "code": "undefined_variable",
                        "message": f"Prompt '{prompt.get('title', 'Untitled')}' references undefined variable '{name}'.",
                    }
                )

    if isinstance(variables, Mapping):
        for name, definition in variables.items():
            if not is_valid_variable_name(str(name)):
                warnings.append({"code": "invalid_variable_name", "message": f"Invalid variable name: {name}."})
            values = definition.get("values", []) if isinstance(definition, Mapping) else []
            fallback = definition.get("fallback", "") if isinstance(definition, Mapping) else ""
            if not values and not fallback:
                warnings.append({"code": "empty_variable_values", "message": f"Variable '{name}' has no values."})
            if name not in used_variables:
                warnings.append({"code": "unused_variable", "message": f"Variable '{name}' is not used by any prompt."})

    return warnings
