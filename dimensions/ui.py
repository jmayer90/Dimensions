import bpy

from .annotation_manager import annotation_is_hidden, manager_item_matches
from .constants import SIDEBAR_CATEGORY
from .preferences import ADDON_ID, get_preferences
from .properties import (
    is_dimension_object,
    is_guide_object,
    is_read_only_dimensions_object,
    resolve_dimension_style,
)
from .units import format_area, format_length, get_configured_unit_style


class CADDIM_PT_PanelBase:
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = SIDEBAR_CATEGORY


class CADDIM_PT_MainPanel(CADDIM_PT_PanelBase, bpy.types.Panel):
    bl_label = "Dimensions"
    bl_idname = "CADDIM_PT_main_panel"

    def draw(self, context):
        tools = self.layout.column(align=True)
        tools.enabled = context.mode in {"OBJECT", "EDIT_MESH"}
        row = tools.row(align=True)
        row.operator("dimensions.create_dimension", text="Dimension", icon="DRIVER_DISTANCE")
        chain = row.operator("dimensions.create_dimension", text="Chain", icon="LINKED")
        chain.chain = True
        row = tools.row(align=True)
        row.operator("dimensions.create_angle", text="Angle", icon="DRIVER_ROTATIONAL_DIFFERENCE")
        row.operator("dimensions.create_area", text="Area", icon="FACESEL")
        tools.operator("dimensions.measure", text="Measure", icon="ARROW_LEFTRIGHT")

        direction = self.layout.column(align=True)
        direction.label(text="Direction")
        direction_buttons = direction.row(align=True)
        preferences = get_preferences(context)
        for value, label in (("ALIGNED", "Auto"), ("X", "X"), ("Y", "Y"), ("Z", "Z")):
            direction_buttons.prop_enum(preferences, "default_axis_mode", value, text=label)


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
        layout.operator("dimensions.area_selected_faces", text="Area from Selected Faces", icon="FACESEL")
        layout.operator(
            "dimensions.rebind_area_from_selection",
            text="Apply Faces to Selected Area",
            icon="FILE_REFRESH",
        )


class CADDIM_PT_ConstructionGuides(CADDIM_PT_PanelBase, bpy.types.Panel):
    bl_label = "Construction"
    bl_idname = "CADDIM_PT_construction_guides"
    bl_parent_id = CADDIM_PT_MainPanel.bl_idname
    bl_order = 1

    def draw(self, context):
        layout = self.layout
        settings = context.scene.dimensions_settings
        tools = layout.column(align=True)
        tools.enabled = context.mode in {"OBJECT", "EDIT_MESH"}
        row = tools.row(align=True)
        row.operator("dimensions.create_guide", text="Guide Line", icon="EMPTY_SINGLE_ARROW")
        row.operator("dimensions.create_offset_guide", text="Offset Guide", icon="MOD_OFFSET")
        row = tools.row(align=True)
        point = row.operator("dimensions.create_guide_point", text="Guide Point", icon="EMPTY_AXIS")
        point.placement_mode = "DIRECT"
        center = row.operator("dimensions.create_guide_point", text="At Selection", icon="PIVOT_MEDIAN")
        center.placement_mode = "SELECTION"
        row = tools.row(align=True)
        three = row.operator("dimensions.create_guide_plane", text="Plane: 3 Points", icon="MESH_GRID")
        three.definition = "THREE_POINTS"
        face = row.operator("dimensions.create_guide_plane", text="Plane: Face", icon="FACESEL")
        face.definition = "FACE"

        display = layout.column()
        display.use_property_split = True
        display.use_property_decorate = False
        display.prop(settings, "show_construction_guides")
        display.prop(settings, "guide_color")
        display.prop(settings, "guide_line_width")
        clear = layout.row(align=True)
        clear.operator("dimensions.clear_guides", text="Clear Guides", icon="TRASH")
        clear.operator("dimensions.clear_measurements", text="Clear Measurements", icon="TRASH")


_MANAGER_KIND_ICONS = {
    "LINEAR": "DRIVER_DISTANCE",
    "ANGLE": "DRIVER_ROTATIONAL_DIFFERENCE",
    "AREA": "FACESEL",
    "MEASUREMENT": "ARROW_LEFTRIGHT",
    "GUIDE": "EMPTY_SINGLE_ARROW",
    "POINT": "EMPTY_AXIS",
    "PLANE": "MESH_GRID",
}

