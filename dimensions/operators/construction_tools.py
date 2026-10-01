"""Construction tools: guide lines, guide points, guide planes, and offset guides.

Every tool acquires points through the same snapping, inference, axis, and typed
distance contract as Create Dimension, then creates an ordinary Blender object
that can be selected, moved, and rotated afterward.
"""

from math import ceil

import bmesh
import bpy
from mathutils import Vector

from .. import messages
from ..collections import (
    create_guide_object,
    create_guide_plane_object,
    create_guide_point_object,
    ensure_guide_point_snap_proxy,
    iter_scene_role_objects,
    remove_guide_point_snap_proxies,
    remove_measurement_snap_proxies,
)
from ..construction import (
    construction_segment_world,
    extent_covering,
    frame_grid_segments,
    guide_line_world,
    nice_grid_spacing,
    plane_frame_from_face,
    plane_frame_from_points,
    set_guide_line_transform,
)
from ..drawing import clear_guide_preview_state, set_guide_preview_state
from ..inference import InferenceSession, cycle_local_axis, handle_inference_event, inference_status
from ..interaction import (
    axis_from_event,
    axis_from_mouse_direction,
    axis_world_direction,
    constrained_delta,
    continuous_placement_enabled,
    is_confirm_event,
    is_navigation_event,
    modal_cleanup_on_exception,
    push_undo_step,
    remember_session_context,
    session_axis,
    session_context_changed,
    set_tool_status_text,
    update_distance_text,
)
from ..keymaps import modal_action_from_event
from ..properties import is_read_only_dimensions_object
from ..snap_targets import handle_snap_target_event
from ..snapping import copy_snap, find_nearest_snap_point, raycast_from_mouse
from ..units import format_length, parse_distance_input
from ..viewport_state import viewport_key


def _select_new_object(context, obj):
    if context.mode != "OBJECT":
        return
    for selected in context.selected_objects:
        selected.select_set(False)
    obj.select_set(True)
    context.view_layer.objects.active = obj


def selection_centroid(context):
    """Return the world centroid of the current mesh or object selection."""
    if context.mode == "EDIT_MESH" and context.edit_object is not None:
        points = []
        for obj in getattr(context, "objects_in_mode", (context.edit_object,)):
            if obj is None or obj.type != "MESH":
                continue
            mesh = bmesh.from_edit_mesh(obj.data)
            points.extend(obj.matrix_world @ vertex.co for vertex in mesh.verts if vertex.select and not vertex.hide)
        return None if not points else sum(points, Vector()) / len(points)
    selected = [obj.matrix_world.translation.copy() for obj in context.selected_objects]
    return None if not selected else sum(selected, Vector()) / len(selected)


def _selected_edit_vertices_world(context):
    obj = context.edit_object
    if obj is None or obj.type != "MESH":
        return []
    mesh = bmesh.from_edit_mesh(obj.data)
    return [obj.matrix_world @ vertex.co for vertex in mesh.verts if vertex.select and not vertex.hide]


def _selected_edit_face_world(context):
    """Return (face points, normal) for the active or first selected Edit Mode face.

    Coordinates are copied out immediately, so creating objects afterward cannot
    invalidate a BMesh reference.
    """
    obj = context.edit_object
    if obj is None or obj.type != "MESH":
        return None
    mesh = bmesh.from_edit_mesh(obj.data)
    face = mesh.faces.active
    if face is None or not face.select or face.hide:
        face = next((item for item in mesh.faces if item.select and not item.hide), None)
    if face is None:
        return None
    points = [obj.matrix_world @ vertex.co for vertex in face.verts]
    normal = obj.matrix_world.to_3x3().inverted_safe().transposed() @ face.normal
    return points, normal


def _face_world_from_hit(context, hit):
    obj = hit["object"]
    face_index = hit.get("face_index", -1)
    if hit.get("edit_mesh"):
        mesh = bmesh.from_edit_mesh(obj.data)
        mesh.faces.ensure_lookup_table()
        if not 0 <= face_index < len(mesh.faces):
            return None
        points = [obj.matrix_world @ vertex.co for vertex in mesh.faces[face_index].verts]
    else:
        evaluated = obj.evaluated_get(context.evaluated_depsgraph_get())
        data = evaluated.data
        if not 0 <= face_index < len(data.polygons):
            return None
        points = [evaluated.matrix_world @ data.vertices[index].co for index in data.polygons[face_index].vertices]
    return points, Vector(hit["normal"])


