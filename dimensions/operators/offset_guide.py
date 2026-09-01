"""Offset and centerline construction-guide operators."""

import bpy
from mathutils import Vector

from .. import messages
from ..anchors import set_anchor_from_snap
from ..collections import create_guide_object
from ..derived_guides import (
    bind_source_from_snap,
    centerline_preview,
    detach_derived_guide,
    offset_preview_line,
    resolve_derived_guide,
    source_geometry_from_snap,
    would_create_cycle,
)
from ..drawing import clear_guide_preview_state, set_guide_preview_state
from ..interaction import is_confirm_event, is_navigation_event, update_distance_text
from ..keymaps import modal_action_from_event
from ..snapping import copy_snap, find_nearest_snap_point, get_mouse_ray, project_mouse_to_plane
from ..snap_targets import handle_snap_target_event
from ..units import format_length, parse_distance_input
from ..properties import is_read_only_dimensions_object


def eligible_offset_source(snap):
    return source_geometry_from_snap(snap) is not None and (
        snap.get("type") in {"EDGE", "FACE", "GUIDE"}
    )


class DIMENSIONS_OT_CreateDerivedGuide(bpy.types.Operator):
    bl_idname = "dimensions.create_derived_guide"
    bl_label = "Add Offset or Centerline Guide"
    bl_options = {"REGISTER", "UNDO"}

    mode: bpy.props.EnumProperty(
        name="Mode",
        items=[
            ("OFFSET", "Offset", "Offset from one edge, guide, or face"),
            ("CENTERLINE", "Centerline", "Place midway between two parallel sources"),
        ],
        default="OFFSET",
        options={"SKIP_SAVE"},
    )

    def invoke(self, context, _event):
        if context.area is None or context.area.type != "VIEW_3D" or context.mode != "OBJECT":
            self.report(messages.WARNING, messages.GUIDE_REQUIRE_OBJECT_MODE)
            return {"CANCELLED"}
        self.state = "SOURCE_A"
        self.source_a_snap = None
        self.source_b_snap = None
        self.hover_snap = None
        self.distance_text = ""
        self.distance_input_valid = True
        self.preview_distance = 1.0
        self.offset_side = 1
        self.derived_direction = Vector((0.0, 1.0, 0.0))
        context.window_manager.modal_handler_add(self)
        self._update_preview(context)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if context.area is None or context.area.type != "VIEW_3D":
            clear_guide_preview_state()
            return {"CANCELLED"}
        if handle_snap_target_event(context, event):
            return {"RUNNING_MODAL"}
        if modal_action_from_event(event) == "FLIP_OFFSET" and self.state == "OFFSET":
            self.offset_side *= -1
            self._update_preview(context)
            return {"RUNNING_MODAL"}
        if event.type == "MOUSEMOVE":
            if self.state in {"SOURCE_A", "SOURCE_B"}:
                snap = find_nearest_snap_point(
                    context, event.mouse_region_x, event.mouse_region_y,
                    include_free=False,
                )
                self.hover_snap = copy_snap(snap) if eligible_offset_source(snap) else None
            else:
                self._update_mouse_offset(context, event.mouse_region_x, event.mouse_region_y)
            self._update_preview(context)
            return {"RUNNING_MODAL"}
        if self.state == "OFFSET":
            text, handled = update_distance_text(self.distance_text, event)
            if handled:
                self.distance_text = text
                self._update_preview(context)
                return {"RUNNING_MODAL"}
        if event.type == "LEFTMOUSE" and event.value == "PRESS":
            return self._accept(context)
        if is_confirm_event(event):
            return self._accept(context)
        if event.type in {"ESC", "RIGHTMOUSE"} and event.value == "PRESS":
            clear_guide_preview_state()
            return {"CANCELLED"}
        if is_navigation_event(event):
            return {"PASS_THROUGH"}
        return {"RUNNING_MODAL"}

    def cancel(self, _context):
        clear_guide_preview_state()

    def _accept(self, context):
        if self.state == "SOURCE_A":
            if self.hover_snap is None:
                return {"RUNNING_MODAL"}
            self.source_a_snap = copy_snap(self.hover_snap)
            self.hover_snap = None
            self._set_initial_direction(context)
            self.state = "SOURCE_B" if self.mode == "CENTERLINE" else "OFFSET"
            self._update_preview(context)
            return {"RUNNING_MODAL"}
        if self.state == "SOURCE_B":
            if self.hover_snap is None:
                return {"RUNNING_MODAL"}
            self.source_b_snap = copy_snap(self.hover_snap)
            if self._preview_line(context) is None:
                self.report(messages.WARNING, messages.DERIVED_GUIDE_PARALLEL_REQUIRED)
                self.source_b_snap = None
                return {"RUNNING_MODAL"}
            self.state = "CONFIRM"
            self._update_preview(context)
            return {"RUNNING_MODAL"}
        if self._preview_line(context) is None:
            if self.distance_text:
                self.report(messages.WARNING, messages.invalid_distance(self.distance_text))
            return {"RUNNING_MODAL"}
        self._commit(context)
        clear_guide_preview_state()
        return {"FINISHED"}

    def _distance(self, context):
        if not self.distance_text.strip():
            self.distance_input_valid = True
            return self.preview_distance
        try:
            value = abs(parse_distance_input(context, self.distance_text))
        except (TypeError, ValueError):
            self.distance_input_valid = False
            return None
        self.distance_input_valid = value > 1e-8
        return value if self.distance_input_valid else None

    def _set_initial_direction(self, context):
        geometry = source_geometry_from_snap(self.source_a_snap)
        if geometry["kind"] == "PLANE":
            normal = geometry["normal"]
            direction = normal.cross(Vector((0.0, 0.0, 1.0)))
            if direction.length < 1e-6:
                direction = normal.cross(Vector((0.0, 1.0, 0.0)))
            self.derived_direction = direction.normalized()
            return
        _origin, view_direction = get_mouse_ray(context, 0.0, 0.0)
        direction = geometry["direction"].cross(view_direction)
        if direction.length < 1e-6:
            direction = geometry["direction"].cross(Vector((0.0, 0.0, 1.0)))
        self.derived_direction = direction.normalized()

    def _update_mouse_offset(self, context, mouse_x, mouse_y):
        geometry = source_geometry_from_snap(self.source_a_snap)
        point = project_mouse_to_plane(context, mouse_x, mouse_y, geometry["origin"])
        if point is None:
            return
        if geometry["kind"] == "PLANE":
            signed = (point - geometry["origin"]).dot(geometry["normal"])
            if abs(signed) > 1e-6:
                self.preview_distance = abs(signed)
                self.offset_side = 1 if signed >= 0.0 else -1
            return
        delta = point - geometry["origin"]
        perpendicular = delta - geometry["direction"] * delta.dot(geometry["direction"])
        if perpendicular.length > 1e-6:
            self.preview_distance = perpendicular.length
            self.offset_side = 1 if perpendicular.dot(self.derived_direction) >= 0.0 else -1

    def _preview_line(self, context):
        first = source_geometry_from_snap(self.source_a_snap)
        if first is None:
            return None
        if self.mode == "CENTERLINE":
            second = source_geometry_from_snap(self.source_b_snap)
            return None if second is None else centerline_preview(first, second, self.derived_direction)
        distance = self._distance(context)
        return None if distance is None else offset_preview_line(
            first, distance, self.offset_side, self.derived_direction,
        )

    def _commit(self, context):
        line = self._preview_line(context)
        obj = create_guide_object(context, "GUIDE Derived Centerline" if self.mode == "CENTERLINE" else "GUIDE Derived Offset")
        props = obj.guide_props
        props.derived = True
        props.derivation_mode = self.mode
        props.derived_direction = tuple(self.derived_direction)
        props.offset_distance = 0.0 if self.mode == "CENTERLINE" else self._distance(context)
        props.offset_side = self.offset_side
        bind_source_from_snap(props.source_a, self.source_a_snap)
        if self.mode == "CENTERLINE":
            bind_source_from_snap(props.source_b, self.source_b_snap)
        props.last_resolved_origin = tuple(line[0])
        props.last_resolved_direction = tuple(line[1])
        obj.location = line[0]
        for selected in context.selected_objects:
            selected.select_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        self.report(messages.INFO, messages.CREATED_DERIVED_GUIDE)

    def _update_preview(self, context):
        state = {
            "state": self.state,
            "distance_text": self.distance_text,
            "distance_input_valid": self.distance_input_valid,
            "axis": "ALIGNED",
            "derived_guide": self.mode,
            "offset_side": self.offset_side,
        }
        if self.hover_snap is not None:
            state.update({
                "hover_screen": self.hover_snap["screen_co"],
                "hover_type": self.hover_snap.get("type", "WORLD"),
                "hover_label": self.hover_snap.get("label", "Source"),
            })
        line = self._preview_line(context)
        if line is not None:
            state["start_world"] = line[0]
            state["end_world"] = line[0] + line[1]
            if self.mode == "OFFSET":
                state["derived_label"] = format_length(context, self._distance(context), 3)
        set_guide_preview_state(state)