_MANAGER_KIND_FILTERS = (
    ("linear", "Linear"), ("angle", "Angle"), ("area", "Area"), ("measurement", "Measure"),
    ("guide", "Line"), ("point", "Point"), ("plane", "Plane"),
)


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
        if item.state in {"NEEDS_REPAIR", "FALLBACK"}:
            row.label(text="", icon="ERROR" if item.state == "NEEDS_REPAIR" else "QUESTION")
        elif item.state == "CAPTURED":
            row.label(text="", icon="REC")
        visibility = row.operator(
            "dimensions.manager_toggle_visibility", text="",
            icon="HIDE_ON" if annotation_is_hidden(obj) else "HIDE_OFF",
        )
        visibility.object_name = obj.name

    def draw_filter(self, _context, _layout):
        # Search and filters are drawn in the panel itself so they are always visible.
        return

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
        search = layout.row(align=True)
        search.prop(settings, "annotation_manager_search", text="", icon="VIEWZOOM")
        search.prop(
            settings, "annotation_manager_show_filters", text="", icon="FILTER",
        )
        if settings.annotation_manager_show_filters:
            filters = layout.box().column(align=True)
            filters.label(text="Show Types")
            grid = filters.grid_flow(row_major=True, columns=4, even_columns=True, align=True)
            for name, label in _MANAGER_KIND_FILTERS:
                grid.prop(settings, f"annotation_manager_kind_{name}", text=label, toggle=True)
            filters.separator()
            filters.label(text="Show States")
            states = filters.grid_flow(row_major=True, columns=2, even_columns=True, align=True)
            states.prop(settings, "annotation_manager_state_live", text="Live", toggle=True)
            states.prop(settings, "annotation_manager_state_captured", text="Captured", toggle=True)
            states.prop(settings, "annotation_manager_state_fallback", text="Fallback", toggle=True)
            states.prop(settings, "annotation_manager_state_needs_repair", text="Needs Repair", toggle=True)
            filters.separator()
            filters.prop(settings, "annotation_manager_references_active", toggle=True)
            if settings.annotation_manager_references_active:
                filters.prop(settings, "annotation_manager_reference_object", text="")
        layout.template_list(
            "CADDIM_UL_AnnotationManager", "", settings, "annotation_manager_items",
            settings, "active_annotation_manager_index", rows=4,
        )
        if not settings.annotation_manager_items:
            layout.label(text="No annotations or guides in this scene")
            return
        index = settings.active_annotation_manager_index
        if 0 <= index < len(settings.annotation_manager_items):
            item = settings.annotation_manager_items[index]
            managed = item.annotation
            if managed is not None:
                detail = layout.box()
                detail.label(text=item.display_value, icon=_MANAGER_KIND_ICONS.get(item.kind, "OBJECT_DATA"))
                if is_dimension_object(managed):
                    detail.label(text=item.state.replace("_", " ").title())
                actions = detail.row(align=True)
                select = actions.operator("dimensions.manager_select", text="Select")
                select.object_name = managed.name
                frame = actions.operator("dimensions.manager_jump_to", text="Frame")
                frame.object_name = managed.name
                visibility = actions.operator(
                    "dimensions.manager_toggle_visibility",
                    text="Show" if annotation_is_hidden(managed) else "Hide",
                )
                visibility.object_name = managed.name
                edits = detail.row(align=True)
                edits.enabled = not is_read_only_dimensions_object(managed)
                rename = edits.operator("dimensions.manager_rename", text="Rename")
                rename.object_name = managed.name
                delete = edits.operator("dimensions.manager_delete", text="Delete")
                delete.object_name = managed.name
                if item.state in {"NEEDS_REPAIR", "FALLBACK"}:
                    repair = detail.operator("dimensions.manager_repair_entry", text="Show Sources", icon="TOOL_SETTINGS")
                    repair.object_name = managed.name
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
        styles = layout.row(align=True)
        styles.operator("dimensions.manager_bulk_style", text="Apply Style", icon="BRUSH_DATA")
        styles.operator("dimensions.manager_bulk_reset_style", text="Reset Style", icon="LOOP_BACK")
        layout.operator("dimensions.manager_bulk_delete", text="Delete", icon="TRASH")