class _ConstructionTool:
    """Shared point acquisition for construction tools.

    Subclasses set ``points_required`` and implement ``_commit``. They may
    override ``_find_snap``, ``_effective_snap``, ``_validate``, ``_prompt``,
    ``_preview_extras``, and ``_handle_tool_event``.
    """

    tool_label = "GUIDE"
    points_required = 1
    accepts_axis = True
    accepts_distance = True
    status_text = ""

    def invoke(self, context, _event):
        if context.area is None or context.area.type != "VIEW_3D" or context.mode not in {"OBJECT", "EDIT_MESH"}:
            self.report(messages.WARNING, messages.CONSTRUCTION_REQUIRE_SUPPORTED_MODE)
            return {"CANCELLED"}
        self.axis = session_axis(context)
        self.inference_axis = self.axis
        self.continuous_placement = continuous_placement_enabled(context)
        self.picked = []
        self.hover_snap = None
        self.hover_mouse = None
        self.distance_text = ""
        self.distance_input_valid = True
        self.inference_session = InferenceSession()
        remember_session_context(self, context)
        immediate = self._begin(context)
        if immediate is not None:
            return immediate
        self._update_preview(context)
        context.window_manager.modal_handler_add(self)
        set_tool_status_text(context, self.status_text)
        return {"RUNNING_MODAL"}

    def _begin(self, _context):
        return None

    @modal_cleanup_on_exception
    def modal(self, context, event):
        owner_key = getattr(self, "_session_viewport_key", None)
        if owner_key is not None and (
            viewport_key(context) != owner_key
            or getattr(getattr(context, "area", None), "type", None) != "VIEW_3D"
        ):
            self.cancel(context)
            return {"CANCELLED"}
        if self.continuous_placement and session_context_changed(self, context):
            return self._exit(context)
        if handle_snap_target_event(context, event):
            if self.hover_mouse is not None:
                self.hover_snap = self._find_snap(context, self.hover_mouse.x, self.hover_mouse.y)
            self._update_preview(context)
            return {"RUNNING_MODAL"}
        if handle_inference_event(self.inference_session, event):
            self._update_preview(context)
            return {"RUNNING_MODAL"}
        if self._handle_tool_event(context, event):
            self._update_preview(context)
            return {"RUNNING_MODAL"}

        if self.accepts_axis and self.picked and event.type == "MIDDLEMOUSE":
            # Middle drag picks the projected axis closest to the drag direction.
            if event.value == "PRESS":
                self.axis_gesture_active = True
                self._update_axis_gesture(context, event)
                self._update_preview(context)
                return {"RUNNING_MODAL"}
            if event.value == "RELEASE" and getattr(self, "axis_gesture_active", False):
                self.axis_gesture_active = False
                self._update_preview(context)
                return {"RUNNING_MODAL"}

        if self.accepts_axis:
            axis = axis_from_event(event)
            if axis is not None:
                self.inference_axis = cycle_local_axis(self.inference_axis, axis, context)
                self.axis = "ALIGNED" if self.inference_axis.startswith("LOCAL_") else self.inference_axis
                self._update_preview(context)
                return {"RUNNING_MODAL"}

        if self.picked and self.accepts_distance:
            text, handled = update_distance_text(self.distance_text, event)
            if handled:
                self.distance_text = text
                self._effective_snap(context)
                self._update_preview(context)
                return {"RUNNING_MODAL"}

        if event.type == "MOUSEMOVE":
            if getattr(self, "axis_gesture_active", False):
                self._update_axis_gesture(context, event)
            self.hover_mouse = Vector((event.mouse_region_x, event.mouse_region_y))
            self.hover_snap = self._find_snap(context, event.mouse_region_x, event.mouse_region_y)
            self._update_preview(context)
            return {"RUNNING_MODAL"}

        if event.type == "LEFTMOUSE" and event.value == "PRESS":
            mouse = Vector((event.mouse_region_x, event.mouse_region_y))
            if self.hover_snap is None or self.hover_mouse is None or self.hover_mouse != mouse:
                self.hover_mouse = mouse
                self.hover_snap = self._find_snap(context, mouse.x, mouse.y)
            return self._accept(context)

        if is_confirm_event(event):
            return self._accept(context)

        if event.type in {"BACK_SPACE", "DEL"} and event.value == "PRESS":
            self._step_back()
            self._update_preview(context)
            return {"RUNNING_MODAL"}

        if event.type == "ESC" and event.value == "PRESS":
            if self.continuous_placement:
                return self._exit(context)
            if self.distance_text:
                self.distance_text = ""
                self.distance_input_valid = True
                self._update_preview(context)
                return {"RUNNING_MODAL"}
            if self.picked:
                self._step_back()
                self._update_preview(context)
                return {"RUNNING_MODAL"}
            return self._exit(context)

        if event.type == "RIGHTMOUSE" and event.value == "PRESS":
            return self._exit(context)
        if is_navigation_event(event):
            return {"PASS_THROUGH"}
        return {"RUNNING_MODAL"}

    def cancel(self, context):
        clear_guide_preview_state(key=getattr(self, "_session_viewport_key", None))
        set_tool_status_text(context, None)

    def _exit(self, context):
        self.cancel(context)
        return {"CANCELLED"}

    def _handle_tool_event(self, _context, _event):
        return False

    def _update_axis_gesture(self, context, event):
        axis = axis_from_mouse_direction(context, self._origin(), event.mouse_region_x, event.mouse_region_y)
        if axis is not None:
            self.axis = axis
            self.inference_axis = axis

    def _origin(self):
        return self.picked[-1]["world_co"] if self.picked else None

    def _find_snap(self, context, mouse_x, mouse_y):
        origin = self._origin()
        return find_nearest_snap_point(
            context,
            mouse_x,
            mouse_y,
            include_free=True,
            plane_point=origin,
            inference_session=self.inference_session,
            inference_origin=origin,
            inference_axis=self.inference_axis,
        )

    def _effective_snap(self, context):
        """Apply the axis lock and typed distance relative to the previous pick."""
        base = self.hover_snap
        if base is None:
            # Typed distance with a locked axis needs no further mouse movement.
            if not (self.picked and self.distance_text.strip() and self.axis in {"X", "Y", "Z"}):
                return None
            base = {
                "type": "WORLD", "label": "Point", "object": None, "vertex_index": -1,
                "world_co": self._origin() + axis_world_direction(context, self.axis),
                "screen_co": Vector((0.0, 0.0)),
            }
        snap = copy_snap(base)
        if not self.picked:
            return snap
        origin = self._origin()
        raw_delta = snap["world_co"] - origin
        direction = constrained_delta(raw_delta, self.axis, context)
        typed = self.distance_text.strip()
        if typed:
            try:
                distance = parse_distance_input(context, self.distance_text)
            except (TypeError, ValueError):
                self.distance_input_valid = False
                return None
            self.distance_input_valid = True
            if direction.length < 1e-8:
                axis_direction = axis_world_direction(context, self.axis)
                if axis_direction is None:
                    return None
                direction = axis_direction
            direction = direction.normalized() * distance
        else:
            self.distance_input_valid = True
        if typed or (direction - raw_delta).length >= 1e-6:
            snap["type"] = "WORLD"
            snap["label"] = "Typed Point" if typed else "Constrained Point"
            snap["object"] = None
            snap["vertex_index"] = -1
            for key in ("edge_index", "edge_vertices", "edge_factor", "face_index", "guide_object"):
                snap.pop(key, None)
        snap["world_co"] = origin + direction
        return snap

    def _validate(self, _context, _snap):
        return None

    def _on_pick(self, _context, _snap):
        return None

    def _accept(self, context):
        snap = self._effective_snap(context)
        if snap is None:
            if self.distance_text.strip() and not self.distance_input_valid:
                self.report(messages.WARNING, messages.invalid_distance(self.distance_text))
            return {"RUNNING_MODAL"}
        problem = self._validate(context, snap)
        if problem:
            self.report(messages.WARNING, problem)
            return {"RUNNING_MODAL"}
        self.picked.append(snap)
        self._on_pick(context, snap)
        self.distance_text = ""
        self.distance_input_valid = True
        self.hover_snap = None
        if len(self.picked) < self.points_required:
            self._update_preview(context)
            return {"RUNNING_MODAL"}
        if not self._commit(context):
            self.picked.pop()
            self._update_preview(context)
            return {"RUNNING_MODAL"}
        return self._after_commit(context)

    def _after_commit(self, context):
        if not self.continuous_placement:
            self.cancel(context)
            return {"FINISHED"}
        push_undo_step(self.bl_label)
        self.picked.clear()
        self.inference_session.clear()
        self.inference_axis = self.axis
        remember_session_context(self, context)
        self._update_preview(context)
        return {"RUNNING_MODAL"}

    def _step_back(self):
        self.distance_text = ""
        self.distance_input_valid = True
        if self.picked:
            self.picked.pop()
        self.inference_session.clear()

    def _prompt(self):
        return ""

    def _preview_extras(self, _context, _state):
        return None

    def _update_preview(self, context):
        state = {
            "state": f"PICK_{len(self.picked)}",
            "tool_label": self.tool_label,
            "prompt": self._prompt(),
            "axis": self.inference_axis if self.accepts_axis else None,
            "distance_text": self.distance_text,
            "distance_input_valid": self.distance_input_valid,
            "continuous_placement": self.continuous_placement,
            "axis_gesture_active": getattr(self, "axis_gesture_active", False),
        }
        status = inference_status(self.inference_session)
        if status:
            state["inference_status"] = status
        if self.hover_snap is not None:
            state["hover_screen"] = self.hover_snap["screen_co"]
            state["hover_type"] = self.hover_snap.get("type", "WORLD")
            state["hover_label"] = self.hover_snap.get("label", "Point")
            state["hover_snap"] = copy_snap(self.hover_snap)
        if self.picked:
            state["locked_snaps"] = [copy_snap(snap) for snap in self.picked]
            state["axis_origin_world"] = self._origin()
        self._preview_extras(context, state)
        set_guide_preview_state(state, key=getattr(self, "_session_viewport_key", None))


