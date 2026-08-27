import bpy

from .constants import SIDEBAR_CATEGORY
from .preferences import get_preferences
from .properties import is_dimension_object
from .units import format_area, format_length, get_configured_unit_style


class CADDIM_PT_PanelBase:
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = SIDEBAR_CATEGORY


class CADDIM_PT_MainPanel(CADDIM_PT_PanelBase, bpy.types.Panel):
    bl_label = "Dimensions"
    bl_idname = "CADDIM_PT_main_panel"

    def draw(self, context):
        annotation_tools = self.layout.column()
        annotation_tools.enabled = context.mode in {"OBJECT", "EDIT_MESH"}
        annotation_tools.operator("dimensions.create_dimension", icon="DRIVER_DISTANCE")
        annotation_tools.operator("dimensions.create_angle", icon="DRIVER_ROTATIONAL_DIFFERENCE")
        annotation_tools.operator("dimensions.create_area", icon="FACESEL")
        annotation_tools.operator("dimensions.measure", icon="DRIVER_DISTANCE")
        guide_row = self.layout.row()
        guide_row.enabled = context.mode == "OBJECT"
        guide_row.operator("dimensions.create_guide", icon="EMPTY_AXIS")
        if context.mode == "EDIT_MESH":
            selection_box = self.layout.box()
            selection_box.label(text="From Mesh Selection")
            selection_box.operator(
                "dimensions.dimension_selected_edge",
                icon="DRIVER_DISTANCE",
            )
            selection_box.operator(
                "dimensions.angle_selected_edges",
                icon="DRIVER_ROTATIONAL_DIFFERENCE",
            )
            selection_box.operator("dimensions.create_area", text="Area from Selected Faces", icon="FACESEL")
            selection_box.operator(
                "dimensions.rebind_area_from_selection",
                text="Apply Faces to Selected Area",
                icon="FILE_REFRESH",
            )

        direction = self.layout.row(align=True)
        direction.label(text="Direction")
        direction.prop(
            get_preferences(context),
            "default_axis_mode",
            text="",
            expand=True,
        )


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
        layout.prop(settings, "snap_pixel_radius")
        preferences = layout.operator("preferences.addon_show", text="Open Add-on Preferences", icon="PREFERENCES")
        preferences.module = "dimensions"


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
            layout.prop(settings, "show_overlay_volume")
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
        layout.prop(settings, "dimension_arrow_end_style")
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
        if active_object.library is not None:
            layout.label(text="Linked annotation: read-only", icon="LOCKED")
            return
        layout.label(text="Changes below affect only this dimension.")
        layout.prop(active_object, "name", text="Name")
        annotation_kind = getattr(props, "annotation_kind", "LINEAR")
        layout.label(text=f"Kind: {annotation_kind.title()}")
        if annotation_kind == "LINEAR":
            layout.prop(props, "measurement_mode")
            layout.prop(props, "dimension_type")
            layout.prop(props, "offset_distance")
            layout.prop(props, "offset_angle")
        elif annotation_kind == "AREA":
            precision = context.scene.dimensions_settings.precision
            layout.label(text=f"Measured Area: {format_area(context, props.area_value, precision)}")
            layout.label(text=f"State: {props.measurement_state.replace('_', ' ').title()}")
            source_name = props.area_source_object.name if props.area_source_object is not None else "Missing"
            layout.label(text=f"Source: {source_name}")
            if props.area_face_count:
                layout.label(text=f"Bound Faces: {props.area_face_count}")
            axis_label = "Aligned" if props.dimension_type == "ALIGNED" else f"{props.dimension_type} Axis"
            precision = context.scene.dimensions_settings.precision
            layout.label(text=f"Placement: {axis_label}, {format_length(context, props.offset_distance, precision)}")
            area_actions = layout.row(align=True)
            area_actions.operator("dimensions.move_area_label", text="Move Label", icon="ORIENTATION_CURSOR")
            remake = area_actions.operator("dimensions.create_area", text="Remake Area", icon="FILE_REFRESH")
            remake.replace_active = True
            area_source_actions = layout.row(align=True)
            area_source_actions.operator("dimensions.select_area_source", text="Select Source Faces", icon="RESTRICT_SELECT_OFF")
            area_source_actions.operator("dimensions.capture_area", text="Capture", icon="REC")
        elif annotation_kind == "ANGLE":
            layout.prop(props, "angle_radius")
            layout.prop(props, "angle_mode")
            layout.label(text=f"State: {props.measurement_state.replace('_', ' ').title()}")
            layout.label(text="Source: Two Edges" if props.angle_source_mode == "EDGES" else "Source: Legacy Three Point")
            if props.angle_source_mode == "EDGES":
                edge_actions = layout.row(align=True)
                replace_a = edge_actions.operator("dimensions.replace_angle_edge", text="Replace Edge A", icon="EYEDROPPER")
                replace_a.edge_slot = "A"
                replace_b = edge_actions.operator("dimensions.replace_angle_edge", text="Replace Edge B", icon="EYEDROPPER")
                replace_b.edge_slot = "B"
            remake = layout.operator("dimensions.create_angle", text="Remake Angle", icon="FILE_REFRESH")
            remake.replace_active = True
        layout.prop(props, "custom_text")
        if props.custom_text:
            layout.prop(props, "custom_text_position")
        value_text = layout.row(align=True)
        value_text.prop(props, "value_prefix", text="Prefix")
        value_text.prop(props, "value_suffix", text="Suffix")
        if annotation_kind == "LINEAR":
            layout.prop(props, "tolerance_mode")
            if props.tolerance_mode == "SYMMETRIC":
                layout.prop(props, "tolerance_upper", text="Plus / Minus")
            elif props.tolerance_mode == "DEVIATION":
                layout.prop(props, "tolerance_upper")
                layout.prop(props, "tolerance_lower")
        layout.prop(props, "visible")

        style_box = layout.box()
        style_box.label(text="Local Style")
        style_box.prop(props, "color")
        style_box.prop(props, "selected_color")
        style_box.prop(props, "line_width")
        style_box.prop(props, "text_size")
        style_box.prop(props, "arrow_size")
        style_box.prop(props, "arrow_end_style")
        style_actions = style_box.row(align=True)
        style_actions.operator("dimensions.reset_style_to_global", icon="LOOP_BACK")
        style_actions.operator("dimensions.copy_style_to_global", icon="DUPLICATE")

        if annotation_kind in {"AREA", "ANGLE"}:
            return

        start_box = layout.box()
        start_box.label(text="Start Anchor")
        start_box.prop(props.start, "target_object", text="Object")
        start_row = start_box.row(align=True)
        start_row.label(text="Anchor")
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
        end_row.label(text="Anchor")
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
        actions = layout.row(align=True)
        actions.operator("dimensions.clear_guides", text="Clear Guides", icon="TRASH")
        actions.operator("dimensions.clear_measurements", text="Clear Measures", icon="TRASH")


