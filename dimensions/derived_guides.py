"""Resolution and binding for persistent derived construction guides."""

from math import floor
from mathutils import Quaternion, Vector

from .anchors import anchor_resolution, resolve_anchor, set_world_anchor
from .area_binding import _evaluate_faces, _faces_by_id, ensure_bmesh_face_ids, ensure_mesh_face_ids


EPSILON = 1e-6


def bind_edge_source(source, obj, edge_index):
    if obj is None or obj.type != "MESH":
        return False
    from .anchors import set_anchor

    if obj.mode == "EDIT":
        import bmesh

        bm = bmesh.from_edit_mesh(obj.data)
        bm.edges.ensure_lookup_table()
        if not (0 <= edge_index < len(bm.edges)):
            return False
        edge = bm.edges[edge_index]
        v0 = edge.verts[0].index
        v1 = edge.verts[1].index
    else:
        if not (0 <= edge_index < len(obj.data.edges)):
            return False
        edge = obj.data.edges[edge_index]
        v0 = edge.vertices[0]
        v1 = edge.vertices[1]

    source.kind = "EDGE"
    source.target_object = obj
    source.guide_object = None
    set_anchor(source.start, obj, v0)
    set_anchor(source.end, obj, v1)
    source.source_name = obj.name
    return True


def bind_guide_source(source, guide):
    if guide is None or not getattr(getattr(guide, "guide_props", None), "enabled", False):
        return False
    source.kind = "GUIDE"
    source.target_object = None
    source.guide_object = guide
    source.source_name = guide.name
    return True


def bind_face_source(source, obj, face_index):
    if obj is None or obj.type != "MESH":
        return False

    if obj.mode == "EDIT":
        import bmesh

        bm = bmesh.from_edit_mesh(obj.data)
        bm.faces.ensure_lookup_table()
        if not (0 <= face_index < len(bm.faces)):
            return False
        face = bm.faces[face_index]
        source.kind = "FACE"
        source.target_object = obj
        source.guide_object = None
        source.face_id = ensure_bmesh_face_ids(obj, [face_index])[0]
        source.face_vertex_count = len(face.verts)
        source.fallback_center = tuple(face.calc_center_median())
        source.fallback_normal = tuple(face.normal)
        source.source_name = obj.name
        return True

    if not (0 <= face_index < len(obj.data.polygons)):
        return False
    polygon = obj.data.polygons[face_index]
    source.kind = "FACE"
    source.target_object = obj
    source.guide_object = None
    source.face_id = ensure_mesh_face_ids(obj.data, [face_index])[0]
    source.face_vertex_count = len(polygon.vertices)
    source.fallback_center = tuple(polygon.center)
    source.fallback_normal = tuple(polygon.normal)
    source.source_name = obj.name
    return True


def bind_source_from_snap(source, snap):
    if snap is None:
        return False
    if snap.get("guide_object") is not None and snap.get("type") == "GUIDE":
        return bind_guide_source(source, snap["guide_object"])
    obj = snap.get("object")
    if obj is not None and snap.get("type") == "EDGE":
        return bind_edge_source(source, obj, snap.get("edge_index", -1))
    if obj is not None and snap.get("type") == "FACE":
        return bind_face_source(source, obj, snap.get("face_index", -1))
    return False


def source_geometry_from_snap(snap):
    if snap is None:
        return None
    from .inference import snap_line, snap_plane

    line = snap_line(snap)
    if line is not None:
        return {"kind": "LINE", "origin": line[0], "direction": line[1]}
    plane = snap_plane(snap)
    if plane is not None:
        return {"kind": "PLANE", "origin": plane[0], "normal": plane[1]}
    return None


def offset_preview_line(source, distance, side, direction):
    return _offset_line(source, distance, side, Vector(direction))


def centerline_preview(first, second, direction):
    return _centerline(first, second, Vector(direction))


def resolve_source(source, visited=None):
    """Resolve one derived-guide source without persisting dependency state."""
    geometry, state = source_resolution(source, visited)
    return geometry if state == "LIVE" else None


