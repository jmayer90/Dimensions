import bpy

from .constants import SIDEBAR_CATEGORY
from .properties import is_dimension_object
from .units import get_configured_unit_style


class CADDIM_PT_PanelBase:
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = SIDEBAR_CATEGORY


class CADDIM_PT_MainPanel(CADDIM_PT_PanelBase, bpy.types.Panel):
    bl_label = "Dimensions"
    bl_idname = "CADDIM_PT_main_panel"

    def draw(self, _context):
        self.layout.operator("dimensions.create_dimension", icon="DRIVER_DISTANCE")
        row = self.layout.row(align=True)
        row.operator("dimensions.measure", icon="DRIVER_DISTANCE")
        row.operator("dimensions.create_guide", icon="EMPTY_AXIS")


class CADDIM_PT_GlobalSettings(CADDIM_PT_PanelBase, bpy.types.Panel):
    bl_label = "Global Dimension Settings"
    bl_idname = "CADDIM_PT_global_settings"
    bl_parent_id = CADDIM_PT_MainPanel.bl_idname
    bl_order = 1

    def draw(self, context):
        layout = self.layout
        settings = context.scene.dimensions_settings
        layout.use_property_split = True
        layout.use_property_decorate = False

        unit_system = context.scene.unit_settings.system
        if unit_system == "METRIC":
            layout.prop(settings, "metric_unit_style", text="Unit Style")
        elif unit_system == "IMPERIAL":
            layout.prop(settings, "imperial_unit_style", text="Unit Style")
        else:
            layout.prop(settings, "unit_style")

        configured_style = get_configured_unit_style(context)
        if unit_system == "IMPERIAL" and configured_style in {
            "AUTO",
            "FEET_INCHES",
            "INCH_FRACTION",
        }:
            layout.prop(settings, "imperial_denominator")
        layout.prop(settings, "precision")
        layout.prop(settings, "text_placement")
        layout.prop(settings, "enable_click_select")


class CADDIM_PT_MeshSizeHUD(CADDIM_PT_PanelBase, bpy.types.Panel):
    bl_label = "Selected Mesh Size HUD"
    bl_idname = "CADDIM_PT_mesh_size_hud"
    bl_parent_id = CADDIM_PT_MainPanel.bl_idname
    bl_order = 0
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        settings = context.scene.dimensions_settings
        layout.use_property_split = True
        layout.use_property_decorate = False

        layout.prop(settings, "show_selected_object_overlay", text="Enabled")
        if settings.show_selected_object_overlay:
            layout.prop(settings, "show_overlay_object_name")
            layout.prop(settings, "hud_corner")
            layout.prop(settings, "hud_padding_horizontal")
            layout.prop(settings, "hud_padding_vertical")


class CADDIM_PT_GlobalStyle(CADDIM_PT_PanelBase, bpy.types.Panel):
    bl_label = "Global Dimension Style"
    bl_idname = "CADDIM_PT_global_style"
    bl_parent_id = CADDIM_PT_MainPanel.bl_idname
    bl_order = 2
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        settings = context.scene.dimensions_settings
        layout.use_property_split = True
        layout.use_property_decorate = False

        layout.prop(settings, "dimension_color")
        layout.prop(settings, "selected_dimension_color")
        layout.prop(settings, "dimension_line_width")
        layout.prop(settings, "dimension_text_size")
        layout.prop(settings, "dimension_arrow_size")
        layout.operator("dimensions.apply_global_style_to_all", icon="FILE_REFRESH")


class CADDIM_PT_SelectedDimension(CADDIM_PT_PanelBase, bpy.types.Panel):
    bl_label = "Selected Dimension (Local)"
    bl_idname = "CADDIM_PT_selected_dimension"
    bl_parent_id = CADDIM_PT_MainPanel.bl_idname
    bl_order = 4

    def draw(self, context):
        layout = self.layout
        active_object = context.view_layer.objects.active

        if not is_dimension_object(active_object):
            layout.label(text="No dimension selected.")
            layout.label(text="Settings here affect one dimension only.")
            return

        props = active_object.dimension_props
        layout.use_property_split = True
        layout.use_property_decorate = False
        layout.label(text="Changes below affect only this dimension.")
        layout.prop(active_object, "name", text="Name")
        layout.prop(props, "dimension_type")
        layout.prop(props, "offset_distance")
        layout.prop(props, "offset_angle")
        layout.prop(props, "custom_text")
        if props.custom_text:
            layout.prop(props, "custom_text_position")
        layout.prop(props, "visible")

        style_box = layout.box()
        style_box.label(text="Local Style")
        style_box.prop(props, "color")
        style_box.prop(props, "selected_color")
        style_box.prop(props, "line_width")
        style_box.prop(props, "text_size")
        style_box.prop(props, "arrow_size")
        style_actions = style_box.row(align=True)
        style_actions.operator("dimensions.reset_style_to_global", icon="LOOP_BACK")
        style_actions.operator("dimensions.copy_style_to_global", icon="DUPLICATE")

        start_box = layout.box()
        start_box.label(text="Start Anchor")
        start_box.prop(props.start, "target_object", text="Object")
        start_row = start_box.row(align=True)
        start_row.label(text="Vertex Index")
        start_pick = start_row.operator(
            "dimensions.reattach_anchor",
            text=_vertex_picker_text(props.start),
            icon="EYEDROPPER",
        )
        start_pick.anchor_name = "START"

        end_box = layout.box()
        end_box.label(text="End Anchor")
        end_box.prop(props.end, "target_object", text="Object")
        end_row = end_box.row(align=True)
        end_row.label(text="Vertex Index")
        end_pick = end_row.operator(
            "dimensions.reattach_anchor",
            text=_vertex_picker_text(props.end),
            icon="EYEDROPPER",
        )
        end_pick.anchor_name = "END"


class CADDIM_PT_ConstructionGuides(CADDIM_PT_PanelBase, bpy.types.Panel):
    bl_label = "Construction Guides"
    bl_idname = "CADDIM_PT_construction_guides"
    bl_parent_id = CADDIM_PT_MainPanel.bl_idname
    bl_order = 3
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        settings = context.scene.dimensions_settings
        layout.use_property_split = True
        layout.use_property_decorate = False
        layout.prop(settings, "show_construction_guides")
        layout.prop(settings, "guide_color")
        layout.prop(settings, "guide_line_width")
        layout.operator("dimensions.clear_guides", icon="TRASH")


def _vertex_picker_text(anchor):
    if anchor.vertex_index < 0:
        return "Pick Vertex"

    return str(anchor.vertex_index)


classes = (
    CADDIM_PT_MainPanel,
    CADDIM_PT_MeshSizeHUD,
    CADDIM_PT_GlobalSettings,
    CADDIM_PT_GlobalStyle,
    CADDIM_PT_ConstructionGuides,
    CADDIM_PT_SelectedDimension,
)
