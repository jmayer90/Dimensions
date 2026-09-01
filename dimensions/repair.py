"""Explicit, user-confirmed repair inspection and rebinding helpers."""

from mathutils import Vector

from .anchors import (
    anchor_resolution,
    dimension_source_anchors,
    refresh_dimension_anchor_resolutions,
    resolve_anchor,
    set_anchor,
    set_object_anchor,
)
from .area_binding import bind_area_face_indices, evaluate_area_binding
from .properties import is_dimension_object
from .dimension_sets import refresh_dimension_set_state, synchronize_set_member_anchor
from .circle_binding import evaluate_circle_binding, store_circle_fit
from .coordinate_dimensions import datum_frame


def _refresh_repaired_state(props):
    kind = getattr(props, "annotation_kind", "LINEAR")
    if kind == "DIMENSION_SET":
        return refresh_dimension_set_state(props)
    if kind == "CIRCLE":
        fit = evaluate_circle_binding(props)
        if fit is None:
            return "NEEDS_REPAIR"
        store_circle_fit(props, fit)
        return fit["state"]
    return refresh_dimension_anchor_resolutions(props)


def _repair_anchor_items(props):
    if getattr(props, "annotation_kind", "LINEAR") == "DIMENSION_SET":
        return tuple(
            (f"SET_{index}_{slot}", anchor)
            for index, member in enumerate(props.set_members)
            for slot, anchor in (("START", member.start), ("END", member.end))
        )
    if getattr(props, "annotation_kind", "LINEAR") == "CIRCLE":
        return tuple((f"CIRCLE_{index}", anchor) for index, anchor in enumerate(props.circle_vertices))
    return tuple(dimension_source_anchors(props))


def repair_anchor(props, name):
    return dict(_repair_anchor_items(props)).get(name)


def repair_issues(annotation):
    if not is_dimension_object(annotation):
        return ()
    props = annotation.dimension_props
    issues = []
    if getattr(props, "annotation_kind", "LINEAR") in {"COORDINATE", "ELEVATION"}:
        datum = getattr(props, "datum_object", None)
        frame = datum_frame(datum)
        if frame is None or frame[-1] != "LIVE":
            issues.append({
                "type": "DATUM", "status": "UNRESOLVABLE" if frame is None else frame[-1],
                "source_name": "Missing datum" if datum is None else datum.name,
                "world_co": Vector(props.start.world_co), "candidate": None,
            })
    for name, anchor in _repair_anchor_items(props):
        world, status = anchor_resolution(anchor)
        if status == "BY_ID":
            continue
        source_name = anchor.source_object_name or (
            anchor.target_object.name if anchor.target_object is not None else "Deleted source"
        )
        issues.append({
            "type": "ANCHOR",
            "anchor_name": name,
            "status": status,
            "source_name": source_name,
            "world_co": Vector(world),
            "candidate": suggest_vertex_candidate(anchor),
        })
    if props.annotation_kind == "AREA" and props.measurement_state != "CAPTURED" and evaluate_area_binding(props) is None:
        source = props.area_source_object
        source_name = source.name if source is not None else (props.start.source_object_name or "Deleted source")
        issues.append({
            "type": "AREA",
            "status": "UNRESOLVABLE" if source is None else "BY_FALLBACK",
            "source_name": source_name,
            "world_co": area_last_known_world(props),
            "candidate": suggest_area_candidate(props),
        })
    return tuple(issues)


def suggest_vertex_candidate(anchor):
    _world, status = anchor_resolution(anchor)
    obj = anchor.target_object
    if status == "BY_ID" or obj is None or obj.type != "MESH" or not obj.data.vertices:
        return None
    fallback = Vector(anchor.fallback_local_co)
    vertex = min(obj.data.vertices, key=lambda item: (item.co - fallback).length_squared)
    return {
        "object": obj,
        "vertex_index": vertex.index,
        "world_co": obj.matrix_world @ vertex.co,
        "label": f"{obj.name} vertex {vertex.index}",
    }


def area_last_known_world(props):
    source = props.area_source_object
    if props.area_faces:
        local = sum((Vector(item.fallback_center) for item in props.area_faces), Vector()) / len(props.area_faces)
        if source is not None:
            return source.matrix_world @ local
    return Vector(props.start.world_co)


def suggest_area_candidate(props):
    obj = props.area_source_object
    bindings = list(props.area_faces)
    if obj is None or obj.type != "MESH" or not bindings or not obj.data.polygons:
        return None
    remaining = set(range(len(obj.data.polygons)))
    chosen = []
    for binding in bindings:
        candidates = [obj.data.polygons[index] for index in remaining]
        if not candidates:
            return None
        compatible = [face for face in candidates if len(face.vertices) == binding.vertex_count]
        candidates = compatible or candidates
        center = Vector(binding.fallback_center)
        normal = Vector(binding.fallback_normal)
        area = max(binding.fallback_area, 1e-12)
        face = min(candidates, key=lambda item: (
            (Vector(item.center) - center).length_squared
            + (1.0 - abs(Vector(item.normal).dot(normal)))
            + abs(item.area - area) / area
        ))
        chosen.append(face.index)
        remaining.discard(face.index)
    center = sum((Vector(obj.data.polygons[index].center) for index in chosen), Vector()) / len(chosen)
    return {
        "object": obj,
        "face_indices": tuple(chosen),
        "world_co": obj.matrix_world @ center,
        "label": f"{obj.name} face" if len(chosen) == 1 else f"{obj.name} {len(chosen)} faces",
    }


def apply_suggested_repairs(annotation):
    """Apply available suggestions only to currently broken/fallback sources."""
    if not is_dimension_object(annotation):
        return 0
    props = annotation.dimension_props
    issues = repair_issues(annotation)
    changed = 0
    for issue in issues:
        changed += int(apply_repair_issue(annotation, issue))
    if changed:
        props.measurement_state = _refresh_repaired_state(props)
    return changed


def apply_repair_issue(annotation, issue):
    candidate = issue.get("candidate")
    if candidate is None or not is_dimension_object(annotation):
        return False
    props = annotation.dimension_props
    if issue["type"] == "AREA":
        return rebind_area_preserving_presentation(props, candidate["object"], candidate["face_indices"])
    anchor = repair_anchor(props, issue.get("anchor_name"))
    if anchor is None or anchor_resolution(anchor)[1] == "BY_ID":
        return False
    set_anchor(anchor, candidate["object"], candidate["vertex_index"])
    anchor_name = issue.get("anchor_name", "")
    if props.annotation_kind == "DIMENSION_SET" and anchor_name.startswith("SET_"):
        _prefix, index, slot = anchor_name.split("_", 2)
        synchronize_set_member_anchor(props, int(index), slot)
    props.measurement_state = _refresh_repaired_state(props)
    return True


def rebind_area_preserving_presentation(props, source, face_indices):
    if props.annotation_kind != "AREA" or props.measurement_state == "CAPTURED":
        return False
    old_label_world = resolve_anchor(props.end)
    result = bind_area_face_indices(props, source, face_indices)
    if result is None:
        return False
    props.area_value = result["area"]
    props.area_face_count = result["face_count"]
    set_object_anchor(props.start, source, result["center"])
    set_object_anchor(props.end, source, old_label_world)
    props.measurement_state = result.get("state", "LIVE")
    return True


def repair_cause(issue):
    return issue["type"], issue["status"], issue["source_name"]
