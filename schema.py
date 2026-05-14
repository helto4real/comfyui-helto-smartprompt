"""State schema helpers for Smart Prompt Manager."""

from __future__ import annotations

import copy
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Tuple

try:
    from .resolver import is_valid_variable_name
except ImportError:  # Allows running tests from the repository root.
    from resolver import is_valid_variable_name


SCHEMA_VERSION = 1
VIRTUAL_FOLDER_IDS = {"all", "unsorted", "favorites"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def make_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def default_state() -> Dict[str, Any]:
    now = utc_now()
    folder_id = make_id("folder")
    prompt_id = make_id("prompt")
    return {
        "version": SCHEMA_VERSION,
        "selectedFolderId": "all",
        "selectedPromptId": prompt_id,
        "search": "",
        "privacyMode": False,
        "folders": [{"id": folder_id, "name": "Portraits", "hidden": False}],
        "prompts": [
            {
                "id": prompt_id,
                "title": "Cinematic portrait",
                "text": "A {{mood}} cinematic portrait of {{character}} in {{lighting}}.",
                "description": "Starter prompt showing Smart Prompt Manager variables.",
                "folderId": folder_id,
                "tags": ["portrait", "cinematic"],
                "favorite": False,
                "locked": False,
                "hidden": False,
                "createdAt": now,
                "updatedAt": now,
            }
        ],
        "variables": {
            "mood": {
                "mode": "random",
                "values": ["dreamy", "melancholic", "dramatic"],
                "fixedValue": None,
                "fallback": "dreamy",
                "description": "Overall emotional tone.",
            },
            "character": {
                "mode": "random",
                "values": ["cyberpunk detective", "medieval knight", "astronaut"],
                "fixedValue": None,
                "fallback": "astronaut",
                "description": "Main subject.",
            },
            "lighting": {
                "mode": "random",
                "values": ["golden hour", "neon rim light", "soft studio light"],
                "fixedValue": None,
                "fallback": "soft studio light",
                "description": "Lighting setup.",
            },
        },
        "cycleState": {},
        "ui": {"collapsedSections": {}},
    }


def state_to_json(state: Mapping[str, Any]) -> str:
    return json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True)


def parse_state(value: Any) -> Tuple[Dict[str, Any], List[str]]:
    warnings: List[str] = []
    if isinstance(value, Mapping):
        data = dict(value)
    elif isinstance(value, str) and value.strip():
        try:
            loaded = json.loads(value)
            data = loaded if isinstance(loaded, Mapping) else {}
            if not isinstance(loaded, Mapping):
                warnings.append("Prompt manager JSON must be an object; using defaults.")
        except Exception as exc:  # noqa: BLE001 - bad user JSON should not crash ComfyUI.
            data = {}
            warnings.append(f"Could not parse prompt manager JSON: {exc}")
    else:
        data = {}
    state, normalization_warnings = normalize_state(data)
    warnings.extend(normalization_warnings)
    return state, warnings


def _as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _as_bool(value: Any) -> bool:
    return bool(value)


def _as_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _normalize_tags(value: Any) -> List[str]:
    if isinstance(value, str):
        parts = re.split(r"[,#\n]", value)
    elif isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray, Mapping)):
        parts = value
    else:
        parts = []
    tags: List[str] = []
    seen = set()
    for part in parts:
        tag = _as_text(part).strip()
        if tag and tag.lower() not in seen:
            seen.add(tag.lower())
            tags.append(tag)
    return tags


def _normalize_values(value: Any) -> List[str]:
    if isinstance(value, str):
        parts = value.splitlines()
    elif isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray, Mapping)):
        parts = value
    else:
        parts = []
    return [_as_text(part).strip() for part in parts if _as_text(part).strip()]


def _unique_id(candidate: Any, prefix: str, used: set[str]) -> str:
    text = _as_text(candidate).strip()
    if not text or text in used or text in VIRTUAL_FOLDER_IDS:
        text = make_id(prefix)
    used.add(text)
    return text


