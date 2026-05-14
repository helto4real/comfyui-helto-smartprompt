"""Prompt variable resolution for Smart Prompt Manager.

This module intentionally has no ComfyUI imports so it can be tested in
isolation and reused by the browser UI implementation.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional


TOKEN_RE = re.compile(r"\{\{([^{}]*)\}\}")
VALID_VARIABLE_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def is_valid_variable_name(name: str) -> bool:
    return bool(VALID_VARIABLE_RE.match(name or ""))


def stable_hash(text: str) -> int:
    """Return a small cross-language FNV-1a hash.

    The JavaScript frontend uses the same algorithm so random previews match the
    Python backend without relying on Python's process-randomized hash().
    """

    value = 2166136261
    for char in text:
        value ^= ord(char)
        value = (value * 16777619) & 0xFFFFFFFF
    return value


def _string_or_empty(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _normalize_values(values: Any) -> List[str]:
    if isinstance(values, str):
        values = values.splitlines()
    if not isinstance(values, Iterable) or isinstance(values, (bytes, bytearray)):
        return []
    normalized: List[str] = []
    for value in values:
        text = _string_or_empty(value).strip()
        if text:
            normalized.append(text)
    return normalized


def _definition_for(variables: Mapping[str, Any], name: str) -> Optional[Mapping[str, Any]]:
    definition = variables.get(name)
    if isinstance(definition, Mapping):
        return definition
    return None


def _candidate_values(definition: Mapping[str, Any]) -> List[str]:
    values = _normalize_values(definition.get("values", []))
    fallback = _string_or_empty(definition.get("fallback")).strip()
    if values:
        return values
    if fallback:
        return [fallback]
    return []


def _select_value(
    name: str,
    definition: Mapping[str, Any],
    seed: int,
    reroll: int,
    cycle_state: Mapping[str, Any],
    warnings: List[str],
) -> str:
    values = _normalize_values(definition.get("values", []))
    fallback = _string_or_empty(definition.get("fallback")).strip()
    candidates = values[:] if values else ([fallback] if fallback else [])
    mode = _string_or_empty(definition.get("mode") or "random").strip().lower()
    if mode not in {"random", "fixed", "cycle"}:
        warnings.append(f"Variable '{name}' has unsupported mode '{mode}', using random.")
        mode = "random"

    if not values:
        warnings.append(f"Variable '{name}' has no values.")

    if mode == "fixed":
        fixed_value = _string_or_empty(definition.get("fixedValue")).strip()
        if fixed_value:
            return fixed_value
        if fallback:
            return fallback
        if values:
            return values[0]
        return ""

    if not candidates:
        return ""

    if mode == "cycle":
        try:
            base_index = int(cycle_state.get(name, 0))
        except (TypeError, ValueError):
            base_index = 0
        return candidates[(base_index + int(reroll or 0)) % len(candidates)]

    index = stable_hash(f"{int(seed or 0)}:{int(reroll or 0)}:{name}") % len(candidates)
    return candidates[index]


def variables_used(raw_prompt: Any) -> List[str]:
    """Return valid variable names used by a prompt in first-seen order."""

    seen = set()
    ordered: List[str] = []
    for match in TOKEN_RE.finditer(_string_or_empty(raw_prompt)):
        name = match.group(1).strip()
        if is_valid_variable_name(name) and name not in seen:
            seen.add(name)
            ordered.append(name)
    return ordered


def resolve_prompt(
    raw_prompt: Any,
    variables: Optional[Mapping[str, Any]] = None,
    seed: int = 0,
    reroll: int = 0,
    cycle_state: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Resolve variables in a prompt without raising on malformed data."""

    text = _string_or_empty(raw_prompt)
    definitions: Mapping[str, Any] = variables if isinstance(variables, Mapping) else {}
    cycle: Mapping[str, Any] = cycle_state if isinstance(cycle_state, Mapping) else {}
    selected_values: MutableMapping[str, str] = {}
    missing: List[str] = []
    used: List[str] = []
    warnings: List[str] = []

    def replace(match: re.Match[str]) -> str:
        token = match.group(0)
        name = match.group(1).strip()
        if not name:
            warnings.append("Encountered an empty variable token.")
            return token
        if not is_valid_variable_name(name):
            warnings.append(f"Variable token '{token}' has an invalid name.")
            return token
        if name not in used:
            used.append(name)

        definition = _definition_for(definitions, name)
        if definition is None:
            if name not in missing:
                missing.append(name)
            warnings.append(f"Variable '{name}' is referenced but not defined.")
            return token

        if name not in selected_values:
            selected_values[name] = _select_value(name, definition, seed, reroll, cycle, warnings)
        if selected_values[name] == "":
            warnings.append(f"Variable '{name}' resolved to an empty value.")
            return token
        return selected_values[name]

    resolved = TOKEN_RE.sub(replace, text)
    return {
        "resolved_prompt": resolved,
        "selected_values": dict(selected_values),
        "missing_variables": missing,
        "variables_used": used,
        "warnings": warnings,
    }


def needed_variable_definitions(raw_prompt: Any, variables: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    definitions: Dict[str, Any] = {}
    source: Mapping[str, Any] = variables if isinstance(variables, Mapping) else {}
    for name in variables_used(raw_prompt):
        definition = _definition_for(source, name)
        if definition is not None:
            definitions[name] = dict(definition)
    return definitions


def candidate_values_for_tooltip(definition: Any) -> List[str]:
    if not isinstance(definition, Mapping):
        return []
    return _candidate_values(definition)
