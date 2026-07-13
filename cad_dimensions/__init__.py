import bpy

from .operators import classes as operator_classes
from .properties import classes as property_classes
from .properties import register_properties, unregister_properties
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


def unregister():
    unregister_properties()

    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