def normalize_state(data: Mapping[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    base = default_state()
    if not data:
        return base, []

    warnings: List[str] = []
    version = data.get("version", SCHEMA_VERSION)
    if version != SCHEMA_VERSION:
        warnings.append(f"Unsupported schema version '{version}', attempting version 1 normalization.")

    used_folder_ids: set[str] = set()
    folders: List[Dict[str, Any]] = []
    for item in _as_list(data.get("folders")):
        if not isinstance(item, Mapping):
            warnings.append("Ignored malformed folder entry.")
            continue
        folder_id = _unique_id(item.get("id"), "folder", used_folder_ids)
        raw_name = _as_text(item.get("name"), "Folder")
        name = raw_name if raw_name.strip() else "Folder"
        folders.append({"id": folder_id, "name": name, "hidden": _as_bool(item.get("hidden"))})

    folder_ids = {folder["id"] for folder in folders}
    used_prompt_ids: set[str] = set()
    prompts: List[Dict[str, Any]] = []
    for item in _as_list(data.get("prompts")):
        if not isinstance(item, Mapping):
            warnings.append("Ignored malformed prompt entry.")
            continue
        prompt_id = _unique_id(item.get("id"), "prompt", used_prompt_ids)
        folder_id = _as_text(item.get("folderId")).strip()
        if folder_id not in folder_ids:
            folder_id = ""
        created = _as_text(item.get("createdAt"), utc_now())
        updated = _as_text(item.get("updatedAt"), created)
        prompts.append(
            {
                "id": prompt_id,
                "title": _as_text(item.get("title"), "Untitled prompt")
                if _as_text(item.get("title"), "Untitled prompt").strip()
                else "Untitled prompt",
                "text": _as_text(item.get("text")),
                "description": _as_text(item.get("description")),
                "folderId": folder_id,
                "tags": _normalize_tags(item.get("tags")),
                "favorite": _as_bool(item.get("favorite")),
                "locked": _as_bool(item.get("locked")),
                "hidden": _as_bool(item.get("hidden")),
                "createdAt": created,
                "updatedAt": updated,
            }
        )

    variables: Dict[str, Dict[str, Any]] = {}
    raw_variables = data.get("variables", {})
    if not isinstance(raw_variables, Mapping):
        warnings.append("Variables must be an object; using no variables.")
        raw_variables = {}
    for raw_name, raw_definition in raw_variables.items():
        name = _as_text(raw_name).strip()
        if not is_valid_variable_name(name):
            warnings.append(f"Ignored invalid variable name '{name}'.")
            continue
        definition = raw_definition if isinstance(raw_definition, Mapping) else {}
        mode = _as_text(definition.get("mode"), "random").lower()
        if mode not in {"random", "fixed", "cycle"}:
            warnings.append(f"Variable '{name}' had invalid mode '{mode}', using random.")
            mode = "random"
        fixed_value = definition.get("fixedValue")
        variables[name] = {
            "mode": mode,
            "values": _normalize_values(definition.get("values")),
            "fixedValue": None if fixed_value is None else _as_text(fixed_value),
            "fallback": _as_text(definition.get("fallback")),
            "description": _as_text(definition.get("description")),
        }

    cycle_state: Dict[str, int] = {}
    raw_cycle = data.get("cycleState", {})
    if isinstance(raw_cycle, Mapping):
        for name, value in raw_cycle.items():
            try:
                cycle_state[_as_text(name)] = int(value)
            except (TypeError, ValueError):
                warnings.append(f"Ignored invalid cycle state for '{name}'.")

    selected_folder = _as_text(data.get("selectedFolderId"), "all") or "all"
    if selected_folder not in VIRTUAL_FOLDER_IDS and selected_folder not in folder_ids:
        warnings.append("Selected folder was missing; using All.")
        selected_folder = "all"

    prompt_ids = {prompt["id"] for prompt in prompts}
    selected_prompt = _as_text(data.get("selectedPromptId"))
    if selected_prompt not in prompt_ids:
        selected_prompt = prompts[0]["id"] if prompts else ""
        if data.get("selectedPromptId"):
            warnings.append("Selected prompt was missing.")

    ui = data.get("ui") if isinstance(data.get("ui"), Mapping) else {}
    collapsed = ui.get("collapsedSections") if isinstance(ui.get("collapsedSections"), Mapping) else {}

    state = {
        "version": SCHEMA_VERSION,
        "selectedFolderId": selected_folder,
        "selectedPromptId": selected_prompt,
        "search": _as_text(data.get("search")),
        "privacyMode": _as_bool(data.get("privacyMode")),
        "folders": folders,
        "prompts": prompts,
        "variables": variables,
        "cycleState": cycle_state,
        "ui": {"collapsedSections": dict(collapsed)},
    }
    return state, warnings


def selected_prompt(state: Mapping[str, Any]) -> Dict[str, Any]:
    prompt_id = _as_text(state.get("selectedPromptId"))
    for prompt in _as_list(state.get("prompts")):
        if isinstance(prompt, Mapping) and prompt.get("id") == prompt_id:
            return dict(prompt)
    prompts = [prompt for prompt in _as_list(state.get("prompts")) if isinstance(prompt, Mapping)]
    return dict(prompts[0]) if prompts else {}


def suffix_name(name: str, existing: Iterable[str], suffix: str = "copy") -> str:
    existing_lower = {_as_text(value).lower() for value in existing}
    base = name.strip() or "Untitled prompt"
    first = f"{base} {suffix}"
    if first.lower() not in existing_lower:
        return first
    index = 2
    while f"{first} {index}".lower() in existing_lower:
        index += 1
    return f"{first} {index}"


def merge_library(current: Mapping[str, Any], incoming: Mapping[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """Merge an imported library into current state, avoiding IDs/name collisions."""

    base, base_warnings = normalize_state(current)
    imported, imported_warnings = normalize_state(incoming)
    warnings = base_warnings + imported_warnings
    result = copy.deepcopy(base)

    folder_id_map: Dict[str, str] = {}
    existing_folder_names = {folder["name"].lower() for folder in result["folders"]}
    existing_folder_ids = {folder["id"] for folder in result["folders"]}
    for folder in imported["folders"]:
        new_folder = copy.deepcopy(folder)
        old_id = new_folder["id"]
        if new_folder["id"] in existing_folder_ids or new_folder["id"] in VIRTUAL_FOLDER_IDS:
            new_folder["id"] = make_id("folder")
        if new_folder["name"].lower() in existing_folder_names:
            new_folder["name"] = suffix_name(new_folder["name"], [f["name"] for f in result["folders"]])
        folder_id_map[old_id] = new_folder["id"]
        existing_folder_ids.add(new_folder["id"])
        existing_folder_names.add(new_folder["name"].lower())
        result["folders"].append(new_folder)

    existing_prompt_names = [prompt["title"] for prompt in result["prompts"]]
    existing_prompt_ids = {prompt["id"] for prompt in result["prompts"]}
    for prompt in imported["prompts"]:
        new_prompt = copy.deepcopy(prompt)
        if new_prompt["id"] in existing_prompt_ids:
            new_prompt["id"] = make_id("prompt")
        if new_prompt["title"].lower() in {name.lower() for name in existing_prompt_names}:
            new_prompt["title"] = suffix_name(new_prompt["title"], existing_prompt_names)
        new_prompt["folderId"] = folder_id_map.get(new_prompt.get("folderId", ""), "")
        existing_prompt_ids.add(new_prompt["id"])
        existing_prompt_names.append(new_prompt["title"])
        result["prompts"].append(new_prompt)

    for name, definition in imported["variables"].items():
        if name not in result["variables"]:
            result["variables"][name] = copy.deepcopy(definition)
        elif result["variables"][name] != definition:
            warnings.append(f"Variable '{name}' already exists and was not overwritten.")

    if result["prompts"] and not result.get("selectedPromptId"):
        result["selectedPromptId"] = result["prompts"][0]["id"]
    return result, warnings
