import bpy

from .annotation_manager import annotation_is_hidden, manager_item_matches
from .constants import SIDEBAR_CATEGORY
from .preferences import ADDON_ID, get_preferences
from .properties import (
    is_dimension_object,
    is_read_only_dimensions_object,
    resolve_dimension_style,
)
from .repair import repair_issues
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
        set_row = annotation_tools.row(align=True)
        chain = set_row.operator("dimensions.create_dimension_set", text="Chain", icon="GROUP")
        chain.set_kind = "CHAIN"
        baseline = set_row.operator("dimensions.create_dimension_set", text="Baseline", icon="ALIGN_JUSTIFY")
        baseline.set_kind = "BASELINE"
        circle_row = annotation_tools.row(align=True)
        for kind, label in (("RADIUS", "Radial"), ("DIAMETER", "Diameter"), ("ARC_LENGTH", "Arc")):
            operator = circle_row.operator("dimensions.create_circle_dimension", text=label)
            operator.circle_kind = kind
        annotation_tools.operator("dimensions.create_angle", icon="DRIVER_ROTATIONAL_DIFFERENCE")
        annotation_tools.operator("dimensions.create_area", icon="FACESEL")
        datum_row = annotation_tools.row(align=True)
        datum_row.operator("dimensions.create_coordinate", text="Coordinate", icon="ORIENTATION_GLOBAL")
        datum_row.operator("dimensions.create_elevation", text="Elevation", icon="EMPTY_SINGLE_ARROW")
        annotation_tools.operator("dimensions.measure", icon="DRIVER_DISTANCE")
        guide_row = self.layout.row()
        guide_row.enabled = context.mode == "OBJECT"
        guide_row.operator("dimensions.create_guide", icon="EMPTY_AXIS")
        point = guide_row.operator("dimensions.create_guide_point", text="Guide Point", icon="SNAP_ON")
        point.placement_mode = "DIRECT"
        guide_row.operator("dimensions.create_datum", text="Datum", icon="EMPTY_AXIS")

        direction = self.layout.column(align=True)
        direction.label(text="Direction")
        direction_buttons = direction.row(align=True)
        preferences = get_preferences(context)
        for value, label in (("ALIGNED", "Auto"), ("X", "X"), ("Y", "Y"), ("Z", "Z")):
            direction_buttons.prop_enum(preferences, "default_axis_mode", value, text=label)

        from .snap_targets import draw_snap_target_row

        snap_box = self.layout.box()
        snap_box.label(text="Snap Targets")
        settings = context.scene.dimensions_settings
        snap_box.prop(settings, "use_snap_target_override", text="Scene Override")
        source = settings if settings.use_snap_target_override else preferences
        snap_box.prop(
            source,
            "snap_pixel_radius" if settings.use_snap_target_override else "snap_pixel_threshold",
            text="Snap Radius",
        )
        draw_snap_target_row(snap_box, source)


class CADDIM_PT_MeshSelection(CADDIM_PT_PanelBase, bpy.types.Panel):
    bl_label = "From Mesh Selection"
    bl_idname = "CADDIM_PT_mesh_selection"
    bl_parent_id = CADDIM_PT_MainPanel.bl_idname
    bl_order = 0

    @classmethod
    def poll(cls, context):
        return context.mode == "EDIT_MESH"

    def draw(self, _context):
        layout = self.layout
        layout.operator("dimensions.dimension_selected_edge", icon="DRIVER_DISTANCE")
        layout.operator("dimensions.angle_selected_edges", icon="DRIVER_ROTATIONAL_DIFFERENCE")
        layout.operator("dimensions.create_area", text="Area from Selected Faces", icon="FACESEL")
        layout.operator(
            "dimensions.rebind_area_from_selection",
            text="Apply Faces to Selected Area",
            icon="FILE_REFRESH",
        )


class CADDIM_PT_GlobalSettings(CADDIM_PT_PanelBase, bpy.types.Panel):
    bl_label = "Global Dimension Settings"
    bl_idname = "CADDIM_PT_global_settings"
    bl_parent_id = CADDIM_PT_MainPanel.bl_idname
    bl_order = 2

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
        preferences = layout.operator("preferences.addon_show", text="Open Add-on Preferences", icon="PREFERENCES")
        preferences.module = ADDON_ID


