"""Transient drafting inference layered over the shared snap acquisition contract."""

from mathutils import Vector
from mathutils.geometry import intersect_line_line, intersect_line_plane
from bpy_extras import view3d_utils


INFERENCE_TYPES = (
    ("parallel", "Parallel"),
    ("perpendicular", "Perpendicular"),
    ("extension", "Extension"),
    ("intersection", "Intersection"),
    ("local_axis", "Local Axis"),
    ("active_plane", "Active Plane"),
)

DERIVED_PRIORITY = 20
_EPSILON = 1e-8


def enabled_inference_types(context):
    from .preferences import get_preferences

    preferences = get_preferences(context)
    return frozenset(
        identifier
        for identifier, _label in INFERENCE_TYPES
        if bool(getattr(preferences, f"inference_{identifier}", True))
    )


def draw_inference_preferences(layout, source):
    grid = layout.grid_flow(row_major=True, columns=2, even_columns=True, align=True)
    for identifier, _label in INFERENCE_TYPES:
        grid.prop(source, f"inference_{identifier}")


def inference_status(session):
    if session is None:
        return ""
    candidate = session.active_candidate
    if candidate is not None:
        suffix = " (locked)" if session.locked else ""
        return f"Inference: {candidate['label']}{suffix}"
    if session.locked:
        label = session.reference_label or "Reference"
        return f"Inference locked: {label}"
    return ""


def handle_inference_event(session, event):
    """Toggle the explicit reference lock through the user-rebindable modal map."""
    if session is None:
        return False
    from .keymaps import modal_action_from_event

    if modal_action_from_event(event) != "TOGGLE_INFERENCE_LOCK":
        return False
    session.toggle_lock()
    return True


def cycle_local_axis(current_axis, requested_axis, context):
    """Global on first axis press, local on repeat, then global again."""
    if requested_axis not in {"X", "Y", "Z"}:
        return requested_axis
    if current_axis == requested_axis and "local_axis" in enabled_inference_types(context):
        return f"LOCAL_{requested_axis}"
    if current_axis == f"LOCAL_{requested_axis}":
        return requested_axis
    return requested_axis


def axis_direction(context, axis):
    if axis in {"X", "Y", "Z"}:
        from .interaction import axis_world_direction

        return axis_world_direction(context, axis)
    if not isinstance(axis, str) or not axis.startswith("LOCAL_"):
        return None
    obj = getattr(context, "active_object", None)
    if obj is None:
        return None
    index = {"X": 0, "Y": 1, "Z": 2}[axis[-1]]
    direction = obj.matrix_world.to_3x3().col[index].copy()
    if direction.length < _EPSILON:
        return None
    return direction.normalized()


def snap_line(snap):
    """Return a stable world-space line represented by an eligible snap."""
    if snap is None:
        return None
    explicit = snap.get("reference_line")
    if explicit is not None:
        origin, direction = Vector(explicit[0]), Vector(explicit[1])
        if direction.length >= _EPSILON:
            return origin, direction.normalized()
    obj = snap.get("object")
    vertices = snap.get("edge_vertices", ())
    if obj is not None and len(vertices) == 2 and getattr(obj, "type", None) == "MESH":
        mesh = obj.data
        if all(0 <= index < len(mesh.vertices) for index in vertices):
            start = obj.matrix_world @ mesh.vertices[vertices[0]].co
            end = obj.matrix_world @ mesh.vertices[vertices[1]].co
            direction = end - start
            if direction.length >= _EPSILON:
                return start, direction.normalized()
    guide_object = snap.get("guide_object")
    if guide_object is not None:
        from .snapping import guide_line_world

        return guide_line_world(guide_object)
    return None


def snap_plane(snap):
    if snap is None:
        return None
    normal = snap.get("normal")
    if normal is not None:
        normal = Vector(normal)
        if normal.length >= _EPSILON:
            return snap["world_co"].copy(), normal.normalized()
    obj = snap.get("object")
    face_index = snap.get("face_index", -1)
    if obj is None or getattr(obj, "type", None) != "MESH":
        return None
    if 0 <= face_index < len(obj.data.polygons):
        polygon = obj.data.polygons[face_index]
        normal = obj.matrix_world.to_3x3().inverted_safe().transposed() @ polygon.normal
        if normal.length >= _EPSILON:
            return obj.matrix_world @ polygon.center, normal.normalized()
    return None


class InferenceSession:
    """Small operator-owned store for implicit and explicitly locked references."""

    def __init__(self):
        self.references = []
        self.locked = False
        self.active_candidate = None

    @property
    def reference_label(self):
        return self.references[0].get("label", "") if self.references else ""

    def clear(self):
        self.references.clear()
        self.locked = False
        self.active_candidate = None

    def toggle_lock(self):
        if not self.references:
            return False
        self.locked = not self.locked
        return True

    def observe(self, snap, enabled_targets):
        if self.locked or snap is None or snap.get("derived"):
            return
        eligible = False
        if snap_line(snap) is not None:
            eligible = (
                (snap.get("guide_object") is not None and "guide" in enabled_targets)
                or (snap.get("object") is not None and "edge" in enabled_targets)
            )
        elif snap_plane(snap) is not None:
            eligible = bool({"face_center", "face_point"} & set(enabled_targets))
        if not eligible:
            return
        identity = _reference_identity(snap)
        references = [snap] + [item for item in self.references if _reference_identity(item) != identity]
        self.references = references[:2]

    def acquire(self, context, mouse_x, mouse_y, base_snap, origin=None, axis=None, pixel_threshold=14.0, enabled_targets=()):
        self.observe(base_snap, enabled_targets)
        candidates = generate_inference_candidates(
            context,
            mouse_x,
            mouse_y,
            self.references,
            origin=origin,
            axis=axis,
            pixel_threshold=pixel_threshold,
            enabled_targets=enabled_targets,
        )
        inference = _nearest_candidate(candidates, mouse_x, mouse_y, pixel_threshold)
        if inference is not None and self.locked:
            inference["inference_locked"] = True
        self.active_candidate = inference
        return inference