class DIMENSIONS_OT_CreateGuide(_ConstructionTool, bpy.types.Operator):
    bl_idname = "dimensions.create_guide"
    bl_label = "Guide Line"
    bl_description = (
        "Place an infinite construction line: click a point on it, then a second point for its direction. "
        "X, Y, or Z locks the direction. Move or rotate the line afterward like any object"
    )
    bl_options = {"REGISTER", "UNDO"}

    tool_label = "GUIDE LINE"
    points_required = 2
    status_text = "Guide Line: click a point, then a second point for direction · X/Y/Z lock direction · S cycles snapping · Esc exits"

    def _prompt(self):
        return "Click a point on the line" if not self.picked else "Click a second point for its direction"

    def _direction(self, context, start, end):
        direction = Vector(end) - Vector(start)
        if direction.length < 1e-6:
            direction = axis_world_direction(context, self.axis) or Vector()
        return direction

    def _validate(self, context, snap):
        if self.picked and self._direction(context, self._origin(), snap["world_co"]).length < 1e-6:
            return messages.GUIDE_DIRECTION_DISTANCE_REQUIRED
        return None

    def _commit(self, context):
        start, end = (snap["world_co"] for snap in self.picked)
        obj = create_guide_object(context, "GUIDE Line")
        set_guide_line_transform(obj, start, self._direction(context, start, end))
        _select_new_object(context, obj)
        self.report(messages.INFO, messages.CREATED_GUIDE)
        return True

    def _preview_extras(self, context, state):
        if not self.picked:
            return
        end = self._effective_snap(context)
        if end is None:
            return
        direction = self._direction(context, self._origin(), end["world_co"])
        if direction.length >= 1e-6:
            state["start_world"] = self._origin()
            state["end_world"] = self._origin() + direction