class CADDIM_PT_Output(CADDIM_PT_PanelBase, bpy.types.Panel):
    bl_label = "Grease Pencil Output"
    bl_idname = "CADDIM_PT_output"
    bl_parent_id = CADDIM_PT_MainPanel.bl_idname
    bl_order = 5
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        settings = context.scene.dimensions_settings
        layout.use_property_split = True
        layout.use_property_decorate = False
        layout.prop(settings, "output_scope")
        layout.prop(settings, "output_sizing_mode")
        if settings.output_sizing_mode == "CAMERA":
            layout.prop(settings, "output_line_width")
            layout.prop(settings, "output_text_height")
            layout.prop(settings, "output_arrow_size")
        else:
            layout.prop(settings, "output_world_line_width")
            layout.prop(settings, "output_world_text_height")
            layout.prop(settings, "output_world_arrow_size")
        layout.operator("dimensions.generate_output", icon="GREASEPENCIL")
        layout.label(text="Disposable: regeneration replaces hand edits", icon="ERROR")


def _vertex_picker_text(anchor):
    if getattr(anchor, "anchor_type", "VERTEX") == "WORLD":
        return "World Point"
    if getattr(anchor, "anchor_type", "VERTEX") == "OBJECT_POINT":
        return "Object Point"

    if anchor.vertex_index < 0:
        return "Pick Vertex"

    if getattr(anchor, "vertex_id", 0) > 0:
        return f"ID {anchor.vertex_id}"
    return f"Legacy Vertex {anchor.vertex_index}"


classes = (
    CADDIM_PT_MainPanel,
    CADDIM_PT_MeshSizeHUD,
    CADDIM_PT_GlobalSettings,
    CADDIM_PT_GlobalStyle,
    CADDIM_PT_ConstructionGuides,
    CADDIM_PT_Output,
    CADDIM_PT_SelectedDimension,
)
