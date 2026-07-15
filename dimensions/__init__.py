import bpy

from .drawing import register_draw_handler, unregister_draw_handler
from .operators.click_select import register_click_select, unregister_click_select
from .operators import classes as operator_classes
from .properties import classes as property_classes
from .properties import register_properties, unregister_properties
from .tools import register_tools, unregister_tools
from .ui import classes as ui_classes


CLASSES = (
    *property_classes,
    *operator_classes,
    *ui_classes,
)
_registered_classes = []
_registered_components = []


_COMPONENTS = (
    (register_properties, unregister_properties),
    (register_tools, unregister_tools),
    (register_draw_handler, unregister_draw_handler),
    (register_click_select, unregister_click_select),
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
    except Exception:
        _rollback_registration()
        raise


def unregister():
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