_POINT_DESCRIPTIONS = {
    "DIRECT": "Click to place construction points that every tool can snap to. Move them afterward like any object",
    "SELECTION": "Place a construction point at the center of the selected objects or selected mesh vertices",
}


class DIMENSIONS_OT_CreateGuidePoint(_ConstructionTool, bpy.types.Operator):
    bl_idname = "dimensions.create_guide_point"
    bl_label = "Guide Point"
    bl_description = _POINT_DESCRIPTIONS["DIRECT"]
    bl_options = {"REGISTER", "UNDO"}

    placement_mode: bpy.props.EnumProperty(
        name="Placement",
        items=(
            ("DIRECT", "Click", _POINT_DESCRIPTIONS["DIRECT"]),
            ("SELECTION", "Selection Center", _POINT_DESCRIPTIONS["SELECTION"]),
        ),
        default="DIRECT",
        options={"SKIP_SAVE"},
    )

    tool_label = "GUIDE POINT"
    points_required = 1
    accepts_axis = False
    accepts_distance = False
    status_text = "Guide Point: click to place points · S cycles snapping · Esc exits"

    @classmethod
    def description(cls, _context, properties):
        return _POINT_DESCRIPTIONS.get(properties.placement_mode, cls.bl_description)

    def _begin(self, context):
        if self.placement_mode != "SELECTION":
            return None
        point = selection_centroid(context)
        if point is None:
            self.report(messages.WARNING, messages.GUIDE_POINT_SELECTION_REQUIRED)
            return {"CANCELLED"}
        self._create(context, point)
        return {"FINISHED"}

    def _prompt(self):
        return "Click to place a point"

    def _commit(self, context):
        self._create(context, self.picked[0]["world_co"])
        return True

    def _create(self, context, world_co):
        obj = create_guide_point_object(context, "POINT Guide", location=Vector(world_co))
        ensure_guide_point_snap_proxy(obj, context.scene)
        _select_new_object(context, obj)
        self.report(messages.INFO, messages.CREATED_GUIDE_POINT)


