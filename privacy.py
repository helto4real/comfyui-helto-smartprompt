"""Shared privacy-envelope helpers for Smart Prompt Manager."""

from __future__ import annotations

import os
from typing import Any, Dict, Mapping, Tuple

import helto_privacy.envelope as _envelope
import helto_privacy.keystore as _keystore
from helto_privacy import PrivacyEnvelopeCodec, PrivacyError  # noqa: F401

try:
    from .schema import normalize_state
except ImportError:  # Allows running tests from the repository root.
    from schema import normalize_state


ENVELOPE_SCHEMA = "helto.smart-prompt-manager"
LEGACY_ENVELOPE_SCHEMA = "comfyui-helto-prompts.smart-prompt-manager"
ENVELOPE_VERSION = _envelope.ENVELOPE_VERSION
ALGORITHM = _envelope.ALGORITHM
CRYPTO_AVAILABLE = _envelope.CRYPTO_AVAILABLE
CRYPTO_IMPORT_ERROR = _envelope.CRYPTO_IMPORT_ERROR

_codec = PrivacyEnvelopeCodec(ENVELOPE_SCHEMA)


def _keystore_required() -> None:
    if not _keystore.keystore_exists():
        raise PrivacyError(
            "PRIVACY_KEYSTORE_UNINITIALIZED: Privacy keystore has not been created yet."
        )


def crypto_status(base_dir: str | os.PathLike[str] | None = None) -> Dict[str, Any]:
    del base_dir
    keystore_status = _keystore.keystore_status()
    return {
        "available": CRYPTO_AVAILABLE,
        "algorithm": ALGORITHM,
        "keyExists": False,
        "keyPath": "",
        "error": "" if CRYPTO_AVAILABLE else f"Python package 'cryptography' is required: {CRYPTO_IMPORT_ERROR}",
        "keystoreAvailable": bool(keystore_status.get("keystoreAvailable")),
        "keystoreInitialized": bool(keystore_status.get("keystoreInitialized")),
        "keystoreLocked": bool(keystore_status.get("keystoreLocked")),
    }


def is_encrypted_payload(value: Any) -> bool:
    return _codec.is_encrypted_payload(value)


def _payload_mapping(value: Any) -> Mapping[str, Any] | None:
    if isinstance(value, Mapping):
        return value
    if isinstance(value, str):
        try:
            import json

            value = json.loads(value)
        except Exception:
            return None
    return value if isinstance(value, Mapping) else None


def is_unsupported_encrypted_payload(value: Any) -> bool:
    payload = _payload_mapping(value)
    return payload is not None and payload.get("encrypted") is True and not is_encrypted_payload(payload)


def unsupported_encrypted_payload_message(value: Any) -> str:
    payload = _payload_mapping(value)
    if payload is not None and payload.get("schema") == LEGACY_ENVELOPE_SCHEMA:
        return "Encrypted Smart Prompt Manager data uses an unsupported legacy privacy schema."
    return "Encrypted Smart Prompt Manager data uses an unsupported encrypted privacy schema or algorithm."


def encrypt_state(state: Mapping[str, Any], base_dir: str | os.PathLike[str] | None = None) -> Dict[str, Any]:
    del base_dir
    normalized, warnings = normalize_state(state)
    if warnings:
        normalized["_normalizationWarnings"] = warnings
    _keystore_required()
    return _codec.encrypt_state(normalized)


def decrypt_state(payload: Any, base_dir: str | os.PathLike[str] | None = None) -> Tuple[Dict[str, Any], list[str]]:
    del base_dir
    if is_unsupported_encrypted_payload(payload):
        raise PrivacyError(unsupported_encrypted_payload_message(payload))
    _keystore_required()
    loaded = _codec.decrypt_state(payload)
    state, warnings = normalize_state(loaded if isinstance(loaded, Mapping) else {})
    state["privacyMode"] = True
    return state, warnings
