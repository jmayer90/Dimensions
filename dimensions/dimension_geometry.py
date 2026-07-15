"""Pure world-space geometry calculations for persistent dimensions."""

from math import acos, cos, pi, sin
from mathutils import Quaternion, Vector


_AXIS_CANDIDATES = (
    Vector((1.0, 0.0, 0.0)),
    Vector((0.0, 1.0, 0.0)),
    Vector((0.0, 0.0, 1.0)),
)


def get_measure_world_points(measurement_mode, start_world, end_world):
    delta = end_world - start_world
    axis_indices = {"DELTA_X": 0, "DELTA_Y": 1, "DELTA_Z": 2}
    axis_index = axis_indices.get(measurement_mode)
    if axis_index is None:
        return start_world, end_world, delta.length
    projected_delta = Vector((0.0, 0.0, 0.0))
    projected_delta[axis_index] = delta[axis_index]
    return start_world, start_world + projected_delta, abs(delta[axis_index])


def get_dimension_world_geometry(
    dimension_type,
    start_world,
    end_world,
    plane_normal,
    offset_distance,
    offset_angle=0.0,
    measurement_mode="TRUE",
):
    measure_start_world, measure_end_world, value = get_measure_world_points(
        measurement_mode,
        start_world,
        end_world,
    )
    measure_vector = measure_end_world - measure_start_world
    if measure_vector.length < 1e-6:
        return None

    measure_direction = measure_vector.normalized()
    stable_plane_normal, offset_direction = get_offset_basis(
        dimension_type,
        measure_direction,
        plane_normal,
    )
    if abs(offset_angle) >= 1e-6:
        offset_rotation = Quaternion(measure_direction, offset_angle)
        offset_direction = offset_rotation @ offset_direction
        stable_plane_normal = measure_direction.cross(offset_direction).normalized()
    if offset_direction.length < 1e-6:
        return None

    offset_direction.normalize()
    offset_vector = offset_direction * offset_distance
    line_start_world = measure_start_world + offset_vector
    line_end_world = measure_end_world + offset_vector
    return {
        "measure_start_world": measure_start_world,
        "measure_end_world": measure_end_world,
        "measure_direction_world": measure_direction,
        "plane_normal_world": stable_plane_normal,
        "offset_direction_world": offset_direction,
        "offset_distance": offset_distance,
        "offset_angle": offset_angle,
        "line_start_world": line_start_world,
        "line_end_world": line_end_world,
        "line_mid_world": (line_start_world + line_end_world) * 0.5,
        "value": value,
        "measurement_mode": measurement_mode,
    }


def get_angle_world_geometry(start_world, center_world, end_world, radius, mode="MINOR", steps=48):
    """Build a true world-space arc between two rays."""
    first = start_world - center_world
    second = end_world - center_world
    if first.length < 1e-6 or second.length < 1e-6 or radius <= 0.0:
        return None
    first_direction = first.normalized()
    second_direction = second.normalized()
    dot = max(-1.0, min(1.0, first_direction.dot(second_direction)))
    minor_angle = acos(dot)
    if minor_angle < 1e-6:
        return None

    normal = first_direction.cross(second_direction)
    if normal.length < 1e-6:
        fallback = min(_AXIS_CANDIDATES, key=lambda axis: abs(axis.dot(first_direction)))
        normal = first_direction.cross(fallback)
    normal.normalize()
    tangent = normal.cross(first_direction).normalized()

    if mode == "REFLEX":
        tangent.negate()
        sweep = (2.0 * pi) - minor_angle
    else:
        sweep = minor_angle

    arc_points = [
        center_world
        + (first_direction * cos(sweep * index / steps) + tangent * sin(sweep * index / steps)) * radius
        for index in range(steps + 1)
    ]
    label_angle = sweep * 0.5
    label_world = center_world + (
        first_direction * cos(label_angle) + tangent * sin(label_angle)
    ) * (radius * 1.18)
    return {
        "arc_points_world": arc_points,
        "label_world": label_world,
        "start_ray_world": start_world,
        "end_ray_world": end_world,
        "center_world": center_world,
        "value": sweep,
        "minor_value": minor_angle,
        "plane_normal_world": normal,
    }


def get_offset_basis(extension_axis, measure_direction, plane_normal):
    stable_plane_normal = sanitize_plane_normal(measure_direction, plane_normal)
    preferred_offset_direction = stable_plane_normal.cross(measure_direction)
    axis_directions = {
        "X": Vector((1.0, 0.0, 0.0)),
        "Y": Vector((0.0, 1.0, 0.0)),
        "Z": Vector((0.0, 0.0, 1.0)),
    }
    candidates = []
    for axis_name, axis_direction in axis_directions.items():
        perpendicular_axis = axis_direction - measure_direction * axis_direction.dot(measure_direction)
        if perpendicular_axis.length >= 1e-6:
            candidates.append((axis_name, perpendicular_axis.normalized()))
    if not candidates:
        return stable_plane_normal, preferred_offset_direction

    matching_candidate = None
    if extension_axis in axis_directions:
        matching_candidate = next(
            (candidate for name, candidate in candidates if name == extension_axis),
            None,
        )
    if matching_candidate is None:
        preferred_direction = preferred_offset_direction.normalized()
        _axis_name, matching_candidate = max(
            candidates,
            key=lambda item: abs(item[1].dot(preferred_direction)),
        )
        if matching_candidate.dot(preferred_direction) < 0.0:
            matching_candidate.negate()

    offset_direction = matching_candidate
    stable_plane_normal = measure_direction.cross(offset_direction).normalized()
    return stable_plane_normal, offset_direction


def sanitize_plane_normal(measure_direction, plane_normal):
    candidate = plane_normal.normalized() if plane_normal.length > 1e-6 else Vector((0.0, 0.0, 1.0))
    if abs(candidate.dot(measure_direction)) < 0.98:
        return candidate
    fallback = min(_AXIS_CANDIDATES, key=lambda axis: abs(axis.dot(measure_direction)))
    return fallback.normalized()