_PLANE_DESCRIPTIONS = {
    "THREE_POINTS": (
        "Click three points to place a snappable construction grid through them. "
        "In Edit Mode, three selected vertices are used directly"
    ),
    "FACE": (
        "Place a snappable construction grid lying on a face and extending past it. "
        "In Edit Mode the selected face is used; otherwise click a face"
    ),
}


class DIMENSIONS_OT_CreateGuidePlane(_ConstructionTool, bpy.types.Operator):
    bl_idname = "dimensions.create_guide_plane"
    bl_label = "Guide Plane"
    bl_description = _PLANE_DESCRIPTIONS["THREE_POINTS"]
    bl_options = {"REGISTER", "UNDO"}

    definition: bpy.props.EnumProperty(
        name="Definition",
        items=(
            ("THREE_POINTS", "3 Points", _PLANE_DESCRIPTIONS["THREE_POINTS"]),
            ("FACE", "Face", _PLANE_DESCRIPTIONS["FACE"]),
        ),
        default="THREE_POINTS",
        options={"SKIP_SAVE"},
    )

    tool_label = "GUIDE PLANE"
    status_text = "Guide Plane: click three points · X/Y/Z lock direction · S cycles snapping · Esc exits"

    @classmethod
    def description(cls, _context, properties):
        return _PLANE_DESCRIPTIONS.get(properties.definition, cls.bl_description)

    def _begin(self, context):
        if self.definition == "FACE":
            self.points_required = 1
            self.accepts_axis = False
            self.accepts_distance = False
            self.tool_label = "PLANE FROM FACE"
            self.status_text = "Guide Plane: click a face · Esc exits"
            if context.mode == "EDIT_MESH":
                face = _selected_edit_face_world(context)
                if face is not None:
                    return {"FINISHED"} if self._create_from_face(context, *face) else {"CANCELLED"}
            return None
        self.points_required = 3
        if context.mode == "EDIT_MESH":
            points = _selected_edit_vertices_world(context)
            if len(points) == 3:
                return {"FINISHED"} if self._create_from_points(context, points) else {"CANCELLED"}
        return None

    def _find_snap(self, context, mouse_x, mouse_y):
        if self.definition != "FACE":
            return _ConstructionTool._find_snap(self, context, mouse_x, mouse_y)
        hit = raycast_from_mouse(context, mouse_x, mouse_y, include_guide_planes=False)
        if hit is None:
            return None
        face = _face_world_from_hit(context, hit)
        if face is None:
            return None
        return {
            "type": "FACE",
            "label": "Face",
            "object": hit["object"],
            "vertex_index": -1,
            "face_index": hit.get("face_index", -1),
            "world_co": Vector(hit["location"]),
            "screen_co": Vector((mouse_x, mouse_y)),
            "normal": Vector(hit["normal"]),
            "face_points": face[0],
        }

    def _effective_snap(self, context):
        if self.definition == "FACE":
            return None if self.hover_snap is None else copy_snap(self.hover_snap)
        return _ConstructionTool._effective_snap(self, context)

    def _validate(self, _context, snap):
        if self.definition == "FACE" or not self.picked:
            return None
        if any((Vector(snap["world_co"]) - Vector(item["world_co"])).length < 1e-6 for item in self.picked):
            return messages.GUIDE_PLANE_POINTS_INVALID
        return None

    def _prompt(self):
        if self.definition == "FACE":
            return "Click a face"
        return ("Click the first point", "Click the second point", "Click the third point")[min(len(self.picked), 2)]

    def _commit(self, context):
        if self.definition == "FACE":
            snap = self.picked[0]
            return self._create_from_face(context, snap["face_points"], snap["normal"])
        return self._create_from_points(context, [snap["world_co"] for snap in self.picked])

    def _create_from_points(self, context, points):
        frame = plane_frame_from_points(points)
        if frame is None:
            self.report(messages.WARNING, messages.GUIDE_PLANE_POINTS_INVALID)
            return False
        return self._create(context, frame, extent_covering(frame, points))

    def _create_from_face(self, context, points, normal):
        frame = plane_frame_from_face(points, normal)
        if frame is None:
            self.report(messages.WARNING, messages.SELECT_FACE_FOR_PLANE)
            return False
        return self._create(context, frame, extent_covering(frame, points, margin=1.5))

    def _create(self, context, frame, extent):
        spacing = nice_grid_spacing(extent)
        extent = max(1, ceil(extent / spacing - 1e-9)) * spacing
        obj = create_guide_plane_object(context, frame, extent, spacing, "PLANE Guide Grid")
        _select_new_object(context, obj)
        self.report(messages.INFO, messages.CREATED_GUIDE_PLANE)
        return True

    def _preview_extras(self, context, state):
        if self.definition == "FACE":
            if self.hover_snap is not None:
                frame = plane_frame_from_face(self.hover_snap["face_points"], self.hover_snap["normal"])
                if frame is not None:
                    extent = extent_covering(frame, self.hover_snap["face_points"], margin=1.5)
                    state["plane_preview_segments"] = frame_grid_segments(frame, extent, nice_grid_spacing(extent))
            return
        candidate = self._effective_snap(context) if self.picked else None
        points = [snap["world_co"] for snap in self.picked]
        if candidate is not None:
            points.append(candidate["world_co"])
        if len(points) == 2:
            state["plane_preview_segments"] = [points[0], points[1]]
        elif len(points) == 3:
            frame = plane_frame_from_points(points)
            if frame is not None:
                extent = extent_covering(frame, points)
                state["plane_preview_segments"] = frame_grid_segments(frame, extent, nice_grid_spacing(extent))