class CADDIM_PT_MeshSizeHUD(CADDIM_PT_PanelBase, bpy.types.Panel):
    bl_label = "Selected Mesh Size HUD"
    bl_idname = "CADDIM_PT_mesh_size_hud"
    bl_parent_id = CADDIM_PT_MainPanel.bl_idname
    bl_order = 1
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
    bl_order = 3
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
        endpoints = layout.column(align=True)
        endpoints.prop(settings, "dimension_start_end_style")
        endpoints.prop(settings, "dimension_end_end_style")
        layout.prop(settings, "dimension_extension_gap")
        layout.prop(settings, "dimension_extension_overshoot")
        layout.prop(settings, "dimension_secondary_unit_style")
        if settings.dimension_secondary_unit_style != "NONE":
            layout.prop(settings, "dimension_secondary_precision")
            layout.prop(settings, "dimension_dual_unit_arrangement")
        layout.prop(settings, "dimension_label_orientation")
        layout.prop(settings, "dimension_label_line_mode")
        layout.operator("dimensions.apply_global_style_to_all", icon="FILE_REFRESH")


_MANAGER_KIND_ICONS = {
    "LINEAR": "DRIVER_DISTANCE",
    "ANGLE": "DRIVER_ROTATIONAL_DIFFERENCE",
    "AREA": "FACESEL",
    "MEASUREMENT": "RULER",
    "GUIDE": "EMPTY_AXIS",
    "POINT": "SNAP_ON",
    "DIMENSION_SET": "GROUP",
    "CIRCLE": "MESH_CIRCLE",
}


class CADDIM_UL_AnnotationManager(bpy.types.UIList):
    def draw_item(self, _context, layout, _data, item, _icon, _active_data, _active_propname, _index):
        obj = item.annotation
        if obj is None:
            layout.label(text="Missing annotation", icon="ERROR")
            return
        row = layout.row(align=True)
        row.label(text="", icon=_MANAGER_KIND_ICONS.get(item.kind, "OBJECT_DATA"))
        select = row.operator("dimensions.manager_select", text=obj.name, emboss=False)
        select.object_name = obj.name
        row.label(text=item.display_value)
        if item.state in {"NEEDS_REPAIR", "FALLBACK"}:
            repair = row.operator(
                "dimensions.manager_repair_entry", text="",
                icon="ERROR" if item.state == "NEEDS_REPAIR" else "QUESTION",
            )
            repair.object_name = obj.name
        elif item.state == "CAPTURED":
            row.label(text="", icon="REC")
        else:
            row.label(text="", icon="CHECKMARK")
        visibility = row.operator(
            "dimensions.manager_toggle_visibility", text="",
            icon="HIDE_ON" if annotation_is_hidden(obj) else "HIDE_OFF",
        )
        visibility.object_name = obj.name
        jump = row.operator("dimensions.manager_jump_to", text="", icon="VIEWZOOM")
        jump.object_name = obj.name
        edit_row = row.row(align=True)
        edit_row.enabled = not is_read_only_dimensions_object(obj)
        rename = edit_row.operator("dimensions.manager_rename", text="", icon="GREASEPENCIL")
        rename.object_name = obj.name
        delete = edit_row.operator("dimensions.manager_delete", text="", icon="TRASH")
        delete.object_name = obj.name

    def draw_filter(self, context, layout):
        settings = context.scene.dimensions_settings
        layout.prop(settings, "annotation_manager_search", text="", icon="VIEWZOOM")
        kinds = layout.row(align=True)
        for name, label in (
            ("linear", "L"), ("angle", "A"), ("area", "Area"),
            ("dimension_set", "Set"),
            ("circle", "R/⌀/⌒"),
            ("measurement", "M"), ("guide", "G"), ("point", "P"), ("plane", "Pl"),
            ("coordinate", "XYZ"), ("elevation", "El"), ("datum", "D"),
        ):
            kinds.prop(settings, f"annotation_manager_kind_{name}", text=label, toggle=True)
        states = layout.row(align=True)
        states.prop(settings, "annotation_manager_state_live", text="Live", toggle=True)
        states.prop(settings, "annotation_manager_state_fallback", text="Fallback", toggle=True)
        states.prop(settings, "annotation_manager_state_captured", text="Captured", toggle=True)
        states.prop(settings, "annotation_manager_state_needs_repair", text="Repair", toggle=True)
        states.prop(settings, "annotation_manager_references_active", text="References Active", toggle=True)
        if settings.annotation_manager_references_active:
            states.prop(settings, "annotation_manager_reference_object", text="")

    def filter_items(self, _context, data, property_name):
        items = getattr(data, property_name)
        flags = [
            self.bitflag_filter_item if manager_item_matches(data, item) else 0
            for item in items
        ]
        return flags, []


