import bmesh
import bpy
from mathutils import Vector

from .. import messages
from mathutils.geometry import intersect_line_line

from ..anchors import resolve_anchor, set_object_anchor
from ..area_binding import bind_area_face_indices, evaluate_area_binding, evaluate_area_face_indices
from ..collections import create_dimension_object
from ..constants import DEFAULT_OFFSET_DISTANCE
from ..drawing import clear_preview_state, set_preview_state
from ..interaction import axis_from_event, update_distance_text
from ..properties import is_dimension_object
from ..snapping import copy_snap, find_nearest_snap_point, get_mouse_ray, has_view3d_window_region, raycast_from_mouse
from ..units import parse_distance_input


_AXIS_DIRECTIONS = {
    "X": Vector((1.0, 0.0, 0.0)),
    "Y": Vector((0.0, 1.0, 0.0)),
    "Z": Vector((0.0, 0.0, 1.0)),
}


def _axis_mouse_world(context, center, axis, mouse_x, mouse_y):
    direction = _AXIS_DIRECTIONS.get(axis)
    if direction is None:
        return None
    ray_origin, ray_direction = get_mouse_ray(context, mouse_x, mouse_y)
    closest = intersect_line_line(
        Vector(center),
        Vector(center) + direction,
        ray_origin,
        ray_origin + ray_direction * 100000.0,
    )
    return None if closest is None else closest[0]


def _default_area_direction(normal):
    normal = Vector(normal).normalized()
    axis = min(_AXIS_DIRECTIONS.values(), key=lambda candidate: abs(candidate.dot(normal)))
    direction = axis - normal * axis.dot(normal)
    return direction.normalized() if direction.length > 1e-6 else Vector((1.0, 0.0, 0.0))


def _constrained_label_world(center, normal, raw_world, axis, typed_distance=None):
    center = Vector(center)
    raw_delta = Vector(raw_world) - center
    if axis in _AXIS_DIRECTIONS:
        direction = _AXIS_DIRECTIONS[axis]
        signed_distance = raw_delta.dot(direction)
        if typed_distance is not None:
            signed_distance = (-1.0 if signed_distance < 0.0 else 1.0) * typed_distance
        return center + direction * signed_distance
    direction = raw_delta
    if direction.length < 1e-6:
        direction = _default_area_direction(normal)
    if typed_distance is not None:
        direction = direction.normalized() * typed_distance
    return center + direction


