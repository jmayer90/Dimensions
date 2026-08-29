"""Persistent mesh-point binding and arbitrary-plane circle fitting."""

from math import atan2, pi, sqrt

import numpy as np
from mathutils import Vector

from .anchors import anchor_resolution, set_anchor


def fit_circle_world(points, mode="FITTED", closed=True):
    """Fit a circle after a least-squares best-plane projection."""
    if len(points) < 3:
        return None
    coordinates = np.asarray([tuple(Vector(point)) for point in points], dtype=np.float64)
    centroid = coordinates.mean(axis=0)
    centered = coordinates - centroid
    _u, singular, vh = np.linalg.svd(centered, full_matrices=False)
    if len(singular) < 2 or singular[1] <= 1e-10:
        return None
    normal = vh[-1]
    dominant = int(np.argmax(np.abs(normal)))
    if normal[dominant] < 0.0:
        normal = -normal
    axis_u = vh[0]
    axis_u /= np.linalg.norm(axis_u)
    axis_v = np.cross(normal, axis_u)
    axis_v /= np.linalg.norm(axis_v)
    x = centered @ axis_u
    y = centered @ axis_v
    matrix = np.column_stack((2.0 * x, 2.0 * y, np.ones(len(points))))
    target = x * x + y * y
    solution, _residuals, rank, _singular_values = np.linalg.lstsq(matrix, target, rcond=None)
    if rank < 3:
        return None
    center_x, center_y, constant = solution
    fitted_squared = constant + center_x * center_x + center_y * center_y
    if fitted_squared <= 1e-16:
        return None
    fitted_radius = sqrt(float(fitted_squared))
    dx = x - center_x
    dy = y - center_y
    radii = np.sqrt(dx * dx + dy * dy)
    angular_order = np.argsort(np.arctan2(dy, dx))
    projected = np.column_stack((dx, dy))[angular_order]
    segment_distances = []
    for first, second in zip(projected, np.roll(projected, -1, axis=0)):
        delta = second - first
        length = float(np.linalg.norm(delta))
        if length > 1e-12:
            segment_distances.append(abs(float(first[0] * second[1] - first[1] * second[0])) / length)
    inscribed_radius = min(segment_distances) if segment_distances else float(radii.min())
    radius = {
        "INSCRIBED": inscribed_radius,
        "CIRCUMSCRIBED": float(radii.max()),
    }.get(mode, fitted_radius)
    plane_distances = centered @ normal
    error = sqrt(float(np.mean((radii - fitted_radius) ** 2 + plane_distances ** 2)))
    relative_error = error / max(fitted_radius, 1e-12)
    center = centroid + axis_u * center_x + axis_v * center_y
    angles = sorted(atan2(float(v), float(u)) % (2.0 * pi) for u, v in zip(dx, dy))
    if closed:
        sweep = 2.0 * pi
        start_angle = angles[0]
    else:
        gaps = [
            ((angles[(index + 1) % len(angles)] - angles[index]) % (2.0 * pi), index)
            for index in range(len(angles))
        ]
        largest_gap, gap_index = max(gaps)
        sweep = (2.0 * pi) - largest_gap
        start_angle = angles[(gap_index + 1) % len(angles)]
    start_direction = axis_u * np.cos(start_angle) + axis_v * np.sin(start_angle)
    return {
        "center": Vector(center),
        "normal": Vector(normal),
        "axis_u": Vector(axis_u),
        "axis_v": Vector(axis_v),
        "start_direction": Vector(start_direction),
        "radius": radius,
        "fitted_radius": fitted_radius,
        "inscribed_radius": inscribed_radius,
        "circumscribed_radius": float(radii.max()),
        "fit_error": relative_error,
        "sweep": sweep,
    }


def bind_circle_vertices(props, source_object, vertex_indices, closed=True):
    indices = tuple(dict.fromkeys(int(index) for index in vertex_indices))
    if source_object is None or source_object.type != "MESH" or len(indices) < 3:
        return None
    if any(index < 0 or index >= len(source_object.data.vertices) for index in indices):
        return None
    props.circle_source_object = source_object
    props.circle_vertices.clear()
    for index in indices:
        anchor = props.circle_vertices.add()
        set_anchor(anchor, source_object, index)
    props.circle_closed = bool(closed)
    result = evaluate_circle_binding(props)
    if result is not None:
        store_circle_fit(props, result)
    return result


def evaluate_circle_binding(props):
    points = []
    statuses = []
    for anchor in props.circle_vertices:
        world, status = anchor_resolution(anchor)
        points.append(Vector(world))
        statuses.append(status)
    fit = fit_circle_world(points, props.circle_fit_mode, props.circle_closed)
    if fit is None:
        return None
    if "UNRESOLVABLE" in statuses:
        state = "NEEDS_REPAIR"
    elif "BY_FALLBACK" in statuses or fit["fit_error"] > props.circle_fit_warning_threshold:
        state = "FALLBACK"
    else:
        state = "LIVE"
    fit["state"] = state
    fit["fit_warning"] = fit["fit_error"] > props.circle_fit_warning_threshold
    return fit


def store_circle_fit(props, fit):
    props.circle_center = tuple(fit["center"])
    props.circle_normal = tuple(fit["normal"])
    props.circle_start_direction = tuple(fit["start_direction"])
    props.circle_radius = fit["radius"]
    props.circle_sweep = fit["sweep"]
    props.circle_fit_error = fit["fit_error"]
    props.measurement_state = fit["state"]


def circle_geometry(props):
    if props.measurement_state == "CAPTURED":
        normal = Vector(props.circle_normal)
        if normal.length < 1e-8:
            normal = Vector((0.0, 0.0, 1.0))
        normal.normalize()
        axis_u = Vector(props.circle_start_direction)
        axis_u -= normal * axis_u.dot(normal)
        if axis_u.length < 1e-8:
            axis_u = normal.orthogonal()
        axis_u.normalize()
        axis_v = normal.cross(axis_u).normalized()
        return {
            "center": Vector(props.circle_center), "normal": normal,
            "axis_u": axis_u, "axis_v": axis_v, "start_direction": axis_u,
            "radius": props.circle_radius, "fitted_radius": props.circle_radius,
            "fit_error": props.circle_fit_error, "sweep": props.circle_sweep,
            "state": "CAPTURED", "fit_warning": False,
        }
    return evaluate_circle_binding(props)


def circle_value(props, fit):
    if props.circle_kind == "DIAMETER":
        return fit["radius"] * 2.0
    if props.circle_kind == "ARC_LENGTH":
        return fit["radius"] * fit["sweep"]
    return fit["radius"]