class CADDIM_PT_AnnotationManager(CADDIM_PT_PanelBase, bpy.types.Panel):
    bl_label = "Annotation Manager"
    bl_idname = "CADDIM_PT_annotation_manager"
    bl_parent_id = CADDIM_PT_MainPanel.bl_idname
    bl_order = 2

    def draw(self, context):
        layout = self.layout
        settings = context.scene.dimensions_settings
        layout.template_list(
            "CADDIM_UL_AnnotationManager", "", settings, "annotation_manager_items",
            settings, "active_annotation_manager_index", rows=7,
        )
        if not settings.annotation_manager_items:
            layout.label(text="No annotations or guides in this scene")
            return
        index = settings.active_annotation_manager_index
        if 0 <= index < len(settings.annotation_manager_items):
            managed = settings.annotation_manager_items[index].annotation
            if is_dimension_object(managed) and managed.dimension_props.annotation_kind == "DIMENSION_SET":
                props = managed.dimension_props
                member_box = layout.box()
                member_box.prop(
                    props, "set_expanded", text=f"{props.set_kind.title()} Members ({len(props.set_members)})",
                    icon="DISCLOSURE_TRI_DOWN" if props.set_expanded else "DISCLOSURE_TRI_RIGHT",
                )
                if props.set_expanded:
                    for member_index, member in enumerate(props.set_members):
                        row = member_box.row(align=True)
                        row.label(text=f"{member_index + 1}")
                        row.label(text=member.measurement_state.replace("_", " ").title())
                        select_member = row.operator("dimensions.manager_select_set_member", text="", icon="RESTRICT_SELECT_OFF")
                        select_member.object_name = managed.name
                        select_member.member_index = member_index
        layout.prop(settings, "annotation_manager_bulk_scope", expand=True)
        visibility = layout.row(align=True)
        for action, label, icon in (
            ("SHOW", "Show", "HIDE_OFF"),
            ("HIDE", "Hide", "HIDE_ON"),
            ("ISOLATE", "Isolate", "SOLO_ON"),
        ):
            operator = visibility.operator("dimensions.manager_bulk_visibility", text=label, icon=icon)
            operator.action = action
        if settings.annotation_manager_isolate_active:
            restore = layout.operator("dimensions.manager_bulk_visibility", text="Exit Isolate", icon="LOOP_BACK")
            restore.action = "RESTORE"
        actions = layout.row(align=True)
        actions.operator("dimensions.manager_bulk_style", text="Apply Named Style", icon="BRUSH_DATA")
        actions.operator("dimensions.manager_bulk_reset_style", text="Reset Global", icon="LOOP_BACK")
        layout.operator("dimensions.manager_bulk_delete", text="Delete Scope", icon="TRASH")


class CADDIM_PT_GuidedRepair(CADDIM_PT_PanelBase, bpy.types.Panel):
    bl_label = "Guided Repair"
    bl_idname = "CADDIM_PT_guided_repair"
    bl_parent_id = CADDIM_PT_MainPanel.bl_idname
    bl_order = 3

    @classmethod
    def poll(cls, context):
        active = context.view_layer.objects.active
        return is_dimension_object(active) and bool(repair_issues(active))

    def draw(self, context):
        layout = self.layout
        annotation = context.view_layer.objects.active
        issues = repair_issues(annotation)
        read_only = is_read_only_dimensions_object(annotation)
        layout.label(text=annotation.name, icon="ERROR")
        for issue in issues:
            box = layout.box()
            state = "Fallback" if issue["status"] == "BY_FALLBACK" else "Unresolvable"
            box.label(text=f"{issue['type'].title()}: {state}")
            box.label(text=f"Source: {issue['source_name']}")
            frame = box.operator("dimensions.repair_frame_issue", text="Frame Last Known Position", icon="VIEWZOOM")
            frame.object_name = annotation.name
            candidate = issue.get("candidate")
            if candidate is not None:
                box.label(text=f"Suggested: {candidate['label']}", icon="QUESTION")
            actions = box.row(align=True)
            actions.enabled = not read_only
            if issue["type"] == "AREA":
                pick = actions.operator("dimensions.repair_pick_area_source", text="Pick Face", icon="EYEDROPPER")
                pick.object_name = annotation.name
            else:
                pick = actions.operator("dimensions.reattach_anchor", text="Pick Point", icon="EYEDROPPER")
                anchor_name = issue["anchor_name"]
                if anchor_name.startswith("SET_"):
                    _prefix, member_index, slot = anchor_name.split("_", 2)
                    pick.anchor_name = f"SET_{slot}"
                    pick.member_index = int(member_index)
                elif anchor_name.startswith("CIRCLE_"):
                    _prefix, vertex_index = anchor_name.split("_", 1)
                    pick.anchor_name = "CIRCLE_VERTEX"
                    pick.member_index = int(vertex_index)
                else:
                    pick.anchor_name = anchor_name
                if issue["status"] == "UNRESOLVABLE":
                    convert = actions.operator("dimensions.repair_convert_world", text="Use World Point", icon="EMPTY_AXIS")
                    convert.object_name = annotation.name
                    convert.anchor_name = issue["anchor_name"]
        confirm = layout.column(align=True)
        confirm.enabled = not read_only and any(issue.get("candidate") is not None for issue in issues)
        accept = confirm.operator("dimensions.repair_accept_suggestion", text="Accept Suggested Repair", icon="CHECKMARK")
        accept.object_name = annotation.name
        bulk = confirm.operator("dimensions.repair_bulk_cause", text="Repair Matching Cause", icon="DUPLICATE")
        bulk.object_name = annotation.name
        if read_only:
            layout.label(text="Linked annotation: make local to repair", icon="LOCKED")