def _snap_line(snap):
    """Return (origin, direction) for an edge, guide, or measurement snap."""
    if snap is None:
        return None
    reference = snap.get("reference_line")
    if reference is not None and snap.get("type") == "GUIDE":
        return Vector(reference[0]), Vector(reference[1]).normalized()
    construction = snap.get("guide_object")
    if snap.get("type") == "GUIDE" and construction is not None:
        return guide_line_world(construction)
    if snap.get("type") == "MEASUREMENT" and construction is not None:
        segment = construction_segment_world(construction)
        if segment is None:
            return None
        return segment[0], (segment[1] - segment[0]).normalized()
    obj = snap.get("object")
    vertices = snap.get("edge_vertices", ())
    if snap.get("type") != "EDGE" or obj is None or getattr(obj, "type", None) != "MESH" or len(vertices) != 2:
        return None
    if obj.mode == "EDIT":
        mesh = bmesh.from_edit_mesh(obj.data)
        mesh.verts.ensure_lookup_table()
        coordinates = mesh.verts
    else:
        coordinates = obj.data.vertices
    if not all(0 <= index < len(coordinates) for index in vertices):
        return None
    start = obj.matrix_world @ coordinates[vertices[0]].co
    end = obj.matrix_world @ coordinates[vertices[1]].co
    if (end - start).length < 1e-8:
        return None
    return start, (end - start).normalized()


