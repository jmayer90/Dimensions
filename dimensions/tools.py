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


class CADDIM_WST_Measure(bpy.types.WorkSpaceTool):
    bl_idname = "dimensions.measure_tool"
    bl_label = "Measure"
    bl_description = "Make a transient measurement; A for aligned or X/Y/Z for an axis projection"
    bl_space_type = "VIEW_3D"
    bl_context_mode = "OBJECT"
    bl_icon = "ops.view3d.ruler"
    bl_keymap = (("dimensions.measure", {"type": "LEFTMOUSE", "value": "PRESS"}, None),)


class CADDIM_WST_AddGuide(bpy.types.WorkSpaceTool):
    bl_idname = "dimensions.add_guide_tool"
    bl_label = "Add Construction Guide"
    bl_description = "Create a persistent construction guide; A for aligned or X/Y/Z for a global axis"
    bl_space_type = "VIEW_3D"
    bl_context_mode = "OBJECT"
    bl_icon = "ops.view3d.ruler"
    bl_keymap = (("dimensions.create_guide", {"type": "LEFTMOUSE", "value": "PRESS"}, None),)


class CADDIM_WST_DrawMeshLine(bpy.types.WorkSpaceTool):
    bl_idname = "dimensions.draw_mesh_line_tool"
    bl_label = "Draw Mesh Line"
    bl_description = "Create chained mesh edges in Edit Mode with Dimensions snapping"
    bl_space_type = "VIEW_3D"
    bl_context_mode = "EDIT_MESH"
    bl_icon = "ops.view3d.ruler"
    bl_keymap = (("dimensions.create_line", {"type": "LEFTMOUSE", "value": "PRESS"}, None),)


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
    bpy.utils.register_tool(
        CADDIM_WST_Measure,
        after={CADDIM_WST_AddDimension.bl_idname},
        separator=False,
        group=False,
    )
    bpy.utils.register_tool(
        CADDIM_WST_AddGuide,
        after={CADDIM_WST_Measure.bl_idname},
        separator=False,
        group=False,
    )
    bpy.utils.register_tool(
        CADDIM_WST_DrawMeshLine,
        after={"builtin.select_box"},
        separator=True,
        group=False,
    )
    _tool_registered = True


def unregister_tools():
    global _tool_registered
    if not _tool_registered:
        return

    bpy.utils.unregister_tool(CADDIM_WST_DrawMeshLine)
    bpy.utils.unregister_tool(CADDIM_WST_AddGuide)
    bpy.utils.unregister_tool(CADDIM_WST_Measure)
    bpy.utils.unregister_tool(CADDIM_WST_AddDimension)
    _tool_registered = False