class CADDIM_UL_AnnotationStyles(bpy.types.UIList):
    def draw_item(self, _context, layout, _data, item, _icon, _active_data, _active_propname, _index):
        layout.label(text=item.name, icon="BRUSH_DATA")


class CADDIM_PT_AnnotationStyles(CADDIM_PT_PanelBase, bpy.types.Panel):
    bl_label = "Named Annotation Styles"
    bl_idname = "CADDIM_PT_annotation_styles"
    bl_parent_id = CADDIM_PT_MainPanel.bl_idname
    bl_order = 4
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        settings = context.scene.dimensions_settings
        row = layout.row()
        row.template_list(
            "CADDIM_UL_AnnotationStyles", "", settings, "annotation_styles",
            settings, "active_annotation_style_index", rows=3,
        )
        actions = row.column(align=True)
        actions.operator("dimensions.create_annotation_style", text="", icon="ADD")
        actions.operator("dimensions.duplicate_annotation_style", text="", icon="DUPLICATE")
        actions.operator("dimensions.rename_annotation_style", text="", icon="GREASEPENCIL")
        actions.operator("dimensions.delete_annotation_style", text="", icon="REMOVE")
        index = settings.active_annotation_style_index
        if not (0 <= index < len(settings.annotation_styles)):
            layout.label(text="Create a style to begin")
            return
        style = settings.annotation_styles[index]
        layout.use_property_split = True
        layout.use_property_decorate = False
        layout.prop(style, "color")
        layout.prop(style, "selected_color")
        layout.prop(style, "line_width")
        layout.prop(style, "text_size")
        layout.prop(style, "precision")
        layout.prop(style, "arrow_size")
        layout.prop(style, "start_end_style")
        layout.prop(style, "end_end_style")
        layout.prop(style, "extension_gap")
        layout.prop(style, "extension_overshoot")
        layout.prop(style, "unit_style")
        layout.prop(style, "secondary_unit_style")
        if style.secondary_unit_style != "NONE":
            layout.prop(style, "secondary_precision")
            layout.prop(style, "dual_unit_arrangement")
        layout.prop(style, "label_orientation")
        layout.prop(style, "label_line_mode")
        text = layout.row(align=True)
        text.prop(style, "value_prefix")
        text.prop(style, "value_suffix")
        layout.prop(style, "tolerance_mode")
        if style.tolerance_mode == "SYMMETRIC":
            layout.prop(style, "tolerance_upper", text="Plus / Minus")
        elif style.tolerance_mode == "DEVIATION":
            layout.prop(style, "tolerance_upper")
            layout.prop(style, "tolerance_lower")
        bulk = layout.row(align=True)
        bulk.operator("dimensions.assign_annotation_style", icon="CHECKMARK")
        bulk.operator("dimensions.select_annotation_style_users", icon="RESTRICT_SELECT_OFF")


def _inherited_style_text(style, property_name, label=None):
    display_name = label or property_name.replace("_", " ").title()
    if property_name == "tolerance":
        mode = style.tolerance_mode.replace("_", " ").title()
        return f"{display_name}: inherited {mode}"
    value = getattr(style, property_name)
    if property_name in {"color", "selected_color"}:
        value = ", ".join(f"{channel:.2f}" for channel in value)
    if property_name in {"arrow_end_style", "start_end_style", "end_end_style", "unit_style", "secondary_unit_style", "dual_unit_arrangement", "label_orientation", "label_line_mode"}:
        value = value.replace("_", " ").title()
    return f"{display_name}: inherited {value}"


