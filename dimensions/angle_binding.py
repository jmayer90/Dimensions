"""Persistent two-edge angle sources and derived placement geometry."""

from math import acos, pi

from mathutils import Vector
from mathutils.geometry import intersect_line_line

from .anchors import resolve_anchor, set_anchor


def set_angle_edge(props, slot, obj, vertex_indices):
    if obj is None or obj.type != "MESH" or len(vertex_indices) != 2:
        raise ValueError("Angle edge source requires one mesh edge")
    first = props.angle_a_start if slot == "A" else props.angle_b_start
    second = props.angle_a_end if slot == "A" else props.angle_b_end
    set_anchor(first, obj, int(vertex_indices[0]))
    set_anchor(second, obj, int(vertex_indices[1]))
    props.angle_source_mode = "EDGES"


def resolve_angle_source(props):
    if props.angle_source_mode == "EDGES":
        points = [
            resolve_anchor(props.angle_a_start),
            resolve_anchor(props.angle_a_end),
            resolve_anchor(props.angle_b_start),
            resolve_anchor(props.angle_b_end),
        ]
        if any(point is None for point in points):
            return None
        return derive_angle_from_world_edges(*points, props.angle_mode)

    start = resolve_anchor(props.start)
    center = resolve_anchor(props.center)
    end = resolve_anchor(props.end)
    if start is None or center is None or end is None:
        return None
    if props.angle_mode == "SUPPLEMENT":
        end = center - (end - center)
    return {
        "start": start,
        "center": center,
        "end": end,
        "arc_mode": "REFLEX" if props.angle_mode == "REFLEX" else "MINOR",
        "connected": True,
    }


def derive_angle_from_world_edges(a_start, a_end, b_start, b_end, solution="MINOR"):
    a_start, a_end = Vector(a_start), Vector(a_end)
    b_start, b_end = Vector(b_start), Vector(b_end)
    a_vector = a_end - a_start
    b_vector = b_end - b_start
    if a_vector.length < 1e-6 or b_vector.length < 1e-6:
        return None

    shared = None
    a_other = None
    b_other = None
    for a_point, a_opposite in ((a_start, a_end), (a_end, a_start)):
        for b_point, b_opposite in ((b_start, b_end), (b_end, b_start)):
            if (a_point - b_point).length <= 1e-6:
                shared = (a_point + b_point) * 0.5
                a_other = a_opposite
                b_other = b_opposite
                break
        if shared is not None:
            break

    connected = shared is not None
    if connected:
        center = shared
        first_direction = (a_other - center).normalized()
        second_direction = (b_other - center).normalized()
        first_length = (a_other - center).length
        second_length = (b_other - center).length
    else:
        first_direction = a_vector.normalized()
        second_direction = b_vector.normalized()
        closest = intersect_line_line(a_start, a_end, b_start, b_end)
        if closest is None:
            center = (a_start + a_end + b_start + b_end) * 0.25
        else:
            center = (closest[0] + closest[1]) * 0.5
        # Undirected disconnected edges default to the smaller direction angle.
        if first_direction.dot(second_direction) < 0.0:
            second_direction.negate()
        first_length = max(a_vector.length * 0.5, 0.001)
        second_length = max(b_vector.length * 0.5, 0.001)

    dot = max(-1.0, min(1.0, first_direction.dot(second_direction)))
    minor = acos(dot)
    if minor < 1e-6:
        return None
    if solution == "SUPPLEMENT":
        second_direction.negate()
        minor = pi - minor

    return {
        "start": center + first_direction * first_length,
        "center": center,
        "end": center + second_direction * second_length,
        "arc_mode": "REFLEX" if solution == "REFLEX" else "MINOR",
        "connected": connected,
        "value": (2.0 * pi - minor) if solution == "REFLEX" else minor,
    }