class CADDIM_PT_GuidedRepair(CADDIM_PT_PanelBase, bpy.types.Panel):
    bl_label = "Guided Repair"
    bl_idname = "CADDIM_PT_guided_repair"
    bl_parent_id = CADDIM_PT_MainPanel.bl_idname
    bl_order = 3

    # Polls and redraws read the state recorded by scene sync. The live candidate
    # search scans the whole source mesh, so it runs only when the user acts.
    @classmethod
    def poll(cls, context):
        from .repair import stored_repair_issues

        active = context.view_layer.objects.active
        return is_dimension_object(active) and bool(stored_repair_issues(active))

    def draw(self, context):
        from .repair import stored_repair_issues

        layout = self.layout
        annotation = context.view_layer.objects.active
        issues = stored_repair_issues(annotation)
        read_only = is_read_only_dimensions_object(annotation)
        layout.label(text=annotation.name, icon="ERROR")
        for issue in issues:
            box = layout.box()
            state = "Fallback" if issue["status"] == "BY_FALLBACK" else "Unresolvable"
            box.label(text=f"{issue['type'].title()}: {state}")
            box.label(text=f"Source: {issue['source_name']}")
            frame = box.operator("dimensions.repair_frame_issue", text="Frame Last Known Position", icon="VIEWZOOM")
            frame.object_name = annotation.name
            if issue["status"] == "BY_FALLBACK":
                box.label(text="Accept rebinds it to the nearest match on this source", icon="QUESTION")
            actions = box.row(align=True)
            actions.enabled = not read_only
            if issue["type"] == "AREA":
                pick = actions.operator("dimensions.repair_pick_area_source", text="Pick Face", icon="EYEDROPPER")
                pick.object_name = annotation.name
            else:
                pick = actions.operator("dimensions.reattach_anchor", text="Pick Point", icon="EYEDROPPER")
                pick.anchor_name = issue["anchor_name"]
                if issue["status"] == "UNRESOLVABLE":
                    convert = actions.operator("dimensions.repair_convert_world", text="Use World Point", icon="EMPTY_AXIS")
                    convert.object_name = annotation.name
                    convert.anchor_name = issue["anchor_name"]
        confirm = layout.column(align=True)
        # Only a source that still exists can offer a suggested match.
        confirm.enabled = not read_only and any(issue["status"] == "BY_FALLBACK" for issue in issues)
        accept = confirm.operator("dimensions.repair_accept_suggestion", text="Accept Suggested Repair", icon="CHECKMARK")
        accept.object_name = annotation.name
        bulk = confirm.operator("dimensions.repair_bulk_cause", text="Repair Matching Cause", icon="DUPLICATE")
        bulk.object_name = annotation.name
        if read_only:
            layout.label(text="Linked annotation: make local to repair", icon="LOCKED")


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
    if isinstance(value, float):
        # Single-precision properties would otherwise print as 1.600000023841858.
        value = f"{round(value, 4):g}"
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


_CONSTRUCTION_HINTS = {
    "GUIDE": "Runs along the object's X axis. Move with G, rotate with R",
    "POINT": "Move with G like any object",
    "PLANE": "Move with G, rotate with R, scale with S",
    "MEASUREMENT": "Move with G to shift both ends",
}


def _draw_construction_object(layout, context, obj):
    props = obj.guide_props
    kind = getattr(props, "kind", "GUIDE")
    layout.prop(obj, "name", text="Name")
    if kind == "PLANE":
        layout.prop(props, "plane_extent")
        layout.prop(props, "plane_spacing")
    elif kind == "MEASUREMENT":
        from .construction import construction_segment_world

        segment = construction_segment_world(obj)
        if segment is not None:
            precision = context.scene.dimensions_settings.precision
            layout.label(text=f"Length: {format_length(context, (segment[1] - segment[0]).length, precision)}")
    layout.prop(props, "visible")
    layout.label(text=_CONSTRUCTION_HINTS.get(kind, ""), icon="INFO")


