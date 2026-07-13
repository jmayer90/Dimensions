import bpy

from .constants import SIDEBAR_CATEGORY
from .properties import is_dimension_object


class CADDIM_PT_MainPanel(bpy.types.Panel):
    bl_label = "CAD Dimensions"
    bl_idname = "CADDIM_PT_main_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = SIDEBAR_CATEGORY

    def draw(self, context):
        layout = self.layout

        layout.operator("caddim.add_test_dimension", icon="EMPTY_AXIS")

        active_object = context.view_layer.objects.active
        if not is_dimension_object(active_object):
            layout.separator()
            layout.label(text="Select a CAD dimension Empty to inspect it.")
            return

        props = active_object.cad_dimension

        layout.separator()
        layout.prop(active_object, "name", text="Name")
        layout.prop(props, "dimension_type")
        layout.prop(props, "offset_pixels")
        layout.prop(props, "precision")
        layout.prop(props, "visible")
        layout.prop(props, "locked")
        layout.prop(props, "color")
        layout.prop(props, "selected_color")

        start_box = layout.box()
        start_box.label(text="Start Anchor")
        start_box.prop(props.start, "target_object", text="Object")
        start_box.prop(props.start, "vertex_index")
        start_status_row = start_box.row()
        start_status_row.enabled = False
        start_status_row.prop(props.start, "status", text="Status")

        end_box = layout.box()
        end_box.label(text="End Anchor")
        end_box.prop(props.end, "target_object", text="Object")
        end_box.prop(props.end, "vertex_index")
        end_status_row = end_box.row()
        end_status_row.enabled = False
        end_status_row.prop(props.end, "status", text="Status")


classes = (
    CADDIM_PT_MainPanel,
)
