import bpy

from .anchors import get_anchor_status
from .constants import SIDEBAR_CATEGORY
from .properties import get_anchor_vertex_count, is_dimension_object


class CADDIM_PT_MainPanel(bpy.types.Panel):
    bl_label = "Dimensions"
    bl_idname = "CADDIM_PT_main_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = SIDEBAR_CATEGORY

    def draw(self, context):
        layout = self.layout
        scene_settings = context.scene.dimensions_settings

        layout.operator("dimensions.create_dimension", icon="DRIVER_DISTANCE")

        display_box = layout.box()
        display_box.label(text="Display")
        display_box.prop(scene_settings, "unit_style")
        if scene_settings.unit_style in {"FEET_INCHES", "INCH_FRACTION"}:
            display_box.prop(scene_settings, "imperial_denominator")
        display_box.prop(scene_settings, "show_selected_object_overlay")
        if scene_settings.show_selected_object_overlay:
            display_box.prop(scene_settings, "show_overlay_object_name")
        display_box.prop(scene_settings, "enable_click_select")

        active_object = context.view_layer.objects.active
        if not is_dimension_object(active_object):
            layout.separator()
            layout.label(text="Select a dimension to inspect it.")
            return

        props = active_object.dimension_props

        layout.separator()
        layout.prop(active_object, "name", text="Name")
        layout.prop(props, "dimension_type")
        layout.prop(props, "offset_distance")
        layout.prop(props, "precision")
        layout.prop(props, "visible")
        layout.prop(props, "locked")
        layout.prop(props, "color")
        layout.prop(props, "selected_color")

        start_box = layout.box()
        start_box.label(text="Start Anchor")
        start_box.prop(props.start, "target_object", text="Object")
        start_row = start_box.row(align=True)
        start_row.prop(props.start, "vertex_index")
        start_pick = start_row.operator("dimensions.reattach_anchor", text="", icon="EYEDROPPER")
        start_pick.anchor_name = "START"
        start_box.label(text=_vertex_range_text(props.start))
        start_box.label(text=f"Status: {get_anchor_status(props.start)}")

        end_box = layout.box()
        end_box.label(text="End Anchor")
        end_box.prop(props.end, "target_object", text="Object")
        end_row = end_box.row(align=True)
        end_row.prop(props.end, "vertex_index")
        end_pick = end_row.operator("dimensions.reattach_anchor", text="", icon="EYEDROPPER")
        end_pick.anchor_name = "END"
        end_box.label(text=_vertex_range_text(props.end))
        end_box.label(text=f"Status: {get_anchor_status(props.end)}")


def _vertex_range_text(anchor):
    vertex_count = get_anchor_vertex_count(anchor)
    if vertex_count <= 0:
        return "Valid Vertices: none"

    return f"Valid Vertices: 0-{vertex_count - 1}"


classes = (
    CADDIM_PT_MainPanel,
)
