"""Persistent construction-plane definitions and active-plane frames."""

from mathutils import Vector

from .anchors import anchor_resolution
from .derived_guides import resolve_source


EPSILON = 1e-6


def plane_frame(origin, normal, preferred_axis=None):
    """Return a stable orthonormal (origin, U, V, normal) frame."""
    origin = Vector(origin)
    normal = Vector(normal)
    if normal.length < EPSILON:
        return None
    normal.normalize()
    axis_u = Vector(preferred_axis or (1.0, 0.0, 0.0))
    axis_u -= normal * axis_u.dot(normal)
    if axis_u.length < EPSILON:
        axis_u = Vector((0.0, 1.0, 0.0))
        axis_u -= normal * axis_u.dot(normal)
    if axis_u.length < EPSILON:
        return None
    axis_u.normalize()
    axis_v = normal.cross(axis_u)
    if axis_v.length < EPSILON:
        return None
    axis_v.normalize()
    return origin, axis_u, axis_v, normal


def resolve_guide_plane(plane_object, visited=None):
    """Resolve a saved plane, refusing dependency cycles and exposing repair state."""
    props = getattr(plane_object, "guide_props", None)
    if props is None or not props.enabled or getattr(props, "kind", "GUIDE") != "PLANE":
        return None
    visited = set() if visited is None else set(visited)
    identity = plane_object.as_pointer() if hasattr(plane_object, "as_pointer") else id(plane_object)
    if identity in visited:
        _store_state(props, None, "CYCLE")
        return None
    visited.add(identity)

    definition = getattr(props, "plane_definition", "POINT_NORMAL")
    frame = None
    if definition == "THREE_POINTS":
        points = []
        fallback = False
        for anchor in (props.plane_point_a, props.plane_point_b, props.plane_point_c):
            point, status = anchor_resolution(anchor)
            if status == "UNRESOLVABLE":
                _store_state(props, None, "NEEDS_REPAIR")
                return None
            fallback = fallback or status != "BY_ID"
            points.append(Vector(point))
        edge_u = points[1] - points[0]
        edge_v = points[2] - points[0]
        normal = edge_u.cross(edge_v)
        frame = plane_frame(points[0], normal, edge_u)
        if fallback:
            _store_state(props, frame, "NEEDS_REPAIR")
            return None
    elif definition == "FACE":
        source = resolve_source(props.source_a, visited)
        if source is not None and source["kind"] == "PLANE":
            frame = plane_frame(source["origin"], source["normal"], props.plane_axis_u)
    elif definition == "OFFSET":
        source_object = props.source_a.guide_object
        source_frame = resolve_guide_plane(source_object, visited)
        if source_frame is not None:
            sign = -1.0 if props.offset_side < 0 else 1.0
            origin, axis_u, _axis_v, normal = source_frame
            frame = plane_frame(
                origin + normal * props.offset_distance * sign,
                normal,
                axis_u,
            )
    else:
        point, status = anchor_resolution(props.plane_point_a)
        if status == "BY_ID":
            frame = plane_frame(point, props.plane_normal, props.plane_axis_u)
        elif status != "UNRESOLVABLE":
            _store_state(
                props, plane_frame(point, props.plane_normal, props.plane_axis_u), "NEEDS_REPAIR",
            )
            return None

    _store_state(props, frame, "LIVE" if frame is not None else "NEEDS_REPAIR")
    return frame


def active_plane_frame(scene):
    """Resolve the scene's active plane, including fixed world planes."""
    settings = getattr(scene, "dimensions_settings", None)
    mode = "NONE" if settings is None else getattr(settings, "active_plane_mode", "NONE")
    if mode == "GUIDE":
        return resolve_guide_plane(settings.active_plane_object)
    if mode in {"FACE", "VIEW"}:
        return plane_frame(
            settings.active_plane_origin,
            settings.active_plane_normal,
            settings.active_plane_axis_u,
        )
    if mode == "WORLD_XY":
        return plane_frame((0.0, 0.0, 0.0), (0.0, 0.0, 1.0), (1.0, 0.0, 0.0))
    if mode == "WORLD_YZ":
        return plane_frame((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0))
    if mode == "WORLD_ZX":
        return plane_frame((0.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
    return None


def constrain_point_to_plane(point, frame):
    origin, _axis_u, _axis_v, normal = frame
    point = Vector(point)
    return point - normal * (point - origin).dot(normal)


def point_within_plane_extent(point, frame, extent, tolerance=EPSILON):
    """Return whether a coplanar point lies inside the displayed square grid."""
    origin, axis_u, axis_v, _normal = frame
    delta = Vector(point) - origin
    limit = max(float(extent), 0.0) + max(float(tolerance), 0.0)
    return abs(delta.dot(axis_u)) <= limit and abs(delta.dot(axis_v)) <= limit


def would_create_plane_cycle(target, source):
    target_id = target.as_pointer() if hasattr(target, "as_pointer") else id(target)
    visited = set()
    pending = [source]
    while pending:
        plane = pending.pop()
        if plane is None:
            continue
        identity = plane.as_pointer() if hasattr(plane, "as_pointer") else id(plane)
        if identity == target_id:
            return True
        if identity in visited:
            continue
        visited.add(identity)
        props = getattr(plane, "guide_props", None)
        if props is not None and getattr(props, "plane_definition", "") == "OFFSET":
            pending.append(props.source_a.guide_object)
    return False


def plane_space_delta(raw_delta, axis, frame):
    """Resolve X/Y/Z as the active plane's U/V/normal axes."""
    raw_delta = Vector(raw_delta)
    if frame is None or axis not in {"X", "Y", "Z"}:
        return raw_delta.copy()
    direction = {"X": frame[1], "Y": frame[2], "Z": frame[3]}[axis]
    return direction * raw_delta.dot(direction)


def _store_state(props, frame, state):
    from .properties import is_read_only_dimensions_object

    owner = getattr(props, "id_data", None)
    if owner is not None and is_read_only_dimensions_object(owner):
        return
    if props.plane_state != state:
        props.plane_state = state
    if frame is not None:
        origin, axis_u, _axis_v, normal = frame
        props.last_resolved_origin = tuple(origin)
        props.plane_axis_u = tuple(axis_u)
        props.last_resolved_direction = tuple(normal)
