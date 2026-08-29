"""Shared presentation mutations used by direct handles and sidebar operators."""

from math import atan2

from mathutils import Vector

from .anchors import resolve_anchor, set_object_anchor
from .dimension_geometry import get_dimension_world_geometry


def angle_radius_from_world(center_world, point_world):
    return max(0.001, (Vector(point_world) - Vector(center_world)).length)


def linear_offset_from_world(props, point_world):
    start = resolve_anchor(props.start)
    end = resolve_anchor(props.end)
    if start is None or end is None:
        return None
    geometry = get_dimension_world_geometry(
        props.dimension_type,
        start,
        end,
        Vector(props.offset_plane_normal),
        0.0,
        props.offset_angle,
        props.measurement_mode,
    )
    if geometry is None:
        return None
    delta = Vector(point_world) - geometry["line_mid_world"]
    return delta.dot(geometry["offset_direction_world"])


def apply_area_label_position(annotation, result, world_co, placement_axis):
    """Apply the established Move Label mutation without changing its source faces."""
    props = annotation.dimension_props
    world_co = Vector(world_co)
    set_object_anchor(props.end, props.area_source_object, world_co)
    props.dimension_type = placement_axis
    label_delta = world_co - Vector(result["center"])
    props.offset_distance = label_delta.length
    props.area_label_direction = (
        tuple(label_delta.normalized()) if label_delta.length > 1e-6 else (1.0, 0.0, 0.0)
    )
    props.area_placement_locked = True
    props.presentation_offset = (0.0, 0.0, 0.0)
    props.placement_initialized = False
    annotation.location = world_co


def apply_circle_label_position(annotation, fit, world_co):
    """Move a circular label in its fitted plane without changing the binding."""
    props = annotation.dimension_props
    delta = Vector(world_co) - Vector(fit["center"])
    delta -= Vector(fit["normal"]) * delta.dot(Vector(fit["normal"]))
    if delta.length < 1e-6:
        return False
    props.circle_label_distance = delta.length
    props.circle_leader_angle = atan2(delta.dot(fit["axis_v"]), delta.dot(fit["axis_u"]))
    props.presentation_offset = (0.0, 0.0, 0.0)
    props.placement_initialized = False
    annotation.location = Vector(fit["center"]) + delta
    return True