def _draw_style_override(layout, props, resolved_style, property_name, label=None):
    row = layout.row(align=True)
    override_name = f"override_{property_name}"
    row.prop(props, override_name, text="", icon="DECORATE_KEYFRAME")
    if not getattr(props, override_name):
        row.label(text=_inherited_style_text(resolved_style, property_name, label))
        return
    value = row.row(align=True)
    if property_name == "tolerance":
        value.prop(props, "tolerance_mode", text=label or "Tolerance")
    elif label is not None:
        value.prop(props, property_name, text=label)
    else:
        value.prop(props, property_name)


class CADDIM_PT_SelectedDimension(CADDIM_PT_PanelBase, bpy.types.Panel):
    bl_label = "Selected Dimension (Local)"
    bl_idname = "CADDIM_PT_selected_dimension"
    bl_parent_id = CADDIM_PT_MainPanel.bl_idname
    bl_order = 5

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
        if is_read_only_dimensions_object(active_object):
            source = "Library override" if active_object.override_library is not None else "Linked annotation"
            layout.label(text=f"{source}: read-only", icon="LOCKED")
            return
        layout.label(text="Changes below affect only this dimension.")
        layout.label(text="Transform: location only; rotation and scale are ignored", icon="LOCKED")
        layout.prop(active_object, "name", text="Name")
        annotation_kind = getattr(props, "annotation_kind", "LINEAR")
        layout.label(text=f"Kind: {annotation_kind.title()}")
        if annotation_kind == "CIRCLE":
            from .circle_binding import circle_geometry, circle_value

            fit = circle_geometry(props)
            layout.label(text=f"Type: {props.circle_kind.replace('_', ' ').title()}")
            state = props.measurement_state if fit is None else fit["state"]
            layout.label(text=f"State: {state.replace('_', ' ').title()}")
            if fit is not None:
                layout.label(text=f"Value: {format_length(context, circle_value(props, fit), props.precision, props.unit_style)}")
                layout.label(text=f"Fit error: {fit['fit_error'] * 100.0:.3f}%", icon="ERROR" if fit["fit_warning"] else "CHECKMARK")
            layout.prop(props, "circle_fit_mode")
            layout.prop(props, "circle_fit_warning_threshold")
            layout.prop(props, "circle_leader_angle")
            layout.prop(props, "circle_label_distance")
            layout.operator("dimensions.capture_circle_dimension", icon="REC")
            layout.label(text=f"Bound points: {len(props.circle_vertices)}")
        elif annotation_kind == "DIMENSION_SET":
            from .dimension_sets import automatic_baseline_spacing, dimension_set_state

            layout.label(text=f"Type: {props.set_kind.title()}")
            layout.label(text=f"State: {dimension_set_state(props).replace('_', ' ').title()}")
            layout.prop(props, "offset_distance", text="Shared Offset")
            if props.set_kind == "BASELINE":
                layout.prop(props, "set_spacing")
                if props.set_spacing <= 1e-6:
                    layout.label(text=f"Automatic: {automatic_baseline_spacing(props):.3f} scene units")
            layout.prop(
                props, "set_expanded", text=f"Members ({len(props.set_members)})",
                icon="DISCLOSURE_TRI_DOWN" if props.set_expanded else "DISCLOSURE_TRI_RIGHT",
            )
            if props.set_expanded:
                layout.prop(props, "active_set_member_index", text="Active")
                for index, member in enumerate(props.set_members):
                    box = layout.box()
                    box.label(text=f"{index + 1}. {member.measurement_state.replace('_', ' ').title()}")
                    actions = box.row(align=True)
                    start_pick = actions.operator("dimensions.reattach_anchor", text="Start", icon="EYEDROPPER")
                    start_pick.anchor_name = "SET_START"
                    start_pick.member_index = index
                    end_pick = actions.operator("dimensions.reattach_anchor", text="End", icon="EYEDROPPER")
                    end_pick.anchor_name = "SET_END"
                    end_pick.member_index = index
                    if props.set_kind == "CHAIN":
                        insert = actions.operator("dimensions.insert_dimension_set_member", text="Insert", icon="ADD")
                        insert.object_name = active_object.name
                        insert.member_index = index
                    delete = actions.operator("dimensions.delete_dimension_set_member", text="", icon="TRASH")
                    delete.object_name = active_object.name
                    delete.member_index = index
        elif annotation_kind == "LINEAR":
            layout.label(text=f"State: {props.measurement_state.replace('_', ' ').title()}")
            layout.prop(props, "measurement_mode")
            layout.prop(props, "dimension_type")
            layout.prop(props, "offset_distance")
            adjust = layout.operator("dimensions.drag_annotation_handle", text="Adjust Offset in View", icon="ORIENTATION_CURSOR")
            adjust.object_name = active_object.name
            adjust.handle_kind = "LINEAR_OFFSET"
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
            adjust = layout.operator("dimensions.drag_annotation_handle", text="Adjust Radius in View", icon="ORIENTATION_CURSOR")
            adjust.object_name = active_object.name
            adjust.handle_kind = "ANGLE_RADIUS"
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
        elif annotation_kind == "COORDINATE":
            layout.label(text=f"State: {props.measurement_state.replace('_', ' ').title()}")
            layout.prop(props, "datum_object")
            layout.prop(props, "coordinate_components")
            layout.prop(props, "coordinate_alignment")
            if props.coordinate_alignment != "FREE":
                layout.prop(props, "coordinate_alignment_offset")
            layout.prop(props, "coordinate_sign")
            layout.prop(props, "coordinate_show_plus")
            layout.prop(props, "coordinate_show_negative")
        elif annotation_kind == "ELEVATION":
            layout.label(text=f"State: {props.measurement_state.replace('_', ' ').title()}")
            layout.prop(props, "datum_object")
            layout.prop(props, "elevation_axis")
            layout.prop(props, "elevation_mode")
            if props.elevation_mode == "RELATIVE":
                layout.prop(props, "elevation_reference")
            layout.prop(props, "elevation_precision")
            layout.prop(props, "elevation_show_plus")
            layout.prop(props, "elevation_prefix")
            layout.prop(props, "elevation_suffix")
        layout.prop(props, "custom_text")
        if props.custom_text:
            layout.prop(props, "custom_text_position")
        layout.prop(props, "visible")

        style_box = layout.box()
        style_box.label(text=f"Style: {props.style_name or 'Scene Defaults'}")
        resolved_style = resolve_dimension_style(context.scene.dimensions_settings, props)
        _draw_style_override(style_box, props, resolved_style, "color")
        _draw_style_override(style_box, props, resolved_style, "selected_color")
        _draw_style_override(style_box, props, resolved_style, "line_width")
        _draw_style_override(style_box, props, resolved_style, "text_size")
        _draw_style_override(style_box, props, resolved_style, "precision")
        _draw_style_override(style_box, props, resolved_style, "arrow_size")
        _draw_style_override(style_box, props, resolved_style, "start_end_style")
        _draw_style_override(style_box, props, resolved_style, "end_end_style")
        _draw_style_override(style_box, props, resolved_style, "extension_gap")
        _draw_style_override(style_box, props, resolved_style, "extension_overshoot")
        _draw_style_override(style_box, props, resolved_style, "unit_style")
        _draw_style_override(style_box, props, resolved_style, "secondary_unit_style")
        _draw_style_override(style_box, props, resolved_style, "secondary_precision")
        _draw_style_override(style_box, props, resolved_style, "dual_unit_arrangement")
        _draw_style_override(style_box, props, resolved_style, "label_orientation")
        _draw_style_override(style_box, props, resolved_style, "label_line_mode")
        _draw_style_override(style_box, props, resolved_style, "value_prefix", "Prefix")
        _draw_style_override(style_box, props, resolved_style, "value_suffix", "Suffix")
        _draw_style_override(style_box, props, resolved_style, "tolerance")
        if props.override_tolerance and props.tolerance_mode == "SYMMETRIC":
            style_box.prop(props, "tolerance_upper", text="Plus / Minus")
        elif props.override_tolerance and props.tolerance_mode == "DEVIATION":
            style_box.prop(props, "tolerance_upper")
            style_box.prop(props, "tolerance_lower")
        style_actions = style_box.row(align=True)
        style_actions.operator("dimensions.clear_annotation_style_overrides", icon="BRUSH_DATA")
        style_actions.operator("dimensions.reset_style_to_global", icon="LOOP_BACK")
        style_actions.operator("dimensions.copy_style_to_global", icon="DUPLICATE")

        if annotation_kind in {"AREA", "ANGLE", "DIMENSION_SET", "CIRCLE"}:
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
    bl_order = 4
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
        direct = actions.operator("dimensions.create_guide_point", text="Point", icon="SNAP_ON")
        direct.placement_mode = "DIRECT"
        offset = actions.operator("dimensions.create_guide_point", text="Offset", icon="DRIVER_DISTANCE")
        offset.placement_mode = "OFFSET"
        selection = actions.operator("dimensions.create_guide_point", text="Selection", icon="RESTRICT_SELECT_OFF")
        selection.placement_mode = "SELECTION"
        datum = layout.box()
        datum.label(text="Named Datum", icon="ORIENTATION_GLOBAL")
        datum.operator("dimensions.create_datum", text="Create / Promote Active")
        active = context.view_layer.objects.active
        if (
            active is not None and getattr(getattr(active, "guide_props", None), "kind", "") == "POINT"
            and getattr(active.guide_props, "is_datum", False)
        ):
            datum.prop(active.guide_props, "datum_name")
            datum.prop(active.guide_props, "datum_orientation")
        actions = layout.row(align=True)
        offset = actions.operator("dimensions.create_derived_guide", text="Offset Guide", icon="MOD_OFFSET")
        offset.mode = "OFFSET"
        centerline = actions.operator("dimensions.create_derived_guide", text="Centerline", icon="MOD_MIRROR")
        centerline.mode = "CENTERLINE"
        advanced = layout.row(align=True)
        advanced.operator("dimensions.create_angular_guide", text="Angular", icon="DRIVER_ROTATIONAL_DIFFERENCE")
        advanced.operator("dimensions.create_spacing_guide", text="Spacing", icon="MOD_ARRAY")
        planes = layout.box()
        planes.label(text="Construction Planes", icon="MESH_GRID")
        active_frame = None
        try:
            from .guide_planes import active_plane_frame

            active_frame = active_plane_frame(context.scene)
        except (ImportError, RuntimeError):
            pass
        if settings.active_plane_mode == "NONE":
            planes.label(text="Active Plane: None (world axes)", icon="WORLD")
        else:
            label = settings.active_plane_mode.replace("WORLD_", "World ").replace("_", " ").title()
            planes.label(
                text=f"ACTIVE PLANE: {label}" if active_frame is not None else "ACTIVE PLANE: Needs Repair",
                icon="ERROR" if active_frame is None else "ORIENTATION_VIEW",
            )
        create = planes.row(align=True)
        three = create.operator("dimensions.create_guide_plane", text="3 Points")
        three.definition = "THREE_POINTS"
        face = create.operator("dimensions.create_guide_plane", text="Face")
        face.definition = "FACE"
        point_normal = create.operator("dimensions.create_guide_plane", text="Cursor + Normal")
        point_normal.definition = "POINT_NORMAL"
        offset_plane = create.operator("dimensions.create_guide_plane", text="Offset")
        offset_plane.definition = "OFFSET"
        activate = planes.row(align=True)
        activate.operator("dimensions.set_active_guide_plane", text="Use Selected")
        activate.operator("dimensions.set_active_face_plane", text="Use Face")
        activate.operator("dimensions.set_view_plane", text="Use View")
        activate.operator("dimensions.clear_active_plane", text="Clear", icon="X")
        world = planes.row(align=True)
        for identifier, label in (("WORLD_XY", "World XY"), ("WORLD_YZ", "World YZ"), ("WORLD_ZX", "World ZX")):
            operator = world.operator("dimensions.set_world_plane", text=label)
            operator.plane = identifier
        active = context.view_layer.objects.active
        if active is not None and getattr(getattr(active, "guide_props", None), "kind", "") == "PLANE":
            planes.prop(active.guide_props, "plane_definition", text="Definition")
            if active.guide_props.plane_definition == "POINT_NORMAL":
                planes.prop(active.guide_props, "plane_normal")
            elif active.guide_props.plane_definition == "OFFSET":
                planes.prop(active.guide_props, "offset_distance")
            planes.prop(active.guide_props, "plane_extent")
        actions = layout.row(align=True)
        active = context.view_layer.objects.active
        detach = actions.operator("dimensions.detach_derived_guide", text="Detach Selected", icon="UNLINKED")
        actions.enabled = bool(
            active is not None and getattr(getattr(active, "guide_props", None), "derived", False)
        )
        if active is not None and getattr(getattr(active, "guide_props", None), "derivation_mode", "NONE") in {"ANGULAR", "SPACING"}:
            edit = layout.box()
            if active.guide_props.derivation_mode == "ANGULAR":
                edit.label(text="Angular Guide")
                edit.prop(active.guide_props, "guide_angle")
            else:
                edit.label(text="Repeated Spacing")
                edit.prop(active.guide_props, "spacing_mode")
                if active.guide_props.spacing_mode != "DISTRIBUTE":
                    edit.prop(active.guide_props, "spacing_interval")
                edit.prop(active.guide_props, "spacing_count")
                if active.guide_props.spacing_mode != "COUNT":
                    edit.prop(active.guide_props, "spacing_extent")
                edit.operator("dimensions.bake_spacing_guide", icon="DUPLICATE")
        actions = layout.row(align=True)
        actions.operator("dimensions.clear_guides", text="Clear Guides", icon="TRASH")
        actions.operator("dimensions.clear_measurements", text="Clear Measures", icon="TRASH")