class CADDIM_PT_SelectedDimension(CADDIM_PT_PanelBase, bpy.types.Panel):
    bl_label = "Selected"
    bl_idname = "CADDIM_PT_selected_dimension"
    bl_parent_id = CADDIM_PT_MainPanel.bl_idname
    bl_order = 4

    def draw(self, context):
        layout = self.layout
        active_object = context.view_layer.objects.active
        layout.use_property_split = True
        layout.use_property_decorate = False

        if is_guide_object(active_object):
            if is_read_only_dimensions_object(active_object):
                layout.label(text="Linked guide: read-only", icon="LOCKED")
                return
            _draw_construction_object(layout, context, active_object)
            return
        if not is_dimension_object(active_object):
            layout.label(text="Select a dimension or guide to edit it here.")
            return

        props = active_object.dimension_props
        if is_read_only_dimensions_object(active_object):
            source = "Library override" if active_object.override_library is not None else "Linked annotation"
            layout.label(text=f"{source}: read-only", icon="LOCKED")
            return
        layout.prop(active_object, "name", text="Name")
        annotation_kind = getattr(props, "annotation_kind", "LINEAR")
        if annotation_kind == "LINEAR":
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
        layout.prop(props, "visible")

        style_box = layout.box()
        style_box.label(text=f"Style: {props.style_name or 'Scene Defaults'}")
        resolved_style = resolve_dimension_style(context.scene.dimensions_settings, props)
        for property_name, label in (
            ("color", None), ("selected_color", None), ("line_width", None), ("text_size", None),
            ("precision", None), ("arrow_size", None), ("start_end_style", None), ("end_end_style", None),
            ("extension_gap", None), ("extension_overshoot", None), ("unit_style", None),
            ("secondary_unit_style", None), ("secondary_precision", None), ("dual_unit_arrangement", None),
            ("label_orientation", None), ("label_line_mode", None), ("value_prefix", "Prefix"),
            ("value_suffix", "Suffix"), ("tolerance", None),
        ):
            _draw_style_override(style_box, props, resolved_style, property_name, label)
        if props.override_tolerance and props.tolerance_mode == "SYMMETRIC":
            style_box.prop(props, "tolerance_upper", text="Plus / Minus")
        elif props.override_tolerance and props.tolerance_mode == "DEVIATION":
            style_box.prop(props, "tolerance_upper")
            style_box.prop(props, "tolerance_lower")
        style_actions = style_box.row(align=True)
        style_actions.operator("dimensions.clear_annotation_style_overrides", icon="BRUSH_DATA")
        style_actions.operator("dimensions.reset_style_to_global", icon="LOOP_BACK")
        style_actions.operator("dimensions.copy_style_to_global", icon="DUPLICATE")

        if annotation_kind != "LINEAR":
            return
        for label, anchor, anchor_name in (("Start", props.start, "START"), ("End", props.end, "END")):
            box = layout.box()
            box.label(text=f"{label} Anchor")
            box.prop(anchor, "target_object", text="Object")
            row = box.row(align=True)
            row.label(text=_anchor_description(anchor))
            pick = row.operator("dimensions.reattach_anchor", text="Repick", icon="EYEDROPPER")
            pick.anchor_name = anchor_name


class CADDIM_PT_Output(CADDIM_PT_PanelBase, bpy.types.Panel):
    bl_label = "Output"
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
        grease_pencil = layout.box()
        grease_pencil.label(text="Grease Pencil", icon="GREASEPENCIL")
        grease_pencil.prop(settings, "output_sizing_mode")
        if settings.output_sizing_mode == "CAMERA":
            grease_pencil.prop(settings, "output_line_width", text="Line Width")
            grease_pencil.prop(settings, "output_text_height", text="Text Height")
            grease_pencil.prop(settings, "output_arrow_size", text="Arrow Size")
        else:
            grease_pencil.prop(settings, "output_world_line_width", text="Line Width")
            grease_pencil.prop(settings, "output_world_text_height", text="Text Height")
            grease_pencil.prop(settings, "output_world_arrow_size", text="Arrow Size")
        grease_pencil.operator("dimensions.generate_output", icon="GREASEPENCIL")
        grease_pencil.label(text="Rebuild replaces hand edits", icon="ERROR")

        vector = layout.box()
        vector.label(text="Scale-Correct SVG / PDF", icon="FILE_IMAGE")
        vector.prop(settings, "vector_paper_size")
        vector.prop(settings, "vector_orientation")
        vector.prop(settings, "vector_scale_denominator", text="Scale 1:N")
        vector.operator("dimensions.sheet_sync_scale", text="Fit Scale to Camera", icon="CAMERA_DATA")
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
            sheet.prop(settings, "sheet_title_block_width_mm", text="Block Width")
            sheet.prop(settings, "sheet_title_block_height_mm", text="Block Height")
            sheet.prop(settings, "sheet_drawing_title")
            sheet.prop(settings, "sheet_drawing_number", text="Drawing No.")
            sheet.prop(settings, "sheet_revision")
            sheet.prop(settings, "sheet_author")
            sheet.prop(settings, "sheet_date")
            sheet.operator("dimensions.sheet_populate_date", text="Today's Date", icon="TIME")
        actions = vector.row(align=True)
        actions.operator("dimensions.export_svg", icon="EXPORT")
        actions.operator("dimensions.export_pdf", icon="EXPORT")
        vector.label(text="Orthographic camera required", icon="CAMERA_DATA")