def _snap_face_normal(snap):
    obj = snap.get("object")
    face_index = snap.get("face_index", -1)
    if obj is None or getattr(obj, "type", None) != "MESH" or face_index is None or face_index < 0:
        return None
    if obj.mode == "EDIT":
        mesh = bmesh.from_edit_mesh(obj.data)
        mesh.faces.ensure_lookup_table()
        if face_index >= len(mesh.faces):
            return None
        normal = mesh.faces[face_index].normal
    else:
        if face_index >= len(obj.data.polygons):
            return None
        normal = obj.data.polygons[face_index].normal
    normal = obj.matrix_world.to_3x3().inverted_safe().transposed() @ normal
    return None if normal.length < 1e-8 else normal.normalized()


class DIMENSIONS_OT_CreateOffsetGuide(_ConstructionTool, bpy.types.Operator):
    bl_idname = "dimensions.create_offset_guide"
    bl_label = "Offset Guide"
    bl_description = (
        "Place a guide line parallel to an edge, guide line, or measurement: click the source, "
        "then click where the new line passes or type its distance. F flips the side"
    )
    bl_options = {"REGISTER", "UNDO"}

    tool_label = "OFFSET GUIDE"
    points_required = 2
    accepts_axis = False
    status_text = "Offset Guide: click an edge, guide, or measurement · click or type the distance · F flips side · Esc exits"

    def _begin(self, _context):
        self.source_line = None
        self.offset_normal = None
        self.flip = 1.0
        return None

    def _handle_tool_event(self, _context, event):
        if self.picked and modal_action_from_event(event) == "FLIP_OFFSET":
            self.flip = -self.flip
            return True
        return False

    def _find_snap(self, context, mouse_x, mouse_y):
        if not self.picked:
            snap = find_nearest_snap_point(context, mouse_x, mouse_y, include_free=False)
            return snap if _snap_line(snap) is not None else None
        origin, _direction = self.source_line
        return find_nearest_snap_point(
            context, mouse_x, mouse_y,
            include_free=True,
            plane_point=origin,
            plane_normal=self.offset_normal,
            inference_session=self.inference_session,
            inference_origin=origin,
        )

    def _offset_vector(self, context, point):
        origin, direction = self.source_line
        relative = Vector(point) - origin
        offset = relative - direction * relative.dot(direction)
        if self.distance_text.strip():
            try:
                distance = parse_distance_input(context, self.distance_text)
            except (TypeError, ValueError):
                self.distance_input_valid = False
                return None
            self.distance_input_valid = True
            side = offset if offset.length >= 1e-8 else self.offset_normal.cross(direction)
            if side.length < 1e-8:
                return None
            return side.normalized() * distance * self.flip
        self.distance_input_valid = True
        return offset

    def _effective_snap(self, context):
        if not self.picked:
            return None if self.hover_snap is None else copy_snap(self.hover_snap)
        point = self.hover_snap["world_co"] if self.hover_snap is not None else self.source_line[0]
        offset = self._offset_vector(context, point)
        if offset is None:
            return None
        snap = copy_snap(self.hover_snap) if self.hover_snap is not None else {
            "type": "WORLD", "label": "Point", "object": None, "vertex_index": -1,
            "screen_co": Vector((0.0, 0.0)),
        }
        snap["world_co"] = self.source_line[0] + offset
        return snap

    def _validate(self, _context, snap):
        if not self.picked:
            return None if _snap_line(snap) is not None else messages.OFFSET_SOURCE_REQUIRED
        if (Vector(snap["world_co"]) - self.source_line[0]).length < 1e-6:
            return messages.OFFSET_DISTANCE_REQUIRED
        return None

    def _on_pick(self, context, snap):
        if len(self.picked) != 1:
            return
        self.source_line = _snap_line(snap)
        self.offset_normal = _snap_face_normal(snap) or self._view_offset_normal(context, self.source_line[1])
        self.flip = 1.0

    @staticmethod
    def _view_offset_normal(context, direction):
        view = context.region_data.view_rotation @ Vector((0.0, 0.0, -1.0))
        normal = view - direction * view.dot(direction)
        if normal.length < 1e-6:
            normal = direction.orthogonal()
        return normal.normalized()

    def _prompt(self):
        if not self.picked:
            return "Click an edge, guide line, or measurement"
        return "Click where the parallel guide passes, or type a distance"

    def _commit(self, context):
        origin = self.picked[-1]["world_co"]
        obj = create_guide_object(context, "GUIDE Offset")
        set_guide_line_transform(obj, origin, self.source_line[1])
        _select_new_object(context, obj)
        distance = (Vector(origin) - self.source_line[0]).length
        precision = context.scene.dimensions_settings.precision
        self.report(messages.INFO, messages.created_offset_guide(format_length(context, distance, precision)))
        return True

    def _after_commit(self, context):
        self.source_line = None
        self.offset_normal = None
        return _ConstructionTool._after_commit(self, context)

    def _step_back(self):
        _ConstructionTool._step_back(self)
        if not self.picked:
            self.source_line = None
            self.offset_normal = None

    def _preview_extras(self, context, state):
        if not self.picked or self.source_line is None:
            return
        candidate = self._effective_snap(context)
        if candidate is None:
            return
        origin = candidate["world_co"]
        state["start_world"] = origin
        state["end_world"] = origin + self.source_line[1]
        precision = context.scene.dimensions_settings.precision
        distance = format_length(context, (Vector(origin) - self.source_line[0]).length, precision)
        state["prompt"] = f"Offset {distance} · click to place or type a distance"