class CADDIM_PT_Output(CADDIM_PT_PanelBase, bpy.types.Panel):
    bl_label = "Output"
    bl_idname = "CADDIM_PT_output"
    bl_parent_id = CADDIM_PT_MainPanel.bl_idname
    bl_order = 6
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        settings = context.scene.dimensions_settings
        layout.use_property_split = True
        layout.use_property_decorate = False
        layout.prop(settings, "output_scope")
        grease_pencil = layout.box()
        grease_pencil.label(text="Grease Pencil", icon="GREASEPENCIL")
        grease_pencil.prop(settings, "output_sizing_mode")
        if settings.output_sizing_mode == "CAMERA":
            grease_pencil.prop(settings, "output_line_width")
            grease_pencil.prop(settings, "output_text_height")
            grease_pencil.prop(settings, "output_arrow_size")
        else:
            grease_pencil.prop(settings, "output_world_line_width")
            grease_pencil.prop(settings, "output_world_text_height")
            grease_pencil.prop(settings, "output_world_arrow_size")
        grease_pencil.operator("dimensions.generate_output", icon="GREASEPENCIL")
        grease_pencil.label(text="Disposable: regeneration replaces hand edits", icon="ERROR")

        vector = layout.box()
        vector.label(text="Scale-Correct SVG / PDF", icon="FILE_IMAGE")
        vector.prop(settings, "vector_paper_size")
        vector.prop(settings, "vector_orientation")
        row = vector.row(align=True)
        row.prop(settings, "vector_scale_denominator")
        row.operator("dimensions.sheet_sync_scale", text="", icon="CAMERA_DATA")
        vector.prop(settings, "vector_line_width_mm")
        vector.prop(settings, "vector_text_height_mm")
        vector.prop(settings, "vector_arrow_size_mm")
        sheet = vector.box()
        sheet.label(text="Drawing Sheet", icon="ALIGN_JUSTIFY")
        sheet.prop(settings, "sheet_border_enabled")
        sheet.prop(settings, "sheet_title_block_enabled")
        if settings.sheet_border_enabled or settings.sheet_title_block_enabled:
            sheet.prop(settings, "sheet_margin_mm")
        if settings.sheet_title_block_enabled:
            sheet.prop(settings, "sheet_title_block_width_mm")
            sheet.prop(settings, "sheet_title_block_height_mm")
            sheet.prop(settings, "sheet_drawing_title")
            sheet.prop(settings, "sheet_drawing_number")
            sheet.prop(settings, "sheet_revision")
            sheet.prop(settings, "sheet_author")
            row = sheet.row(align=True)
            row.prop(settings, "sheet_date")
            row.operator("dimensions.sheet_populate_date", text="", icon="TIME")
        actions = vector.row(align=True)
        actions.operator("dimensions.export_svg", icon="EXPORT")
        actions.operator("dimensions.export_pdf", icon="EXPORT")
        vector.label(text="Orthographic camera required", icon="CAMERA_DATA")


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
    CADDIM_UL_AnnotationManager,
    CADDIM_UL_AnnotationStyles,
    CADDIM_PT_MainPanel,
    CADDIM_PT_MeshSelection,
    CADDIM_PT_MeshSizeHUD,
    CADDIM_PT_GlobalSettings,
    CADDIM_PT_AnnotationManager,
    CADDIM_PT_GuidedRepair,
    CADDIM_PT_GlobalStyle,
    CADDIM_PT_AnnotationStyles,
    CADDIM_PT_ConstructionGuides,
    CADDIM_PT_Output,
    CADDIM_PT_SelectedDimension,
)
