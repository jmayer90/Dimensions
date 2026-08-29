import bpy

from .drawing import register_draw_handler, unregister_draw_handler
from .keymaps import classes as keymap_classes
from .keymaps import register_keymaps, unregister_keymaps
from .migrations import register_migrations, unregister_migrations
from .operators import classes as operator_classes
from .properties import classes as property_classes
from .properties import register_properties, unregister_properties
from .preferences import classes as preference_classes
from .preferences import remember_preferences_for_reregister, restore_preferences_after_reregister
from .tools import register_tools, unregister_tools
from .ui import classes as ui_classes


CLASSES = (
    *property_classes,
    *keymap_classes,
    *preference_classes,
    *operator_classes,
    *ui_classes,
)
_registered_classes = []
_registered_components = []


_COMPONENTS = (
    (register_properties, unregister_properties),
    (register_migrations, unregister_migrations),
    (register_tools, unregister_tools),
    (register_keymaps, unregister_keymaps),
    (register_draw_handler, unregister_draw_handler),
)


def register():
    if _registered_classes or _registered_components:
        return
    try:
        for cls in CLASSES:
            bpy.utils.register_class(cls)
            _registered_classes.append(cls)
        for component_register, component_unregister in _COMPONENTS:
            _registered_components.append(component_unregister)
            component_register()
        restore_preferences_after_reregister()
    except Exception:
        _rollback_registration()
        raise


def unregister():
    remember_preferences_for_reregister()
    _rollback_registration()


def _rollback_registration():
    while _registered_components:
        component_unregister = _registered_components.pop()
        try:
            component_unregister()
        except (ReferenceError, RuntimeError):
            pass
    while _registered_classes:
        cls = _registered_classes.pop()
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass


if __name__ == "__main__":
    register()