class DIMENSIONS_OT_CreateArea(bpy.types.Operator):
    bl_idname = "dimensions.create_area"
    bl_label = "Create Area Dimension"
    bl_description = "Choose source faces, then place the Area label"
    bl_options = {"REGISTER", "UNDO"}

    replace_active: bpy.props.BoolProperty(default=False, options={"SKIP_SAVE"})

    def invoke(self, context, _event):
        if not has_view3d_window_region(context):
            self.report(messages.WARNING, messages.RUN_FROM_3D_VIEW)
            return {"CANCELLED"}
        if context.mode not in {"OBJECT", "EDIT_MESH"}:
            self.report(messages.WARNING, messages.AREA_REQUIRE_SUPPORTED_MODE)
            return {"CANCELLED"}
        self.target_name = ""
        if self.replace_active:
            active = context.view_layer.objects.active
            if not is_dimension_object(active) or active.dimension_props.annotation_kind != "AREA":
                self.report(messages.WARNING, messages.SELECT_AREA_DIMENSION)
                return {"CANCELLED"}
            self.target_name = active.name

        self.source_object = None
        self.face_indices = []
        self.hover_snap = None
        self.label_snap = None
        self.area_result = None
        self.placement_axis = "ALIGNED"
        self.distance_text = ""
        self.distance_input_valid = True
        self.typed_distance = None
        self.state = "PICK_FACE"
        if context.mode == "EDIT_MESH" and context.edit_object is not None:
            bm = bmesh.from_edit_mesh(context.edit_object.data)
            bm.faces.ensure_lookup_table()
            selected = [face.index for face in bm.faces if face.select and not face.hide]
            if selected:
                self.source_object = context.edit_object
                self.face_indices = selected
                self.area_result = evaluate_area_face_indices(self.source_object, self.face_indices)
                if self.area_result is not None:
                    self.state = "PLACE_LABEL"
        self._update_preview()
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if not has_view3d_window_region(context):
            clear_preview_state()
            return {"CANCELLED"}
        if self.state == "PLACE_LABEL":
            axis = axis_from_event(event)
            if axis is not None:
                self.placement_axis = axis
                self._update_effective_label(context)
                self._update_preview()
                return {"RUNNING_MODAL"}
            new_text, handled = update_distance_text(self.distance_text, event)
            if handled:
                self.distance_text = new_text
                self._update_typed_distance(context)
                self._update_effective_label(context)
                self._update_preview()
                return {"RUNNING_MODAL"}
        if event.type == "MOUSEMOVE":
            if self.state == "PICK_FACE":
                self.hover_snap = find_nearest_snap_point(
                    context,
                    event.mouse_region_x,
                    event.mouse_region_y,
                    include_guides=False,
                    include_free=False,
                )
            else:
                if self.placement_axis in _AXIS_DIRECTIONS:
                    world = _axis_mouse_world(
                        context,
                        self.area_result["center"],
                        self.placement_axis,
                        event.mouse_region_x,
                        event.mouse_region_y,
                    )
                    self.hover_snap = None if world is None else {
                        "type": "WORLD",
                        "label": f"{self.placement_axis} Axis",
                        "world_co": world,
                        "screen_co": Vector((event.mouse_region_x, event.mouse_region_y)),
                    }
                else:
                    self.hover_snap = find_nearest_snap_point(
                        context,
                        event.mouse_region_x,
                        event.mouse_region_y,
                        include_free=True,
                        plane_point=self.area_result["center"],
                        plane_normal=self.area_result["normal"],
                    )
                self._update_effective_label(context)
            self._update_preview()
            return {"RUNNING_MODAL"}
        if event.type == "LEFTMOUSE" and event.value == "PRESS":
            if self.state == "PICK_FACE":
                return self._accept_face(context, event)
            return self._commit(context)
        if event.type in {"RET", "NUMPAD_ENTER"} and event.value == "PRESS":
            if self.state == "PICK_FACE" and self.face_indices:
                self.area_result = evaluate_area_face_indices(self.source_object, self.face_indices)
                if self.area_result is not None:
                    self.state = "PLACE_LABEL"
                    self._update_preview()
            elif self.state == "PLACE_LABEL" and self.label_snap is not None:
                return self._commit(context)
            return {"RUNNING_MODAL"}
        if event.type == "ESC" and event.value == "PRESS":
            if self.distance_text:
                self.distance_text = ""
                self.typed_distance = None
                self.distance_input_valid = True
                self._update_effective_label(context)
                self._update_preview()
                return {"RUNNING_MODAL"}
            if self.state == "PLACE_LABEL" and context.mode == "OBJECT":
                self.state = "PICK_FACE"
                self.label_snap = None
                self._update_preview()
                return {"RUNNING_MODAL"}
            clear_preview_state()
            return {"CANCELLED"}
        if event.type == "RIGHTMOUSE" and event.value == "PRESS":
            clear_preview_state()
            return {"CANCELLED"}
        if event.type in {"MIDDLEMOUSE", "WHEELUPMOUSE", "WHEELDOWNMOUSE"}:
            return {"PASS_THROUGH"}
        return {"RUNNING_MODAL"}

    def _accept_face(self, context, event):
        snap = self.hover_snap
        source = None if snap is None else snap.get("object")
        face_index = -1 if snap is None else snap.get("face_index", -1)
        if source is None or face_index < 0:
            hit = raycast_from_mouse(context, event.mouse_region_x, event.mouse_region_y)
            if hit is not None:
                source = hit.get("object")
                face_index = hit.get("face_index", -1)
        if source is None or source.type != "MESH" or face_index < 0:
            self.report(messages.WARNING, messages.POINT_BASE_MESH_FACE)
            return {"RUNNING_MODAL"}
        if source.modifiers and context.mode == "OBJECT":
            self.report(messages.WARNING, messages.AREA_BASE_MESH_REQUIRED)
            return {"RUNNING_MODAL"}
        if self.source_object is not None and source != self.source_object:
            self.report(messages.WARNING, messages.AREA_SINGLE_OBJECT_REQUIRED)
            return {"RUNNING_MODAL"}
        self.source_object = source
        if event.shift:
            if face_index in self.face_indices:
                self.face_indices.remove(face_index)
            else:
                self.face_indices.append(face_index)
            self.area_result = evaluate_area_face_indices(source, self.face_indices)
            self._update_preview()
            return {"RUNNING_MODAL"}
        if face_index not in self.face_indices:
            self.face_indices.append(face_index)
        self.area_result = evaluate_area_face_indices(source, self.face_indices)
        if self.area_result is None:
            self.report(messages.WARNING, messages.AREA_FACES_UNMEASURABLE)
            return {"RUNNING_MODAL"}
        self.state = "PLACE_LABEL"
        self._update_preview()
        return {"RUNNING_MODAL"}

    def _commit(self, context):
        if self.distance_text and not self.distance_input_valid:
            self.report(messages.WARNING, messages.invalid_distance(self.distance_text))
            return {"RUNNING_MODAL"}
        if self.label_snap is None or self.source_object is None or self.area_result is None:
            return {"RUNNING_MODAL"}
        annotation = bpy.data.objects.get(self.target_name) if self.target_name else None
        if annotation is None:
            annotation = create_dimension_object(context, "AREA Faces")
        props = annotation.dimension_props
        props.annotation_kind = "AREA"
        result = bind_area_face_indices(props, self.source_object, self.face_indices)
        if result is None:
            self.report(messages.WARNING, messages.AREA_SOURCE_INVALID)
            clear_preview_state()
            return {"CANCELLED"}
        props.area_value = result["area"]
        props.area_face_count = result["face_count"]
        props.dimension_type = self.placement_axis
        label_delta = self.label_snap["world_co"] - result["center"]
        props.offset_distance = label_delta.length
        props.area_label_direction = tuple(label_delta.normalized()) if label_delta.length > 1e-6 else (1.0, 0.0, 0.0)
        props.area_placement_locked = True
        props.presentation_offset = (0.0, 0.0, 0.0)
        props.placement_initialized = False
        set_object_anchor(props.start, self.source_object, result["center"])
        set_object_anchor(props.end, self.source_object, self.label_snap["world_co"])
        annotation.location = self.label_snap["world_co"]
        clear_preview_state()
        if context.mode == "OBJECT":
            for selected in context.selected_objects:
                selected.select_set(False)
            annotation.select_set(True)
            context.view_layer.objects.active = annotation
        self.report(messages.INFO, messages.created_area(len(self.face_indices), bool(self.target_name)))
        return {"FINISHED"}

    def _update_preview(self):
        preview = {
            "state": self.state,
            "annotation_kind": "AREA",
            "axis": self.placement_axis,
            "distance_text": self.distance_text,
            "distance_input_valid": self.distance_input_valid,
        }
        if self.hover_snap is not None:
            preview["hover_screen"] = self.hover_snap["screen_co"]
            preview["hover_type"] = self.hover_snap.get("type", "WORLD")
            preview["hover_label"] = self.hover_snap.get("label", "Point")
        if self.area_result is not None:
            preview["start_world"] = self.area_result["center"]
            preview["end_world"] = (
                self.label_snap["world_co"]
                if self.label_snap is not None
                else self.area_result["center"] + self.area_result["normal"] * DEFAULT_OFFSET_DISTANCE
            )
            preview["area_value"] = self.area_result["area"]
            preview["face_count"] = self.area_result["face_count"]
        set_preview_state(preview)

    def _update_typed_distance(self, context):
        if not self.distance_text.strip():
            self.typed_distance = None
            self.distance_input_valid = True
            return
        try:
            self.typed_distance = abs(parse_distance_input(context, self.distance_text))
            self.distance_input_valid = True
        except (TypeError, ValueError):
            self.typed_distance = None
            self.distance_input_valid = False

    def _update_effective_label(self, _context):
        if self.area_result is None:
            return
        if self.hover_snap is None:
            if self.typed_distance is None:
                return
            direction = _AXIS_DIRECTIONS.get(
                self.placement_axis,
                _default_area_direction(self.area_result["normal"]),
            )
            self.hover_snap = {
                "type": "WORLD",
                "label": "Typed Area Placement",
                "world_co": self.area_result["center"] + direction,
                "screen_co": Vector((0.0, 0.0)),
            }
        world = _constrained_label_world(
            self.area_result["center"],
            self.area_result["normal"],
            self.hover_snap["world_co"],
            self.placement_axis,
            self.typed_distance,
        )
        self.label_snap = copy_snap(self.hover_snap)
        self.label_snap["world_co"] = world



