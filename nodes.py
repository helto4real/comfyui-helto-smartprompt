"""ComfyUI backend node for Smart Prompt Manager."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

try:
    from .resolver import needed_variable_definitions, resolve_prompt
    from .schema import default_state, parse_state, selected_prompt, state_to_json
    from .privacy import (
        PrivacyError,
        crypto_status,
        decrypt_state,
        encrypt_state,
        is_encrypted_payload,
        is_unsupported_encrypted_payload,
    )
    from .validation import validate_state
except ImportError:  # Allows running tests from the repository root.
    from resolver import needed_variable_definitions, resolve_prompt
    from schema import default_state, parse_state, selected_prompt, state_to_json
    from privacy import (
        PrivacyError,
        crypto_status,
        decrypt_state,
        encrypt_state,
        is_encrypted_payload,
        is_unsupported_encrypted_payload,
    )
    from validation import validate_state


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


CACHE_TOKEN_PREFIX = "spm-cache-v1:"


def _empty_state() -> dict[str, Any]:
    state = default_state()
    state["prompts"] = []
    state["folders"] = []
    state["variables"] = {}
    state["selectedPromptId"] = ""
    state["selectedFolderId"] = "all"
    return state


def is_cache_token(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(CACHE_TOKEN_PREFIX)


def _as_mapping(value: Any) -> Mapping[str, Any] | None:
    if isinstance(value, Mapping):
        return value
    if isinstance(value, str) and value.strip():
        try:
            loaded = json.loads(value)
        except Exception:
            return None
        if isinstance(loaded, Mapping):
            return loaded
    return None


def _looks_like_spm_payload(value: Any) -> bool:
    if is_cache_token(value) or is_encrypted_payload(value) or is_unsupported_encrypted_payload(value):
        return is_encrypted_payload(value) or is_unsupported_encrypted_payload(value)
    payload = _as_mapping(value)
    if payload is None:
        return False
    return any(key in payload for key in ("prompts", "variables", "selectedPromptId", "folders", "privacyMode"))


def _workflow_from_extra(extra_pnginfo: Any) -> Mapping[str, Any] | None:
    if not isinstance(extra_pnginfo, Mapping):
        return None
    workflow = extra_pnginfo.get("workflow")
    if isinstance(workflow, Mapping):
        return workflow
    if isinstance(workflow, str) and workflow.strip():
        try:
            loaded = json.loads(workflow)
        except Exception:
            return None
        if isinstance(loaded, Mapping):
            return loaded
    return None


def _workflow_widget_values(node: Mapping[str, Any]) -> list[Any]:
    widgets = node.get("widgets_values", [])
    if isinstance(widgets, Mapping):
        values: list[Any] = []
        for key in ("spm_data", "0"):
            if key in widgets:
                values.append(widgets[key])
        values.extend(widgets.values())
        return values
    if isinstance(widgets, Sequence) and not isinstance(widgets, (str, bytes, bytearray)):
        return list(widgets)
    return []


def _spm_data_from_workflow(unique_id: Any, extra_pnginfo: Any) -> tuple[Any | None, list[str]]:
    if unique_id is None or str(unique_id) == "":
        return None, ["Smart Prompt Manager cache token could not be resolved because ComfyUI did not provide the node id."]

    workflow = _workflow_from_extra(extra_pnginfo)
    if workflow is None:
        return None, ["Smart Prompt Manager cache token could not be resolved because workflow metadata is missing."]

    nodes = workflow.get("nodes", [])
    if not isinstance(nodes, Sequence) or isinstance(nodes, (str, bytes, bytearray)):
        return None, ["Smart Prompt Manager cache token could not be resolved because workflow metadata has no node list."]

    matching_node: Mapping[str, Any] | None = None
    for node in nodes:
        if isinstance(node, Mapping) and str(node.get("id")) == str(unique_id):
            matching_node = node
            break

    if matching_node is None:
        return None, [f"Smart Prompt Manager cache token could not find workflow node '{unique_id}'."]

    for candidate in _workflow_widget_values(matching_node):
        if _looks_like_spm_payload(candidate):
            return candidate, []

    return None, [f"Smart Prompt Manager cache token could not find saved prompt data for workflow node '{unique_id}'."]


def parse_spm_data(value: Any, unique_id: Any = None, extra_pnginfo: Any = None):
    if is_cache_token(value):
        resolved_value, warnings = _spm_data_from_workflow(unique_id, extra_pnginfo)
        if resolved_value is None:
            return _empty_state(), warnings
        state, parse_warnings = parse_spm_data(resolved_value)
        return state, warnings + parse_warnings

    if is_encrypted_payload(value):
        try:
            return decrypt_state(value)
        except PrivacyError as exc:
            state = _empty_state()
            state["privacyMode"] = True
            return state, [str(exc)]
    if is_unsupported_encrypted_payload(value):
        state = _empty_state()
        state["privacyMode"] = True
        return state, ["Encrypted Smart Prompt Manager data uses an unsupported legacy privacy schema."]
    return parse_state(value)


try:
    from aiohttp import web
    from helto_privacy import aiohttp_check_privacy_token
    from server import PromptServer

    routes = PromptServer.instance.routes

    @routes.get("/helto_spm/privacy/status")
    async def helto_spm_privacy_status(_request):
        return web.json_response({"ok": True, "status": crypto_status()})

    @routes.post("/helto_spm/privacy/encrypt")
    async def helto_spm_privacy_encrypt(request):
        denied = aiohttp_check_privacy_token(request)
        if denied is not None:
            return denied
        try:
            payload = await request.json()
            envelope = encrypt_state(payload.get("state", {}))
            return web.json_response({"ok": True, "envelope": envelope, "status": crypto_status()})
        except Exception as exc:  # noqa: BLE001 - API should return a readable UI error.
            return web.json_response({"ok": False, "error": str(exc), "status": crypto_status()}, status=400)

    @routes.post("/helto_spm/privacy/decrypt")
    async def helto_spm_privacy_decrypt(request):
        denied = aiohttp_check_privacy_token(request)
        if denied is not None:
            return denied
        try:
            payload = await request.json()
            state, warnings = decrypt_state(payload.get("payload", {}))
            return web.json_response({"ok": True, "state": state, "warnings": warnings, "status": crypto_status()})
        except Exception as exc:  # noqa: BLE001 - API should return a readable UI error.
            return web.json_response({"ok": False, "error": str(exc), "status": crypto_status()}, status=400)

except Exception:
    pass


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
            "hidden": {"unique_id": "UNIQUE_ID", "extra_pnginfo": "EXTRA_PNGINFO"},
        }

    @classmethod
    def IS_CHANGED(cls, spm_data: str, seed: int = 0, reroll: int = 0, unique_id=None, extra_pnginfo=None):
        payload = f"{spm_data}\n{seed}\n{reroll}".encode("utf-8", errors="replace")
        return hashlib.sha256(payload).hexdigest()

    def resolve(self, spm_data: str, seed: int = 0, reroll: int = 0, unique_id=None, extra_pnginfo=None):
        state, parse_warnings = parse_spm_data(spm_data, unique_id=unique_id, extra_pnginfo=extra_pnginfo)
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
