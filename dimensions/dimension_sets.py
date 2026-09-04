"""Persistent chain and baseline dimension-set relationships."""

from mathutils import Vector

from .anchors import anchor_resolution, refresh_anchor_resolution, resolve_anchor
from .dimension_geometry import get_offset_basis


SET_AXIS_RELATIVE_TOLERANCE = 0.005
SET_AXIS_ABSOLUTE_TOLERANCE = 1e-5


def automatic_baseline_spacing(props):
    """Return a readable world-space row pitch derived from resolved text size."""
    return max(0.05, float(getattr(props, "text_size", 14)) * 0.015)


def baseline_spacing(props):
    explicit = float(getattr(props, "set_spacing", 0.0))
    return explicit if explicit > 1e-6 else automatic_baseline_spacing(props)


def member_state(member):
    """Return a member's live state without writing Blender data."""
    statuses = tuple(anchor_resolution(anchor)[1] for anchor in (member.start, member.end))
    if "UNRESOLVABLE" in statuses:
        return "NEEDS_REPAIR"
    if "BY_FALLBACK" in statuses:
        return "FALLBACK"
    return "LIVE"


def refresh_member_state(member):
    for anchor in (member.start, member.end):
        refresh_anchor_resolution(anchor)
    state = member_state(member)
    if member.measurement_state != state:
        member.measurement_state = state
    return state


def dimension_set_state(props):
    states = tuple(member_state(member) for member in props.set_members)
    if "NEEDS_REPAIR" in states:
        return "NEEDS_REPAIR"
    if "FALLBACK" in states:
        return "FALLBACK"
    if dimension_set_has_invalid_geometry(props):
        return "NEEDS_REPAIR"
    return "LIVE"


def refresh_dimension_set_state(props):
    """Persist member resolution metadata from an operator or sync callback."""
    states = tuple(refresh_member_state(member) for member in props.set_members)
    if "NEEDS_REPAIR" in states:
        return "NEEDS_REPAIR"
    if "FALLBACK" in states:
        return "FALLBACK"
    if dimension_set_has_invalid_geometry(props):
        return "NEEDS_REPAIR"
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


def synchronize_set_member_anchor(props, member_index, slot):
    """Keep duplicated storage for one logical Chain joint/Baseline datum coherent."""
    if not (0 <= member_index < len(props.set_members)):
        raise IndexError("dimension-set member index out of range")
    if slot not in {"START", "END"}:
        raise ValueError("dimension-set anchor slot must be START or END")
    member = props.set_members[member_index]
    source = member.start if slot == "START" else member.end
    snapshot = anchor_snapshot(source)
    if props.set_kind == "BASELINE" and slot == "START":
        for item in props.set_members:
            _copy_anchor(snapshot, item.start)
        return
    if props.set_kind != "CHAIN":
        return
    if slot == "START" and member_index > 0:
        _copy_anchor(snapshot, props.set_members[member_index - 1].end)
    elif slot == "END" and member_index + 1 < len(props.set_members):
        _copy_anchor(snapshot, props.set_members[member_index + 1].start)


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
        if member_index == 0 and len(props.set_members) > 1:
            anchors.pop(0)
        else:
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
    if props.set_kind == "CHAIN":
        anchors = _anchors_from_chain(props)
        moved_anchor = anchors.pop(member_index + 1)
        anchors.insert(target + 1, moved_anchor)
        _rebuild_chain(props, anchors)
        props.active_set_member_index = target
    else:
        props.set_members.move(member_index, target)
        props.active_set_member_index = target
    return True


def resolved_set_members(props):
    result = []
    for index, member in enumerate(props.set_members):
        start = resolve_anchor(member.start)
        end = resolve_anchor(member.end)
        state = member_state(member)
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


def dimension_set_direction(props, members=None):
    """Return a stable shared direction derived from the first valid member."""
    members = resolved_set_members(props) if members is None else members
    axis = {
        "DELTA_X": Vector((1.0, 0.0, 0.0)),
        "DELTA_Y": Vector((0.0, 1.0, 0.0)),
        "DELTA_Z": Vector((0.0, 0.0, 1.0)),
    }.get(getattr(props, "measurement_mode", "TRUE"))
    if axis is not None:
        return axis
    for item in members:
        delta = item["end_world"] - item["start_world"]
        if delta.length >= 1e-6:
            return delta.normalized()
    return None


def dimension_set_member_issue(props, start_world, end_world, direction, datum):
    """Return why a member cannot participate in one readable shared axis."""
    start = Vector(start_world)
    end = Vector(end_world)
    datum = Vector(datum)
    direction = Vector(direction)
    if direction.length < 1e-6:
        return "ZERO_PROJECTION"
    direction.normalize()
    start_delta = start - datum
    end_delta = end - datum
    start_scalar = start_delta.dot(direction)
    end_scalar = end_delta.dot(direction)
    if getattr(props, "set_kind", "CHAIN") == "BASELINE":
        start_scalar = 0.0
        start_delta = Vector()
    projected_length = end_scalar - start_scalar
    if abs(projected_length) < 1e-6:
        return "ZERO_PROJECTION"
    scale = max(start_delta.length, end_delta.length, (end - start).length, 1.0)
    tolerance = max(SET_AXIS_ABSOLUTE_TOLERANCE, scale * SET_AXIS_RELATIVE_TOLERANCE)
    start_lateral = (start_delta - direction * start_scalar).length
    end_lateral = (end_delta - direction * end_scalar).length
    if max(start_lateral, end_lateral) > tolerance:
        return "OFF_AXIS"
    if getattr(props, "set_kind", "CHAIN") == "CHAIN" and projected_length <= 1e-6:
        return "NON_FORWARD"
    return None


def dimension_set_candidate_issue(props, start_world, end_world):
    """Validate a prospective member against an already established set axis."""
    members = resolved_set_members(props)
    direction = dimension_set_direction(props, members)
    if not members or direction is None:
        return None
    end = Vector(end_world)
    if any((end - item["end_world"]).length < 1e-6 for item in members):
        return "DUPLICATE"
    return dimension_set_member_issue(
        props,
        start_world,
        end_world,
        direction,
        members[0]["start_world"],
    )


def dimension_set_has_invalid_geometry(props):
    members = resolved_set_members(props)
    if len(members) != len(props.set_members):
        return bool(props.set_members)
    direction = dimension_set_direction(props, members)
    if direction is None:
        return bool(members)
    datum = members[0]["start_world"]
    for item in members:
        if dimension_set_member_issue(
            props, item["start_world"], item["end_world"], direction, datum,
        ) is not None:
            return True
    return False


def dimension_set_world_geometry(props):
    """Resolve aligned member geometry without mutating source anchors."""
    members = resolved_set_members(props)
    if not members:
        return ()
    datum = members[0]["start_world"]
    direction = dimension_set_direction(props, members)
    if direction is None:
        return ()
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
        issue = dimension_set_member_issue(props, start, end, direction, datum)
        line_start = datum + direction * start_scalar + offset_direction * row_offset
        line_end = datum + direction * end_scalar + offset_direction * row_offset
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
            "geometry_valid": issue is None,
            "geometry_issue": issue,
        })
    return tuple(geometry)