class DIMENSIONS_OT_MoveAreaLabel(bpy.types.Operator):
    bl_idname = "dimensions.move_area_label"
    bl_label = "Move Area Label"
    bl_description = "Place this Area label and leader without changing its source faces"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.view_layer.objects.active
        return bool(context.mode == "OBJECT" and is_dimension_object(obj) and obj.dimension_props.annotation_kind == "AREA")

    def invoke(self, context, _event):
        self.annotation_name = context.view_layer.objects.active.name
        self.hover_snap = None
        self.raw_snap = None
        props = context.view_layer.objects.active.dimension_props
        self.placement_axis = props.dimension_type
        self.distance_text = ""
        self.distance_input_valid = True
        self.typed_distance = None
        self._update_preview(context)
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        annotation = bpy.data.objects.get(self.annotation_name)
        if annotation is None or not has_view3d_window_region(context):
            clear_preview_state()
            return {"CANCELLED"}
        result = evaluate_area_binding(annotation.dimension_props)
        if result is None:
            self.report(messages.WARNING, messages.AREA_SOURCE_INVALID)
            clear_preview_state()
            return {"CANCELLED"}
        axis = axis_from_event(event)
        if axis is not None:
            self.placement_axis = axis
            self._update_effective_snap(result)
            self._update_preview(context)
            return {"RUNNING_MODAL"}
        new_text, handled = update_distance_text(self.distance_text, event)
        if handled:
            self.distance_text = new_text
            if self.distance_text.strip():
                try:
                    self.typed_distance = abs(parse_distance_input(context, self.distance_text))
                    self.distance_input_valid = True
                except (TypeError, ValueError):
                    self.typed_distance = None
                    self.distance_input_valid = False
            else:
                self.typed_distance = None
                self.distance_input_valid = True
            self._update_effective_snap(result)
            self._update_preview(context)
            return {"RUNNING_MODAL"}
        if event.type == "MOUSEMOVE":
            if self.placement_axis in _AXIS_DIRECTIONS:
                world = _axis_mouse_world(
                    context,
                    result["center"],
                    self.placement_axis,
                    event.mouse_region_x,
                    event.mouse_region_y,
                )
                self.raw_snap = None if world is None else {
                    "type": "WORLD",
                    "label": f"{self.placement_axis} Axis",
                    "world_co": world,
                    "screen_co": Vector((event.mouse_region_x, event.mouse_region_y)),
                }
            else:
                self.raw_snap = find_nearest_snap_point(
                    context,
                    event.mouse_region_x,
                    event.mouse_region_y,
                    include_free=True,
                    plane_point=result["center"],
                    plane_normal=result["normal"],
                )
            self._update_effective_snap(result)
            self._update_preview(context)
            return {"RUNNING_MODAL"}
        if event.type == "LEFTMOUSE" and event.value == "PRESS" and self.hover_snap is not None:
            if self.distance_text and not self.distance_input_valid:
                self.report(messages.WARNING, messages.invalid_distance(self.distance_text))
                return {"RUNNING_MODAL"}
            props = annotation.dimension_props
            set_object_anchor(props.end, props.area_source_object, self.hover_snap["world_co"])
            props.dimension_type = self.placement_axis
            label_delta = self.hover_snap["world_co"] - result["center"]
            props.offset_distance = label_delta.length
            props.area_label_direction = tuple(label_delta.normalized()) if label_delta.length > 1e-6 else (1.0, 0.0, 0.0)
            props.area_placement_locked = True
            props.presentation_offset = (0.0, 0.0, 0.0)
            props.placement_initialized = False
            annotation.location = self.hover_snap["world_co"]
            clear_preview_state()
            return {"FINISHED"}
        if event.type in {"RIGHTMOUSE", "ESC"} and event.value == "PRESS":
            clear_preview_state()
            return {"CANCELLED"}
        if event.type in {"MIDDLEMOUSE", "WHEELUPMOUSE", "WHEELDOWNMOUSE"}:
            return {"PASS_THROUGH"}
        return {"RUNNING_MODAL"}

    def _update_preview(self, context):
        annotation = bpy.data.objects.get(self.annotation_name)
        if annotation is None:
            return
        props = annotation.dimension_props
        result = evaluate_area_binding(props)
        if result is None:
            return
        end = self.hover_snap["world_co"] if self.hover_snap is not None else resolve_anchor(props.end)
        set_preview_state({
            "state": "MOVE_AREA_LABEL",
            "annotation_kind": "AREA",
            "start_world": result["center"],
            "end_world": end,
            "area_value": result["area"],
            "face_count": result["face_count"],
            "axis": self.placement_axis,
            "distance_text": self.distance_text,
            "distance_input_valid": self.distance_input_valid,
            "hover_screen": None if self.hover_snap is None else self.hover_snap["screen_co"],
        })

    def _update_effective_snap(self, result):
        if self.raw_snap is None:
            if self.typed_distance is None:
                return
            direction = _AXIS_DIRECTIONS.get(
                self.placement_axis,
                _default_area_direction(result["normal"]),
            )
            self.raw_snap = {
                "type": "WORLD",
                "label": "Typed Area Placement",
                "world_co": result["center"] + direction,
                "screen_co": Vector((0.0, 0.0)),
            }
        self.hover_snap = copy_snap(self.raw_snap)
        self.hover_snap["world_co"] = _constrained_label_world(
            result["center"],
            result["normal"],
            self.raw_snap["world_co"],
            self.placement_axis,
            self.typed_distance,
        )