def generate_inference_candidates(context, mouse_x, mouse_y, references, *, origin=None, axis=None, pixel_threshold=14.0, enabled_targets=()):
    enabled = enabled_inference_types(context)
    candidates = []
    ray = _mouse_ray(context, mouse_x, mouse_y)
    if ray is None:
        return candidates
    ray_origin, ray_direction = ray
    origin = None if origin is None else Vector(origin)
    line_references = [line for snap in references if (line := snap_line(snap)) is not None]

    if origin is not None and line_references:
        reference_direction = line_references[0][1]
        if "parallel" in enabled:
            _add_line_candidate(context, candidates, ray_origin, ray_direction, origin, reference_direction, "PARALLEL", "Parallel")
        if "perpendicular" in enabled:
            perpendicular = _perpendicular_direction(reference_direction, ray_direction)
            if perpendicular is not None:
                _add_line_candidate(context, candidates, ray_origin, ray_direction, origin, perpendicular, "PERPENDICULAR", "Perpendicular")

    if "extension" in enabled:
        for line_origin, line_direction in line_references[:1]:
            _add_line_candidate(context, candidates, ray_origin, ray_direction, line_origin, line_direction, "EXTENSION", "Extension")

    if "intersection" in enabled and len(line_references) >= 2:
        points = intersect_line_line(
            line_references[0][0], line_references[0][0] + line_references[0][1],
            line_references[1][0], line_references[1][0] + line_references[1][1],
        )
        if points is not None and (points[0] - points[1]).length <= 1e-5:
            _append_candidate(context, candidates, (points[0] + points[1]) * 0.5, "INTERSECTION", "Intersection")

    local_direction = axis_direction(context, axis)
    if origin is not None and isinstance(axis, str) and axis.startswith("LOCAL_") and local_direction is not None and "local_axis" in enabled:
        _add_line_candidate(context, candidates, ray_origin, ray_direction, origin, local_direction, "LOCAL_AXIS", f"Local {axis[-1]}")

    if "active_plane" in enabled:
        plane = next((value for snap in references if (value := snap_plane(snap)) is not None), None)
        if plane is not None:
            point = intersect_line_plane(ray_origin, ray_origin + ray_direction * 100000.0, plane[0], plane[1], False)
            if point is not None:
                _append_candidate(context, candidates, point, "ACTIVE_PLANE", "Active Plane")
    return candidates


def _add_line_candidate(context, candidates, ray_origin, ray_direction, line_origin, line_direction, kind, label):
    points = intersect_line_line(ray_origin, ray_origin + ray_direction, line_origin, line_origin + line_direction)
    if points is None or (points[0] - ray_origin).dot(ray_direction) < 0.0:
        return
    candidate = _append_candidate(context, candidates, points[1], kind, label)
    if candidate is not None:
        candidate["reference_line"] = (Vector(line_origin).copy(), Vector(line_direction).normalized())


def _append_candidate(context, candidates, world_co, kind, label):
    screen_co = view3d_utils.location_3d_to_region_2d(context.region, context.region_data, world_co)
    if screen_co is None:
        return None
    candidate = {
        "type": "INFERENCE",
        "inference_type": kind,
        "label": label,
        "priority": DERIVED_PRIORITY,
        "derived": True,
        "object": None,
        "vertex_index": -1,
        "world_co": Vector(world_co).copy(),
        "screen_co": screen_co.copy(),
    }
    candidates.append(candidate)
    return candidate


def _nearest_candidate(candidates, mouse_x, mouse_y, threshold):
    mouse = Vector((mouse_x, mouse_y))
    ranked = sorted(
        enumerate(candidates),
        key=lambda item: ((item[1]["screen_co"] - mouse).length, item[1]["inference_type"], item[0]),
    )
    if not ranked or (ranked[0][1]["screen_co"] - mouse).length >= threshold:
        return None
    return ranked[0][1]


def _mouse_ray(context, mouse_x, mouse_y):
    from .snapping import get_mouse_ray, has_view3d_window_region

    if not has_view3d_window_region(context):
        return None
    return get_mouse_ray(context, mouse_x, mouse_y)


def _perpendicular_direction(reference, view_ray):
    # The cross product lies in the screen-facing construction plane and is
    # perpendicular to the reference without collapsing onto the mouse ray.
    direction = Vector(view_ray).cross(Vector(reference))
    if direction.length < _EPSILON:
        return None
    return direction.normalized()


def _reference_identity(snap):
    return (
        id(snap.get("object")),
        id(snap.get("guide_object")),
        tuple(snap.get("edge_vertices", ())),
        snap.get("edge_index", -1),
        snap.get("face_index", -1),
        snap.get("type"),
    )
