import bpy


class CADDIM_WST_AddDimension(bpy.types.WorkSpaceTool):
    bl_idname = "dimensions.add_dimension_tool"
    bl_label = "Add Dimension"
    bl_description = "Create a persistent dimension between two mesh vertices"
    bl_space_type = "VIEW_3D"
    bl_context_mode = "OBJECT"
    bl_icon = "ops.view3d.ruler"
    bl_keymap = (
        (
            "dimensions.create_dimension",
            {"type": "LEFTMOUSE", "value": "PRESS"},
            None,
        ),
    )


_tool_registered = False


def register_tools():
    global _tool_registered
    if _tool_registered:
        return

    bpy.utils.register_tool(
        CADDIM_WST_AddDimension,
        after={"builtin.primitive_cube_add"},
        separator=False,
        group=False,
    )
    _tool_registered = True


def unregister_tools():
    global _tool_registered
    if not _tool_registered:
        return

    bpy.utils.unregister_tool(CADDIM_WST_AddDimension)
    _tool_registered = False
