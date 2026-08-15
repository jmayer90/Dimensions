import bpy


class DIMENSIONS_WT_AnnotationSelection(bpy.types.WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "OBJECT"
    bl_idname = "dimensions.annotation_selection"
    bl_label = "Dimensions Selection"
    bl_description = "Select Dimensions annotations and construction guides"
    bl_icon = "ops.generic.select"
    bl_widget = None
    bl_keymap = (
        (
            "dimensions.click_select",
            {"type": "LEFTMOUSE", "value": "PRESS"},
            None,
        ),
    )


def register_tools():
    bpy.utils.register_tool(
        DIMENSIONS_WT_AnnotationSelection,
        after={"builtin.select_box"},
        separator=True,
    )


def unregister_tools():
    bpy.utils.unregister_tool(DIMENSIONS_WT_AnnotationSelection)