class CADDIM_PT_SnapTargets(CADDIM_PT_PanelBase, bpy.types.Panel):
    bl_label = "Snap Targets"
    bl_idname = "CADDIM_PT_snap_targets"
    bl_parent_id = CADDIM_PT_MainPanel.bl_idname
    bl_order = 6
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        from .snap_targets import draw_snap_target_controls

        layout = self.layout
        settings = context.scene.dimensions_settings
        preferences = get_preferences(context)
        layout.prop(settings, "use_snap_target_override", text="Scene Override")
        source = settings if settings.use_snap_target_override else preferences
        layout.prop(
            source,
            "snap_pixel_radius" if settings.use_snap_target_override else "snap_pixel_threshold",
            text="Snap Radius",
        )
        draw_snap_target_controls(layout, source)


class CADDIM_PT_GlobalSettings(CADDIM_PT_PanelBase, bpy.types.Panel):
    bl_label = "Global Dimension Settings"
    bl_idname = "CADDIM_PT_global_settings"
    bl_parent_id = CADDIM_PT_MainPanel.bl_idname
    bl_order = 7
    bl_options = {"DEFAULT_CLOSED"}

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


class CADDIM_PT_GlobalStyle(CADDIM_PT_PanelBase, bpy.types.Panel):
    bl_label = "Global Dimension Style"
    bl_idname = "CADDIM_PT_global_style"
    bl_parent_id = CADDIM_PT_MainPanel.bl_idname
    bl_order = 8
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


class CADDIM_UL_AnnotationStyles(bpy.types.UIList):
    def draw_item(self, _context, layout, _data, item, _icon, _active_data, _active_propname, _index):
        layout.label(text=item.name, icon="BRUSH_DATA")


class CADDIM_PT_AnnotationStyles(CADDIM_PT_PanelBase, bpy.types.Panel):
    bl_label = "Named Annotation Styles"
    bl_idname = "CADDIM_PT_annotation_styles"
    bl_parent_id = CADDIM_PT_MainPanel.bl_idname
    bl_order = 9
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


class CADDIM_PT_MeshSizeHUD(CADDIM_PT_PanelBase, bpy.types.Panel):
    bl_label = "Selected Mesh Size HUD"
    bl_idname = "CADDIM_PT_mesh_size_hud"
    bl_parent_id = CADDIM_PT_MainPanel.bl_idname
    bl_order = 10
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


def _anchor_description(anchor):
    """Say in plain words what an anchor follows."""
    anchor_type = getattr(anchor, "anchor_type", "VERTEX")
    if anchor_type == "WORLD":
        return "Fixed point in space"
    if anchor_type == "OBJECT_POINT":
        guide = getattr(anchor.target_object, "guide_props", None)
        kind = guide.kind if guide is not None and guide.enabled else None
        return {"POINT": "Follows a guide point", "GUIDE": "Follows a guide line"}.get(kind, "Point on the object")
    if anchor.vertex_index < 0:
        return "Not attached"
    return "Follows a vertex"


classes = (
    CADDIM_UL_AnnotationManager,
    CADDIM_UL_AnnotationStyles,
    CADDIM_PT_MainPanel,
    CADDIM_PT_MeshSelection,
    CADDIM_PT_ConstructionGuides,
    CADDIM_PT_AnnotationManager,
    CADDIM_PT_GuidedRepair,
    CADDIM_PT_SelectedDimension,
    CADDIM_PT_Output,
    CADDIM_PT_SnapTargets,
    CADDIM_PT_GlobalSettings,
    CADDIM_PT_GlobalStyle,
    CADDIM_PT_AnnotationStyles,
    CADDIM_PT_MeshSizeHUD,
)