def source_resolution(source, visited=None):
    """Return current source geometry and its pure resolution state."""
    kind = getattr(source, "kind", "NONE")
    if kind == "EDGE":
        start, start_status = anchor_resolution(source.start)
        end, end_status = anchor_resolution(source.end)
        if start_status != "BY_ID" or end_status != "BY_ID" or (end - start).length < EPSILON:
            return None, "NEEDS_REPAIR"
        return {"kind": "LINE", "origin": start, "direction": (end - start).normalized()}, "LIVE"
    if kind == "GUIDE":
        guide = getattr(source, "guide_object", None)
        if getattr(getattr(guide, "guide_props", None), "kind", "") == "PLANE":
            from .guide_planes import guide_plane_resolution

            frame, state = guide_plane_resolution(guide, visited)
            if state != "LIVE" or frame is None:
                return None, state
            return {"kind": "PLANE", "origin": frame[0], "normal": frame[3]}, "LIVE"
        line, state = derived_guide_resolution(guide, visited)
        if state != "LIVE" or line is None:
            return None, state
        return {"kind": "LINE", "origin": line[0], "direction": line[1]}, "LIVE"
    if kind == "FACE":
        obj = getattr(source, "target_object", None)
        if obj is None or obj.type != "MESH":
            return None, "NEEDS_REPAIR"
        matches = _faces_by_id(obj).get(getattr(source, "face_id", 0), ())
        if len(matches) != 1 or len(matches[0].verts) != source.face_vertex_count:
            return None, "NEEDS_REPAIR"
        result = _evaluate_faces(obj, matches)
        if result is None:
            return None, "NEEDS_REPAIR"
        return {"kind": "PLANE", "origin": result["center"], "normal": result["normal"]}, "LIVE"
    return None, "NEEDS_REPAIR"


def resolve_derived_guide(guide, visited=None):
    """Resolve an infinite guide line without mutating persistent state."""
    line, state = derived_guide_resolution(guide, visited)
    return line if state == "LIVE" else None


def derived_guide_resolution(guide, visited=None):
    """Return the current guide line and pure dependency state."""
    if guide is None or not getattr(getattr(guide, "guide_props", None), "enabled", False):
        return None, "NEEDS_REPAIR"
    props = guide.guide_props
    if getattr(props, "kind", "GUIDE") != "GUIDE":
        return None, "NEEDS_REPAIR"
    visited = set() if visited is None else set(visited)
    identity = guide.as_pointer() if hasattr(guide, "as_pointer") else id(guide)
    if identity in visited:
        return None, "CYCLE"
    visited.add(identity)
    if not getattr(props, "derived", False):
        result = _fixed_line(props)
        return result, "LIVE" if result is not None else "NEEDS_REPAIR"

    if props.derivation_mode == "SPACING":
        lines, state = spacing_guide_resolution(guide, visited)
        return (None if not lines else lines[0]), state

    source_a, source_a_state = source_resolution(props.source_a, visited)
    source_b, source_b_state = (
        source_resolution(props.source_b, visited)
        if props.derivation_mode == "CENTERLINE" else (None, "LIVE")
    )
    if "CYCLE" in {source_a_state, source_b_state}:
        return None, "CYCLE"
    if source_a is None or (props.derivation_mode == "CENTERLINE" and source_b is None):
        return None, "NEEDS_REPAIR"

    if props.derivation_mode == "CENTERLINE":
        result = _centerline(source_a, source_b, Vector(props.derived_direction))
    elif props.derivation_mode == "ANGULAR":
        pivot, pivot_status = anchor_resolution(props.construction_pivot)
        result = None if pivot_status != "BY_ID" else _angular_line(
            source_a, pivot, props.guide_angle, Vector(props.derived_direction),
        )
    else:
        result = _offset_line(source_a, props.offset_distance, props.offset_side, Vector(props.derived_direction))
    return result, "LIVE" if result is not None else "NEEDS_REPAIR"


