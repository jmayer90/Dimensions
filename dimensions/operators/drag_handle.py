"""Direct selected-annotation presentation handle manipulation."""

from math import cos, sin

import bpy
from mathutils import Vector

from .. import messages
from ..anchors import resolve_anchor
from ..angle_binding import resolve_angle_source
from ..area_binding import evaluate_area_binding
from ..circle_binding import circle_geometry, circle_value
from ..dimension_geometry import get_dimension_world_geometry
from ..drawing import clear_preview_state, set_preview_state
from ..interaction import axis_from_event, is_confirm_event, update_distance_text
from ..manipulation import (
    angle_radius_from_world,
    apply_area_label_position,
    apply_circle_label_position,
    linear_offset_from_world,
)
from ..modal_state import HandleManipulationState
from ..properties import is_dimension_object, is_read_only_dimensions_object
from ..snapping import find_nearest_snap_point, has_view3d_window_region
from ..units import parse_distance_input
from .create_area import _axis_mouse_world, _constrained_label_world


class DIMENSIONS_OT_DragAnnotationHandle(bpy.types.Operator):
    bl_idname = "dimensions.drag_annotation_handle"
    bl_label = "Adjust Annotation Handle"
    bl_description = "Adjust annotation presentation with the shared constraint and numeric-input contract"
    bl_options = {"REGISTER", "UNDO"}

    object_name: bpy.props.StringProperty()
    handle_kind: bpy.props.EnumProperty(items=[
        ("LINEAR_OFFSET", "Linear Offset", "Adjust the dimension-line offset"),
        ("ANGLE_RADIUS", "Angle Radius", "Adjust the angle arc radius"),
        ("AREA_LABEL", "Area Label", "Adjust the area label position"),
        ("CIRCLE_LABEL", "Circular Label", "Adjust the circular leader and label position"),
    ])

    def invoke(self, context, _event):
        if not has_view3d_window_region(context):
            self.report(messages.WARNING, messages.RUN_FROM_3D_VIEW)
            return {"CANCELLED"}
        annotation = context.scene.objects.get(self.object_name)
        if not is_dimension_object(annotation) or annotation != context.view_layer.objects.active:
            self.report(messages.WARNING, messages.SELECT_DIMENSION_FIRST)
            return {"CANCELLED"}
        if is_read_only_dimensions_object(annotation):
            self.report(messages.WARNING, messages.MANAGER_LINKED_READ_ONLY)
            return {"CANCELLED"}
        expected = {
            "LINEAR": "LINEAR_OFFSET",
            "ANGLE": "ANGLE_RADIUS",
            "AREA": "AREA_LABEL",
            "CIRCLE": "CIRCLE_LABEL",
        }.get(annotation.dimension_props.annotation_kind)
        if self.handle_kind != expected:
            self.report(messages.WARNING, messages.HANDLE_NO_LONGER_AVAILABLE)
            return {"CANCELLED"}
        self.annotation_name = annotation.name
        self.state = HandleManipulationState()
        self.raw_world = self._current_world(annotation)
        self.candidate_world = None
        self.candidate_value = self._current_value(annotation)
        self._update_candidate(context)
        self._update_preview(context)
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        annotation = bpy.data.objects.get(self.annotation_name)
        if annotation is None or not has_view3d_window_region(context):
            clear_preview_state()
            return {"CANCELLED"}
        axis = axis_from_event(event)
        if axis is not None:
            self.state.set_axis(axis)
            self._update_candidate(context)
            self._update_preview(context)
            return {"RUNNING_MODAL"}
        text, handled = update_distance_text(self.state.numeric_text, event)
        if handled:
            valid = True
            if text.strip():
                try:
                    parse_distance_input(context, text)
                except (TypeError, ValueError):
                    valid = False
            self.state.set_numeric_text(text, valid)
            self._update_candidate(context)
            self._update_preview(context)
            return {"RUNNING_MODAL"}
        if event.type == "MOUSEMOVE":
            self.raw_world = self._mouse_world(context, annotation, event)
            self._update_candidate(context)
            self._update_preview(context)
            return {"RUNNING_MODAL"}
        if (
            event.type == "LEFTMOUSE" and event.value == "PRESS"
        ) or is_confirm_event(event):
            if self.state.confirm() == "NUMERIC_INVALID":
                self.report(messages.WARNING, messages.invalid_distance(self.state.numeric_text))
                return {"RUNNING_MODAL"}
            if self.candidate_value is None and self.candidate_world is None:
                return {"RUNNING_MODAL"}
            self._commit(annotation)
            clear_preview_state()
            self.report(messages.INFO, messages.adjusted_handle(self.handle_kind))
            return {"FINISHED"}
        if event.type == "ESC" and event.value == "PRESS":
            if self.state.escape() == "NUMERIC_CLEARED":
                self._update_candidate(context)
                self._update_preview(context)
                return {"RUNNING_MODAL"}
            clear_preview_state()
            return {"CANCELLED"}
        if event.type == "RIGHTMOUSE" and event.value == "PRESS":
            self.state.cancel()
            clear_preview_state()
            return {"CANCELLED"}
        if event.type in {"MIDDLEMOUSE", "WHEELUPMOUSE", "WHEELDOWNMOUSE"}:
            return {"PASS_THROUGH"}
        return {"RUNNING_MODAL"}

    def cancel(self, _context):
        clear_preview_state()

    def _current_value(self, annotation):
        props = annotation.dimension_props
        if self.handle_kind == "LINEAR_OFFSET":
            return props.offset_distance
        if self.handle_kind == "ANGLE_RADIUS":
            return props.angle_radius
        return None

    def _current_world(self, annotation):
        props = annotation.dimension_props
        if self.handle_kind == "AREA_LABEL":
            return resolve_anchor(props.end) + Vector(props.presentation_offset)
        if self.handle_kind == "CIRCLE_LABEL":
            fit = circle_geometry(props)
            if fit is None:
                return None
            direction = fit["axis_u"] * cos(props.circle_leader_angle) + fit["axis_v"] * sin(props.circle_leader_angle)
            distance = props.circle_label_distance if props.circle_label_distance > 1e-6 else fit["radius"] * 1.35
            return fit["center"] + direction * distance + Vector(props.presentation_offset)
        if self.handle_kind == "ANGLE_RADIUS":
            source = resolve_angle_source(props)
            if source is None:
                return None
            direction = Vector(source["start"]) - Vector(source["center"])
            direction = direction.normalized() if direction.length > 1e-6 else Vector((1.0, 0.0, 0.0))
            return Vector(source["center"]) + direction * props.angle_radius
        start, end = resolve_anchor(props.start), resolve_anchor(props.end)
        if start is None or end is None:
            return None
        geometry = get_dimension_world_geometry(
            props.dimension_type, start, end, Vector(props.offset_plane_normal),
            props.offset_distance, props.offset_angle, props.measurement_mode,
        )
        return None if geometry is None else geometry["line_mid_world"]

    def _mouse_world(self, context, annotation, event):
        props = annotation.dimension_props
        if self.handle_kind == "AREA_LABEL":
            result = evaluate_area_binding(props)
            if result is None:
                return None
            if self.state.axis in {"X", "Y", "Z"}:
                return _axis_mouse_world(
                    context, result["center"], self.state.axis,
                    event.mouse_region_x, event.mouse_region_y,
                )
            snap = find_nearest_snap_point(
                context, event.mouse_region_x, event.mouse_region_y,
                include_free=True, plane_point=result["center"], plane_normal=result["normal"],
            )
            return None if snap is None else snap["world_co"]
        if self.handle_kind == "CIRCLE_LABEL":
            fit = circle_geometry(props)
            if fit is None:
                return None
            if self.state.axis in {"X", "Y", "Z"}:
                return _axis_mouse_world(
                    context, fit["center"], self.state.axis,
                    event.mouse_region_x, event.mouse_region_y,
                )
            snap = find_nearest_snap_point(
                context, event.mouse_region_x, event.mouse_region_y,
                include_free=True, plane_point=fit["center"], plane_normal=fit["normal"],
            )
            return None if snap is None else snap["world_co"]
        if self.handle_kind == "ANGLE_RADIUS":
            source = resolve_angle_source(props)
            if source is None:
                return None
            if self.state.axis in {"X", "Y", "Z"}:
                return _axis_mouse_world(
                    context, source["center"], self.state.axis,
                    event.mouse_region_x, event.mouse_region_y,
                )
            first = Vector(source["start"]) - Vector(source["center"])
            second = Vector(source["end"]) - Vector(source["center"])
            normal = first.cross(second)
            normal = normal.normalized() if normal.length > 1e-6 else Vector((0.0, 0.0, 1.0))
            snap = find_nearest_snap_point(
                context, event.mouse_region_x, event.mouse_region_y,
                include_free=True, plane_point=source["center"], plane_normal=normal,
            )
            return None if snap is None else snap["world_co"]
        start, end = resolve_anchor(props.start), resolve_anchor(props.end)
        if start is None or end is None:
            return None
        base = get_dimension_world_geometry(
            props.dimension_type, start, end, Vector(props.offset_plane_normal),
            0.0, props.offset_angle, props.measurement_mode,
        )
        if base is None:
            return None
        if self.state.axis in {"X", "Y", "Z"}:
            return _axis_mouse_world(
                context, base["line_mid_world"], self.state.axis,
                event.mouse_region_x, event.mouse_region_y,
            )
        snap = find_nearest_snap_point(
            context, event.mouse_region_x, event.mouse_region_y,
            include_free=True,
            plane_point=base["line_mid_world"],
            plane_normal=base["plane_normal_world"],
        )
        return None if snap is None else snap["world_co"]

    def _typed_distance(self, context):
        if not self.state.numeric_text.strip() or not self.state.numeric_valid:
            return None
        value = parse_distance_input(context, self.state.numeric_text)
        return value if self.handle_kind == "LINEAR_OFFSET" else abs(value)

    def _update_candidate(self, context):
        annotation = bpy.data.objects.get(self.annotation_name)
        if annotation is None:
            return
        props = annotation.dimension_props
        typed = self._typed_distance(context)
        if self.handle_kind == "LINEAR_OFFSET":
            value = linear_offset_from_world(props, self.raw_world) if self.raw_world is not None else None
            self.candidate_value = typed if typed is not None else value
        elif self.handle_kind == "ANGLE_RADIUS":
            source = resolve_angle_source(props)
            value = (
                None if source is None or self.raw_world is None
                else angle_radius_from_world(source["center"], self.raw_world)
            )
            self.candidate_value = typed if typed is not None else value
        elif self.handle_kind == "AREA_LABEL":
            result = evaluate_area_binding(props)
            if result is None or self.raw_world is None:
                self.candidate_world = None
                return
            self.candidate_world = _constrained_label_world(
                result["center"], result["normal"], self.raw_world,
                self.state.axis, typed,
            )
        else:
            fit = circle_geometry(props)
            if fit is None or self.raw_world is None:
                self.candidate_world = None
                return
            delta = Vector(self.raw_world) - fit["center"]
            if self.state.axis in {"X", "Y", "Z"}:
                axis = {
                    "X": Vector((1.0, 0.0, 0.0)),
                    "Y": Vector((0.0, 1.0, 0.0)),
                    "Z": Vector((0.0, 0.0, 1.0)),
                }[self.state.axis]
                sign = -1.0 if delta.dot(axis) < 0.0 else 1.0
                delta = axis * sign
            delta -= fit["normal"] * delta.dot(fit["normal"])
            if delta.length >= 1e-6 and typed is not None:
                delta.normalize()
                delta *= typed
            self.candidate_world = None if delta.length < 1e-6 else fit["center"] + delta

    def _commit(self, annotation):
        props = annotation.dimension_props
        if self.handle_kind == "LINEAR_OFFSET":
            props.offset_distance = self.candidate_value
        elif self.handle_kind == "ANGLE_RADIUS":
            props.angle_radius = self.candidate_value
        elif self.handle_kind == "AREA_LABEL":
            result = evaluate_area_binding(props)
            if result is not None:
                apply_area_label_position(
                    annotation, result, self.candidate_world, self.state.axis,
                )
        else:
            fit = circle_geometry(props)
            if fit is not None and self.candidate_world is not None:
                apply_circle_label_position(annotation, fit, self.candidate_world)

    def _update_preview(self, context):
        annotation = bpy.data.objects.get(self.annotation_name)
        if annotation is None:
            return
        props = annotation.dimension_props
        preview = {
            "state": "HANDLE_DRAG",
            "tool_label": "HANDLE",
            "axis": self.state.axis,
            "axis_selectable": True,
            "distance_text": self.state.numeric_text,
            "distance_input_valid": self.state.numeric_valid,
        }
        if self.handle_kind == "LINEAR_OFFSET":
            preview.update({
                "start_world": resolve_anchor(props.start),
                "end_world": resolve_anchor(props.end),
                "dimension_type": props.dimension_type,
                "measurement_mode": props.measurement_mode,
                "offset_plane_normal": tuple(props.offset_plane_normal),
                "offset_distance": self.candidate_value,
                "offset_angle": props.offset_angle,
            })
        elif self.handle_kind == "ANGLE_RADIUS":
            source = resolve_angle_source(props)
            if source is not None:
                preview.update({
                    "annotation_kind": "ANGLE",
                    "start_world": source["start"],
                    "center_world": source["center"],
                    "end_world": source["end"],
                    "angle_radius": self.candidate_value,
                    "angle_mode": source.get("arc_mode", "MINOR"),
                })
        elif self.handle_kind == "AREA_LABEL":
            result = evaluate_area_binding(props)
            if result is not None and self.candidate_world is not None:
                preview.update({
                    "annotation_kind": "AREA",
                    "start_world": result["center"],
                    "end_world": self.candidate_world,
                    "area_value": result["area"],
                    "face_count": result["face_count"],
                })
        else:
            fit = circle_geometry(props)
            if fit is not None and self.candidate_world is not None:
                preview.update({
                    "annotation_kind": "CIRCLE",
                    "circle_kind": props.circle_kind,
                    "center_world": fit["center"],
                    "label_world": self.candidate_world,
                    "edge_world": fit["center"] + (self.candidate_world - fit["center"]).normalized() * fit["radius"],
                    "normal_world": fit["normal"],
                    "start_direction_world": fit["start_direction"],
                    "radius": fit["radius"],
                    "sweep": fit["sweep"],
                    "value": circle_value(props, fit),
                })
        set_preview_state(preview)


classes = (DIMENSIONS_OT_DragAnnotationHandle,)
