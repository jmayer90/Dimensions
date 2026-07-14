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


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)

    register_properties()
    register_tools()
    register_draw_handler()
    register_click_select()


def unregister():
    unregister_click_select()
    unregister_draw_handler()
    unregister_tools()
    unregister_properties()

    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
