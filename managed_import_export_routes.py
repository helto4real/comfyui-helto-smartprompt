"""Strict S2 route handlers bound by the atomic managed installer."""

from __future__ import annotations

from collections.abc import Mapping

from helto_privacy.guard import authorize_privacy_request

try:
    from .managed_import_export import (
        IMPORT_MERGE_OPERATION_ID,
        IMPORT_MERGE_ROUTE,
        IMPORT_REPLACE_OPERATION_ID,
        IMPORT_REPLACE_ROUTE,
        SmartPromptImportExportAuthorizations,
        SmartPromptImportExportError,
    )
except ImportError:
    from managed_import_export import (
        IMPORT_MERGE_OPERATION_ID,
        IMPORT_MERGE_ROUTE,
        IMPORT_REPLACE_OPERATION_ID,
        IMPORT_REPLACE_ROUTE,
        SmartPromptImportExportAuthorizations,
        SmartPromptImportExportError,
    )


SMART_PROMPT_MANAGED_IMPORT_ROUTES = {
    IMPORT_REPLACE_ROUTE: IMPORT_REPLACE_OPERATION_ID,
    IMPORT_MERGE_ROUTE: IMPORT_MERGE_OPERATION_ID,
}


class SmartPromptImportExportRoutes:
    """Parse one exact phase and issue only operation-bound authority."""

    def __init__(self, pack, adapter) -> None:
        self._pack = pack
        self._adapter = adapter

    async def dispatch(self, request: object, operation_id: str) -> dict[str, object]:
        if operation_id not in {IMPORT_REPLACE_OPERATION_ID, IMPORT_MERGE_OPERATION_ID}:
            raise SmartPromptImportExportError("Smart Prompt import operation is invalid.")
        payload = await _request_payload(request)
        phase = payload.get("phase")
        operation = authorize_privacy_request(
            request,
            operation_id,
            pack_id=self._pack.profile.id,
        )

        if phase == "prepare":
            _strict(payload, {
                "phase", "owner_id", "idempotency_key", "raw",
                "explicit_reexport", "destination_snapshot", "destination_private",
            })
            _strings(payload, {
                "owner_id", "idempotency_key", "raw", "destination_snapshot",
            })
            _booleans(payload, {"explicit_reexport", "destination_private"})
            authorizations = self._snapshot_authorizations(request, operation)
            result = self._adapter.prepare(
                payload["owner_id"],
                payload["idempotency_key"],
                payload["raw"],
                payload["explicit_reexport"],
                payload["destination_snapshot"],
                payload["destination_private"],
                operation_id=operation_id,
                authorizations=authorizations,
            )
            return {
                "state": result.state,
                "protectedValue": result.protected_value,
                "warnings": list(result.warnings),
                "transactionId": result.transaction_id,
                "resumeToken": result.resume_token,
                "bindingId": result.binding_id,
                "disposition": result.disposition,
                "exportedAt": result.exported_at,
            }

        common = {
            "phase", "owner_id", "transaction_id", "resume_token", "binding_id",
        }
        if phase == "reexport":
            _strict(payload, common | {"committed_snapshot", "destination_private"})
            _strings(payload, common - {"phase"} | {"committed_snapshot"})
            _booleans(payload, {"destination_private"})
            result = self._adapter.reexport(
                payload["owner_id"], payload["transaction_id"], payload["resume_token"],
                payload["binding_id"], payload["committed_snapshot"],
                payload["destination_private"], operation_id=operation_id,
                authorizations=self._snapshot_authorizations(request, operation),
            )
            return {"filename": result.filename, "text": result.text, "digest": result.digest}
        if phase == "finalize":
            _strict(payload, common | {
                "committed_snapshot", "destination_private", "reexport_digest",
            })
            _strings(
                payload,
                common - {"phase"} | {"committed_snapshot", "reexport_digest"},
            )
            _booleans(payload, {"destination_private"})
            if len(payload["reexport_digest"]) != 64 or any(
                character not in "0123456789abcdef"
                for character in payload["reexport_digest"]
            ):
                raise SmartPromptImportExportError("Smart Prompt route payload is invalid.")
            receipt = self._adapter.finalize(
                payload["owner_id"], payload["transaction_id"], payload["resume_token"],
                payload["binding_id"], payload["committed_snapshot"],
                payload["reexport_digest"], payload["destination_private"],
                operation_id=operation_id,
                authorizations=self._snapshot_authorizations(request, operation),
            )
            return receipt.to_payload()
        if phase in {"status", "resume", "cancel"}:
            _strict(payload, common)
            _strings(payload, common - {"phase"})
            method = getattr(self._adapter, phase)
            result = method(
                payload["owner_id"], payload["transaction_id"], payload["resume_token"],
                payload["binding_id"], operation_id=operation_id, authorization=operation,
            )
            if phase == "resume":
                return {
                    **result.status.to_payload(),
                    "originalSnapshot": result.original_exact.decode("utf-8"),
                }
            if phase == "cancel":
                status, original = result
                return {**status.to_payload(), "originalSnapshot": original}
            return result.to_payload()
        if phase == "rollback-ack":
            _strict(payload, common | {"restored_snapshot"})
            _strings(payload, common - {"phase"} | {"restored_snapshot"})
            status = self._adapter.confirm_rollback(
                payload["owner_id"], payload["transaction_id"], payload["resume_token"],
                payload["binding_id"], payload["restored_snapshot"],
                operation_id=operation_id, authorization=operation,
            )
            return status.to_payload()
        raise SmartPromptImportExportError("Smart Prompt import phase is invalid.")

    def _snapshot_authorizations(self, request, operation):
        return SmartPromptImportExportAuthorizations(
            operation,
            authorize_privacy_request(
                request, "snapshot.reveal", pack_id=self._pack.profile.id
            ),
        )


async def _request_payload(request: object) -> dict[str, object]:
    reader = getattr(request, "json", None)
    if not callable(reader):
        raise SmartPromptImportExportError("Smart Prompt route request is invalid.")
    try:
        value = await reader()
    except Exception:
        raise SmartPromptImportExportError("Smart Prompt route request is invalid.") from None
    if not isinstance(value, dict):
        raise SmartPromptImportExportError("Smart Prompt route request is invalid.")
    return value


def _strict(value: Mapping[str, object], fields: set[str]) -> None:
    if set(value) != fields:
        raise SmartPromptImportExportError("Smart Prompt route payload is invalid.")


def _strings(value: Mapping[str, object], fields: set[str]) -> None:
    if any(not isinstance(value.get(name), str) or not value[name] for name in fields):
        raise SmartPromptImportExportError("Smart Prompt route payload is invalid.")


def _booleans(value: Mapping[str, object], fields: set[str]) -> None:
    if any(not isinstance(value.get(name), bool) for name in fields):
        raise SmartPromptImportExportError("Smart Prompt route payload is invalid.")