def _clear_construction(context, kinds):
    removed = 0
    for obj in list(iter_scene_role_objects(context.scene, "GUIDES")):
        props = getattr(obj, "guide_props", None)
        if props is None or not props.enabled or getattr(props, "kind", "GUIDE") not in kinds:
            continue
        if is_read_only_dimensions_object(obj):
            continue
        kind = props.kind
        if kind == "POINT":
            remove_guide_point_snap_proxies(obj)
        elif kind == "MEASUREMENT":
            remove_measurement_snap_proxies(obj)
        mesh = obj.data if obj.type == "MESH" else None
        bpy.data.objects.remove(obj, do_unlink=True)
        if mesh is not None and mesh.users == 0:
            bpy.data.meshes.remove(mesh)
        removed += 1
    return removed


class DIMENSIONS_OT_ClearGuides(bpy.types.Operator):
    bl_idname = "dimensions.clear_guides"
    bl_label = "Clear Guides"
    bl_description = "Delete every guide line, guide point, and guide plane in this scene. Saved measurements are kept"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        removed = _clear_construction(context, {"GUIDE", "POINT", "PLANE"})
        self.report(messages.INFO, messages.cleared_guides(removed))
        return {"FINISHED"}


class DIMENSIONS_OT_ClearMeasurements(bpy.types.Operator):
    bl_idname = "dimensions.clear_measurements"
    bl_label = "Clear Measurements"
    bl_description = "Delete every saved measurement in this scene"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        removed = _clear_construction(context, {"MEASUREMENT"})
        self.report(messages.INFO, messages.cleared_measurements(removed))
        return {"FINISHED"}


classes = (
    DIMENSIONS_OT_CreateGuide,
    DIMENSIONS_OT_CreateGuidePoint,
    DIMENSIONS_OT_CreateGuidePlane,
    DIMENSIONS_OT_CreateOffsetGuide,
    DIMENSIONS_OT_ClearGuides,
    DIMENSIONS_OT_ClearMeasurements,
)