def angular_preview_line(source, pivot, angle, plane_normal):
    return _angular_line(source, Vector(pivot), angle, Vector(plane_normal))


def _angular_line(source, pivot, angle, plane_normal):
    if pivot is None or source is None:
        return None
    if source["kind"] == "PLANE":
        normal = Vector(source["normal"]).normalized()
        direction = _plane_tangent(normal, plane_normal)
    else:
        direction = Vector(source["direction"]).normalized()
        normal = Vector(plane_normal)
        normal = normal - direction * normal.dot(direction)
        if normal.length < EPSILON:
            normal = direction.cross(Vector((0.0, 0.0, 1.0)))
        if normal.length < EPSILON:
            normal = direction.cross(Vector((0.0, 1.0, 0.0)))
        if normal.length < EPSILON:
            return None
        normal.normalize()
    if direction is None:
        return None
    rotated = Quaternion(normal, float(angle)) @ direction
    return Vector(pivot), rotated.normalized()


def spacing_definition(props):
    count = max(2, int(props.spacing_count))
    interval = max(EPSILON, float(props.spacing_interval))
    extent = max(EPSILON, float(props.spacing_extent))
    if props.spacing_mode == "EXTENT":
        count = max(2, floor(extent / interval) + 1)
    elif props.spacing_mode == "DISTRIBUTE":
        interval = extent / (count - 1)
    return interval, count


def spaced_guide_lines(guide, visited=None):
    """Resolve repeated guide lines without mutating persistent state."""
    lines, state = spacing_guide_resolution(guide, visited)
    return lines if state == "LIVE" else ()


def spacing_guide_resolution(guide, visited=None):
    """Return repeated guide lines and their pure dependency state."""
    if guide is None or not getattr(getattr(guide, "guide_props", None), "enabled", False):
        return (), "NEEDS_REPAIR"
    props = guide.guide_props
    if not props.derived or props.derivation_mode != "SPACING":
        return (), "NEEDS_REPAIR"
    source, source_state = source_resolution(props.source_a, visited)
    if source_state == "CYCLE":
        return (), "CYCLE"
    origin, origin_status = anchor_resolution(props.construction_pivot)
    if source is None or origin_status != "BY_ID":
        return (), "NEEDS_REPAIR"
    if source["kind"] == "PLANE":
        direction = _plane_tangent(source["normal"], Vector(props.derived_direction))
    else:
        direction = Vector(source["direction"]).normalized()
    if direction is None:
        return (), "NEEDS_REPAIR"
    offset = Vector(props.derived_direction) - direction * Vector(props.derived_direction).dot(direction)
    distributed_extent = None
    if props.spacing_mode == "DISTRIBUTE":
        end, end_status = anchor_resolution(props.spacing_end)
        if end_status != "BY_ID":
            return (), "NEEDS_REPAIR"
        between = Vector(end) - Vector(origin)
        perpendicular_between = between - direction * between.dot(direction)
        if perpendicular_between.length >= EPSILON:
            offset = perpendicular_between
            distributed_extent = perpendicular_between.length
    if offset.length < EPSILON:
        offset = direction.cross(Vector((0.0, 0.0, 1.0)))
    if offset.length < EPSILON:
        offset = direction.cross(Vector((0.0, 1.0, 0.0)))
    if offset.length < EPSILON:
        return (), "NEEDS_REPAIR"
    offset.normalize()
    interval, count = spacing_definition(props)
    if distributed_extent is not None:
        interval = distributed_extent / (count - 1)
    lines = tuple((Vector(origin) + offset * interval * index, direction.copy()) for index in range(count))
    return lines, "LIVE"


def would_create_cycle(target, source_guides):
    target_id = target.as_pointer() if hasattr(target, "as_pointer") else id(target)
    pending = list(source_guides)
    visited = set()
    while pending:
        guide = pending.pop()
        if guide is None:
            continue
        identity = guide.as_pointer() if hasattr(guide, "as_pointer") else id(guide)
        if identity == target_id:
            return True
        if identity in visited:
            continue
        visited.add(identity)
        props = getattr(guide, "guide_props", None)
        if props is None or not getattr(props, "derived", False):
            continue
        for source in (props.source_a, props.source_b):
            if getattr(source, "kind", "NONE") == "GUIDE":
                pending.append(source.guide_object)
    return False