class DIMENSIONS_OT_DetachDerivedGuide(bpy.types.Operator):
    bl_idname = "dimensions.detach_derived_guide"
    bl_label = "Detach Derived Guide"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        obj = context.view_layer.objects.active
        if obj is None or is_read_only_dimensions_object(obj) or not detach_derived_guide(obj):
            self.report(messages.WARNING, messages.SELECT_DERIVED_GUIDE)
            return {"CANCELLED"}
        self.report(messages.INFO, messages.DETACHED_DERIVED_GUIDE)
        return {"FINISHED"}


class DIMENSIONS_OT_RepairDerivedGuideSource(bpy.types.Operator):
    bl_idname = "dimensions.repair_derived_guide_source"
    bl_label = "Reattach Derived Guide Source"
    bl_options = {"REGISTER", "UNDO"}

    source_slot: bpy.props.EnumProperty(
        name="Source",
        items=[
            ("A", "Source A", "Replace the first source"),
            ("B", "Source B", "Replace the second source"),
            ("PIVOT", "Origin / Pivot", "Replace the angular pivot or spacing origin"),
            ("SPACING_END", "Spacing End", "Replace the distribute-mode end reference"),
        ],
        default="A",
    )

    def invoke(self, context, _event):
        obj = context.view_layer.objects.active
        if (
            obj is None
            or not getattr(getattr(obj, "guide_props", None), "derived", False)
            or is_read_only_dimensions_object(obj)
        ):
            self.report(messages.WARNING, messages.SELECT_DERIVED_GUIDE)
            return {"CANCELLED"}
        self.guide = obj
        self.hover_snap = None
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type == "MOUSEMOVE":
            repairs_anchor = self.source_slot in {"PIVOT", "SPACING_END"}
            snap = find_nearest_snap_point(
                context, event.mouse_region_x, event.mouse_region_y,
                include_free=repairs_anchor,
            )
            self.hover_snap = (
                copy_snap(snap)
                if snap is not None and (repairs_anchor or eligible_offset_source(snap))
                else None
            )
            set_guide_preview_state({
                "state": "REPAIR_DERIVED_GUIDE",
                "hover_screen": None if self.hover_snap is None else self.hover_snap["screen_co"],
                "hover_type": "WORLD" if self.hover_snap is None else self.hover_snap.get("type", "WORLD"),
            })
            return {"RUNNING_MODAL"}
        if event.type == "LEFTMOUSE" and event.value == "PRESS" and self.hover_snap is not None:
            if self.source_slot in {"PIVOT", "SPACING_END"}:
                anchor = (
                    self.guide.guide_props.construction_pivot
                    if self.source_slot == "PIVOT"
                    else self.guide.guide_props.spacing_end
                )
                set_anchor_from_snap(anchor, self.hover_snap)
                resolve_derived_guide(self.guide)
                clear_guide_preview_state()
                self.report(messages.INFO, messages.REATTACHED_DERIVED_GUIDE_SOURCE)
                return {"FINISHED"}
            source_guide = self.hover_snap.get("guide_object")
            if source_guide is not None and would_create_cycle(self.guide, (source_guide,)):
                self.report(messages.WARNING, messages.DERIVED_GUIDE_CYCLE_REFUSED)
                return {"RUNNING_MODAL"}
            source = self.guide.guide_props.source_a if self.source_slot == "A" else self.guide.guide_props.source_b
            bind_source_from_snap(source, self.hover_snap)
            resolve_derived_guide(self.guide)
            clear_guide_preview_state()
            self.report(messages.INFO, messages.REATTACHED_DERIVED_GUIDE_SOURCE)
            return {"FINISHED"}
        if event.type in {"ESC", "RIGHTMOUSE"} and event.value == "PRESS":
            clear_guide_preview_state()
            return {"CANCELLED"}
        return {"PASS_THROUGH"} if is_navigation_event(event) else {"RUNNING_MODAL"}


classes = (
    DIMENSIONS_OT_CreateDerivedGuide,
    DIMENSIONS_OT_DetachDerivedGuide,
    DIMENSIONS_OT_RepairDerivedGuideSource,
)
