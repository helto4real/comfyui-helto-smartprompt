from helto_privacy import register_helto_privacy_ui

from .managed_install import (
    install_smart_prompt_privacy,
    register_smart_prompt_managed_routes,
)
from .nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS

WEB_DIRECTORY = "./web/js"

register_helto_privacy_ui()
install_smart_prompt_privacy()
register_smart_prompt_managed_routes()

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
