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
    return {
        "available": CRYPTO_AVAILABLE,
        "algorithm": ALGORITHM,
        "keyExists": False,
        "keyPath": "",
        "error": "" if CRYPTO_AVAILABLE else f"Python package 'cryptography' is required: {CRYPTO_IMPORT_ERROR}",
        **_keystore.keystore_status(),
    }


def is_encrypted_payload(value: Any) -> bool:
    return _codec.is_encrypted_payload(value)


def is_unsupported_encrypted_payload(value: Any) -> bool:
    if isinstance(value, str):
        try:
            import json

            value = json.loads(value)
        except Exception:
            return False
    return (
        isinstance(value, Mapping)
        and value.get("encrypted") is True
        and value.get("schema") == LEGACY_ENVELOPE_SCHEMA
        and value.get("algorithm") == ALGORITHM
    )


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
        raise PrivacyError(
            "Encrypted Smart Prompt Manager data uses an unsupported legacy privacy schema."
        )
    _keystore_required()
    loaded = _codec.decrypt_state(payload)
    state, warnings = normalize_state(loaded if isinstance(loaded, Mapping) else {})
    state["privacyMode"] = True
    return state, warnings
