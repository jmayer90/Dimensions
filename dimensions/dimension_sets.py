"""Persistent chain and baseline dimension-set relationships."""

from mathutils import Vector

from .anchors import anchor_resolution, refresh_anchor_resolution, resolve_anchor
from .dimension_geometry import get_offset_basis


def automatic_baseline_spacing(props):
    """Return a readable world-space row pitch derived from resolved text size."""
    return max(0.05, float(getattr(props, "text_size", 14)) * 0.015)


def baseline_spacing(props):
    explicit = float(getattr(props, "set_spacing", 0.0))
    return explicit if explicit > 1e-6 else automatic_baseline_spacing(props)


def refresh_member_state(member):
    for anchor in (member.start, member.end):
        refresh_anchor_resolution(anchor)
    statuses = tuple(anchor.resolution_status for anchor in (member.start, member.end))
    if "UNRESOLVABLE" in statuses:
        state = "NEEDS_REPAIR"
    elif "BY_FALLBACK" in statuses:
        state = "FALLBACK"
    else:
        state = "LIVE"
    if member.measurement_state != state:
        member.measurement_state = state
    return state


def dimension_set_state(props):
    states = tuple(refresh_member_state(member) for member in props.set_members)
    if "NEEDS_REPAIR" in states:
        return "NEEDS_REPAIR"
    if "FALLBACK" in states:
        return "FALLBACK"
    return "LIVE"


def member_anchor_pairs(props):
    return tuple((member.start, member.end) for member in props.set_members)


def anchor_snapshot(source):
    return {
        "anchor_type": source.anchor_type,
        "target_object": source.target_object,
        "vertex_index": source.vertex_index,
        "vertex_id": source.vertex_id,
        "fallback_local_co": tuple(source.fallback_local_co),
        "world_co": tuple(source.world_co),
        "resolution_status": source.resolution_status,
        "source_object_name": source.source_object_name,
    }


def _copy_anchor(source, destination):
    values = source if isinstance(source, dict) else anchor_snapshot(source)
    for name, value in values.items():
        setattr(destination, name, value)


def _anchors_from_chain(props):
    if not props.set_members:
        return []
    anchors = [props.set_members[0].start]
    anchors.extend(member.end for member in props.set_members)
    return anchors


def _rebuild_chain(props, anchors):
    anchors = [item if isinstance(item, dict) else anchor_snapshot(item) for item in anchors]
    props.set_members.clear()
    for start, end in zip(anchors, anchors[1:]):
        member = props.set_members.add()
        _copy_anchor(start, member.start)
        _copy_anchor(end, member.end)
        refresh_member_state(member)
    props.active_set_member_index = min(
        props.active_set_member_index, max(0, len(props.set_members) - 1)
    )


def insert_chain_anchor(props, member_index, anchor):
    """Split a chain member by inserting an anchor before its old end."""
    anchors = _anchors_from_chain(props)
    if not anchors or not (0 <= member_index < len(props.set_members)):
        raise IndexError("chain member index out of range")
    anchors.insert(member_index + 1, anchor)
    _rebuild_chain(props, anchors)


def delete_set_member(props, member_index):
    """Delete one member, closing a chain across the removed point."""
    if not (0 <= member_index < len(props.set_members)):
        raise IndexError("dimension-set member index out of range")
    if props.set_kind == "CHAIN":
        anchors = _anchors_from_chain(props)
        anchors.pop(member_index + 1)
        _rebuild_chain(props, anchors)
    else:
        props.set_members.remove(member_index)
        props.active_set_member_index = min(
            props.active_set_member_index, max(0, len(props.set_members) - 1)
        )


def move_set_member(props, member_index, direction):
    target = member_index + direction
    if not (0 <= member_index < len(props.set_members) and 0 <= target < len(props.set_members)):
        return False
    props.set_members.move(member_index, target)
    props.active_set_member_index = target
    if props.set_kind == "CHAIN":
        # Reordering chain endpoints preserves continuity by rebuilding from
        # the datum plus the ordered end anchors.
        anchors = _anchors_from_chain(props)
        _rebuild_chain(props, anchors)
    return True


def resolved_set_members(props):
    result = []
    for index, member in enumerate(props.set_members):
        start = resolve_anchor(member.start)
        end = resolve_anchor(member.end)
        state = refresh_member_state(member)
        if start is None or end is None:
            continue
        result.append({
            "index": index,
            "member": member,
            "start_world": Vector(start),
            "end_world": Vector(end),
            "state": state,
        })
    return tuple(result)


def dimension_set_world_geometry(props):
    """Resolve aligned member geometry without mutating source anchors."""
    members = resolved_set_members(props)
    if not members:
        return ()
    datum = members[0]["start_world"]
    candidates = [item["end_world"] - datum for item in members]
    direction_vector = max(candidates, key=lambda value: value.length_squared)
    if direction_vector.length < 1e-6:
        return ()
    direction = direction_vector.normalized()
    normal, offset_direction = get_offset_basis(
        getattr(props, "dimension_type", "ALIGNED"),
        direction,
        Vector(getattr(props, "offset_plane_normal", (0.0, 0.0, 1.0))),
    )
    pitch = baseline_spacing(props)
    geometry = []
    for item in members:
        start = item["start_world"]
        end = item["end_world"]
        start_scalar = (start - datum).dot(direction)
        end_scalar = (end - datum).dot(direction)
        if props.set_kind == "BASELINE":
            start_scalar = 0.0
            row_offset = props.offset_distance + item["index"] * pitch
        else:
            row_offset = props.offset_distance
        line_start = datum + direction * start_scalar + offset_direction * row_offset
        line_end = datum + direction * end_scalar + offset_direction * row_offset
        if (line_end - line_start).length < 1e-6:
            continue
        geometry.append({
            **item,
            "measure_start_world": start,
            "measure_end_world": end,
            "measure_direction_world": direction,
            "plane_normal_world": normal,
            "offset_direction_world": offset_direction,
            "offset_distance": row_offset,
            "offset_angle": 0.0,
            "line_start_world": line_start,
            "line_end_world": line_end,
            "line_mid_world": (line_start + line_end) * 0.5,
            "value": abs(end_scalar - start_scalar),
            "measurement_mode": "TRUE",
        })
    return tuple(geometry)
