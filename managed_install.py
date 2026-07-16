"""Atomic installation boundary for Smart Prompt shared privacy."""

from __future__ import annotations

from threading import RLock

from helto_privacy import (
    BoundPrivacyPack,
    ConsumerSuiteDeclaration,
    install,
    register_consumer_suite_declaration,
    register_legacy_reader_units,
    smart_prompt_v1_export_reader_unit,
    smart_prompt_v1_reader_unit,
)
from helto_privacy.runtime import bound_privacy_pack

try:
    from .managed_execution import (
        build_smart_prompt_s3_privacy_profile,
        build_smart_prompt_s3_server_adapters,
    )
    from .managed_import_export import SmartPromptImportExportAdapter
    from .managed_import_export_routes import (
        SMART_PROMPT_MANAGED_IMPORT_ROUTES,
        SmartPromptImportExportRoutes,
    )
    from .managed_privacy import (
        PROMPT_LIBRARY_OPERATION_ADAPTER_ID,
        PROMPT_LIBRARY_WORKFLOW_RESOURCE_ID,
        SMART_PROMPT_PROFILE_ID,
    )
except ImportError:  # Allows focused tests from the repository root.
    from managed_execution import (
        build_smart_prompt_s3_privacy_profile,
        build_smart_prompt_s3_server_adapters,
    )
    from managed_import_export import SmartPromptImportExportAdapter
    from managed_import_export_routes import (
        SMART_PROMPT_MANAGED_IMPORT_ROUTES,
        SmartPromptImportExportRoutes,
    )
    from managed_privacy import (
        PROMPT_LIBRARY_OPERATION_ADAPTER_ID,
        PROMPT_LIBRARY_WORKFLOW_RESOURCE_ID,
        SMART_PROMPT_PROFILE_ID,
    )


_INSTALL_LOCK = RLock()
SMART_PROMPT_SUITE_ID = "helto-suite-2026-07-16.2"
_PACK: BoundPrivacyPack | None = None
_ADAPTERS: dict[str, object] | None = None
_IMPORT_EXPORT: SmartPromptImportExportAdapter | None = None
_ROUTES_REGISTERED = False


def install_smart_prompt_privacy() -> BoundPrivacyPack:
    """Install only the complete S1-S3 profile with every adapter bound."""

    global _ADAPTERS, _IMPORT_EXPORT, _PACK
    with _INSTALL_LOCK:
        if _PACK is not None:
            return _PACK
        register_legacy_reader_units(
            (smart_prompt_v1_reader_unit(), smart_prompt_v1_export_reader_unit())
        )
        profile = build_smart_prompt_s3_privacy_profile()
        import_export = SmartPromptImportExportAdapter()
        adapters = build_smart_prompt_s3_server_adapters(
            import_export=import_export,
        )
        expected = {slot.id for slot in profile.server_adapters}
        if set(adapters) != expected:
            raise RuntimeError("Smart Prompt privacy adapter binding is incomplete.")
        pack = install(profile, adapters)
        register_consumer_suite_declaration(
            ConsumerSuiteDeclaration(profile.distribution, SMART_PROMPT_SUITE_ID)
        )
        import_export.bind(
            workflow=pack.workflow(PROMPT_LIBRARY_WORKFLOW_RESOURCE_ID),
            migration=pack.migration,
            profile=pack.profile,
        )
        if adapters[PROMPT_LIBRARY_OPERATION_ADAPTER_ID] is None:
            raise RuntimeError("Smart Prompt privacy operation adapter is unavailable.")
        _PACK = pack
        _ADAPTERS = adapters
        _IMPORT_EXPORT = import_export
        return pack


def smart_prompt_privacy_pack() -> BoundPrivacyPack:
    return _PACK if _PACK is not None else bound_privacy_pack(SMART_PROMPT_PROFILE_ID)


def smart_prompt_privacy_adapter(adapter_id: str) -> object:
    if _ADAPTERS is None or adapter_id not in _ADAPTERS:
        raise RuntimeError("Smart Prompt privacy adapters are not installed.")
    return _ADAPTERS[adapter_id]


def smart_prompt_import_export_adapter() -> SmartPromptImportExportAdapter:
    if _IMPORT_EXPORT is None:
        raise RuntimeError("Smart Prompt import/export privacy is not installed.")
    return _IMPORT_EXPORT


def register_smart_prompt_managed_routes() -> bool:
    """Bind only the declared managed import routes to the installed pack."""

    global _ROUTES_REGISTERED
    with _INSTALL_LOCK:
        if _ROUTES_REGISTERED:
            return True
        try:
            from aiohttp import web
            from server import PromptServer
        except ImportError:
            return False
        pack = smart_prompt_privacy_pack()
        dispatcher = SmartPromptImportExportRoutes(
            pack,
            smart_prompt_import_export_adapter(),
        )
        routes = PromptServer.instance.routes

        for path, operation_id in SMART_PROMPT_MANAGED_IMPORT_ROUTES.items():
            async def handler(request, *, _operation_id=operation_id):
                try:
                    payload = await dispatcher.dispatch(request, _operation_id)
                except Exception:  # Product data and internals never reach the response.
                    return web.json_response(
                        {
                            "ok": False,
                            "error": "PRIVACY_SMART_PROMPT_OPERATION_FAILED",
                        },
                        status=400,
                    )
                return web.json_response({"ok": True, **payload})

            routes.post(path)(handler)
        _ROUTES_REGISTERED = True
        return True