def detach_derived_guide(guide):
    line = resolve_derived_guide(guide)
    if line is None or not getattr(guide.guide_props, "derived", False):
        return False
    props = guide.guide_props
    origin, direction = line
    set_world_anchor(props.start, origin)
    set_world_anchor(props.end, origin + direction)
    props.axis = "ALIGNED"
    props.derived = False
    props.derivation_mode = "NONE"
    _clear_source(props.source_a)
    _clear_source(props.source_b)
    _set_state(props, "LIVE")
    return True


def _fixed_line(props):
    start = resolve_anchor(props.start)
    if start is None:
        return None
    axis = getattr(props, "axis", "ALIGNED")
    if axis in {"X", "Y", "Z"}:
        direction = {"X": Vector((1.0, 0.0, 0.0)), "Y": Vector((0.0, 1.0, 0.0)), "Z": Vector((0.0, 0.0, 1.0))}[axis]
        return start, direction
    end = resolve_anchor(props.end)
    if end is None or (end - start).length < EPSILON:
        return None
    return start, (end - start).normalized()


def _offset_line(source, distance, side, stored_direction):
    sign = -1.0 if side < 0 else 1.0
    if source["kind"] == "PLANE":
        direction = _plane_tangent(source["normal"], stored_direction)
        if direction is None:
            return None
        return source["origin"] + source["normal"] * float(distance) * sign, direction
    direction = source["direction"]
    offset_direction = stored_direction - direction * stored_direction.dot(direction)
    if offset_direction.length < EPSILON:
        offset_direction = direction.cross(Vector((0.0, 0.0, 1.0)))
    if offset_direction.length < EPSILON:
        offset_direction = direction.cross(Vector((0.0, 1.0, 0.0)))
    if offset_direction.length < EPSILON:
        return None
    return source["origin"] + offset_direction.normalized() * float(distance) * sign, direction


def _centerline(first, second, stored_direction):
    if first["kind"] != second["kind"]:
        return None
    if first["kind"] == "LINE":
        if abs(first["direction"].dot(second["direction"])) < 1.0 - 1e-5:
            return None
        delta = second["origin"] - first["origin"]
        perpendicular = delta - first["direction"] * delta.dot(first["direction"])
        return first["origin"] + perpendicular * 0.5, first["direction"]
    if abs(first["normal"].dot(second["normal"])) < 1.0 - 1e-5:
        return None
    direction = _plane_tangent(first["normal"], stored_direction)
    if direction is None:
        return None
    signed = (second["origin"] - first["origin"]).dot(first["normal"])
    return first["origin"] + first["normal"] * signed * 0.5, direction


def _plane_tangent(normal, preferred):
    direction = preferred - normal * preferred.dot(normal)
    if direction.length < EPSILON:
        direction = normal.cross(Vector((0.0, 0.0, 1.0)))
    if direction.length < EPSILON:
        direction = normal.cross(Vector((0.0, 1.0, 0.0)))
    return None if direction.length < EPSILON else direction.normalized()


def _clear_source(source):
    source.kind = "NONE"
    source.target_object = None
    source.guide_object = None


def store_derived_guide_resolution(props, line, state):
    """Persist a computed guide resolution from the scene-sync write phase."""
    from .properties import is_read_only_dimensions_object

    owner = getattr(props, "id_data", None)
    if owner is not None and is_read_only_dimensions_object(owner):
        return
    _set_state(props, state)
    if line is not None:
        props.last_resolved_origin = tuple(line[0])
        props.last_resolved_direction = tuple(line[1])


def _set_state(props, state):
    if hasattr(props, "derived_state") and props.derived_state != state:
        props.derived_state = state
