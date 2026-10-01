"""World-space stroke specs for generated linear-dimension output.

This adapter deliberately shares the persistent-anchor and dimension-frame logic
with the live annotation. It emits dimension linework and legible vector-font
labels as world-space strokes for the Grease Pencil backend.
"""

from dataclasses import dataclass, replace
from math import cos, degrees, sin, tau

from mathutils import Vector

from .anchors import anchor_resolution, dimension_source_anchors, resolve_anchor
from .angle_binding import resolve_angle_source
from .area_binding import area_label_world, evaluate_area_binding
from .dimension_geometry import get_angle_world_geometry, get_dimension_world_geometry
from .grease_pencil_output import GreasePencilOutputSpec, OutputStroke
from .stroke_font import text_block_dimensions, text_strokes
from .units import format_area, format_dual_length, format_length


TEXT_OUTPUT_SUPPORTED = True


def annotation_output_state(dimension_object):
    """Return the current authoritative output state without trusting cached RNA state."""
    props = getattr(dimension_object, "dimension_props", None)
    if props is None or not getattr(props, "enabled", False):
        return "NEEDS_REPAIR"
    cached_state = getattr(props, "measurement_state", "LIVE")
    if cached_state not in {"LIVE", "CAPTURED"}:
        return cached_state
    kind = getattr(props, "annotation_kind", "LINEAR")
    if kind == "AREA":
        if props.measurement_state == "CAPTURED":
            return "CAPTURED"
        result = evaluate_area_binding(props)
        return "NEEDS_REPAIR" if result is None else result.get("state", "LIVE")
    statuses = [
        anchor_resolution(anchor)[1]
        for _name, anchor in dimension_source_anchors(props)
    ]
    if "UNRESOLVABLE" in statuses:
        return "NEEDS_REPAIR"
    if "BY_FALLBACK" in statuses:
        return "FALLBACK"
    return "LIVE"


@dataclass(frozen=True)
class WorldSizingPolicy:
    """Explicit world-space presentation sizing for generated line work."""

    line_width: float
    arrow_size: float

    def __post_init__(self):
        line_width = float(self.line_width)
        arrow_size = float(self.arrow_size)
        if line_width <= 0.0:
            raise ValueError("line_width must be greater than zero")
        if arrow_size <= 0.0:
            raise ValueError("arrow_size must be greater than zero")
        object.__setattr__(self, "line_width", line_width)
        object.__setattr__(self, "arrow_size", arrow_size)


@dataclass(frozen=True)
class LinearLabelLayout:
    """Vector label strokes plus an optional replacement dimension line."""

    strokes: tuple
    dimension_line_strokes: tuple = ()


def _reading_view_axes(camera, label_normal):
    """Return the right, up, and toward-viewer axes a label is read in."""
    if camera is not None and getattr(camera, "type", None) == "CAMERA":
        rotation = camera.matrix_world.to_quaternion()
        return (
            rotation @ Vector((1.0, 0.0, 0.0)),
            rotation @ Vector((0.0, 1.0, 0.0)),
            rotation @ Vector((0.0, 0.0, 1.0)),
        )
    # Without a camera, read the label from Blender's Top, Front, or Right view,
    # whichever looks most directly at the label plane, as a drafter would.
    dominant_axis = max(range(3), key=lambda index: abs(label_normal[index]))
    if dominant_axis == 2:
        return Vector((1.0, 0.0, 0.0)), Vector((0.0, 1.0, 0.0)), Vector((0.0, 0.0, 1.0))
    if dominant_axis == 1:
        return Vector((1.0, 0.0, 0.0)), Vector((0.0, 0.0, 1.0)), Vector((0.0, -1.0, 0.0))
    return Vector((0.0, 1.0, 0.0)), Vector((0.0, 0.0, 1.0)), Vector((1.0, 0.0, 0.0))


def _readable_axes(x_axis, y_axis, camera=None):
    """Flip label axes so text is neither mirrored nor upside down, like the overlay."""
    x_axis = Vector(x_axis)
    y_axis = Vector(y_axis)
    right, _up, toward_viewer = _reading_view_axes(camera, x_axis.cross(y_axis))
    if x_axis.cross(y_axis).dot(toward_viewer) < 0.0:
        y_axis.negate()
    if x_axis.dot(right) < -1e-6:
        x_axis.negate()
        y_axis.negate()
    return x_axis, y_axis


def _camera_axes(camera, fallback_x, fallback_y):
    """Return stable world-space axes for vector labels facing the camera."""
    if camera is not None and getattr(camera, "type", None) == "CAMERA":
        rotation = camera.matrix_world.to_quaternion()
        return (
            (rotation @ Vector((1.0, 0.0, 0.0))).normalized(),
            (rotation @ Vector((0.0, 1.0, 0.0))).normalized(),
        )
    x_axis = Vector(fallback_x)
    if x_axis.length <= 1e-6:
        x_axis = Vector((1.0, 0.0, 0.0))
    x_axis.normalize()
    y_axis = Vector(fallback_y)
    y_axis = y_axis - x_axis * y_axis.dot(x_axis)
    if y_axis.length <= 1e-6:
        y_axis = Vector((0.0, 0.0, 1.0))
        y_axis = y_axis - x_axis * y_axis.dot(x_axis)
    if y_axis.length <= 1e-6:
        y_axis = x_axis.orthogonal()
    y_axis.normalize()
    return _readable_axes(x_axis, y_axis)


def _text_strokes_at(text, position, text_height, line_width, color, camera=None,
                     fallback_x=(1.0, 0.0, 0.0), fallback_y=(0.0, 0.0, 1.0)):
    x_axis, y_axis = _camera_axes(camera, fallback_x, fallback_y)
    block_width, block_height = text_block_dimensions(text, text_height)
    origin = Vector(position) + y_axis * (block_height * 0.5 - text_height)
    return tuple(
        OutputStroke(points=polyline, color=color, line_width=line_width)
        for polyline in text_strokes(text, origin, x_axis, y_axis, text_height, "CENTER")
    )


def _open_arrow_strokes(point, direction, perpendicular, color, sizing):
    left = point + direction * sizing.arrow_size + perpendicular * sizing.arrow_size * 0.45
    right = point + direction * sizing.arrow_size - perpendicular * sizing.arrow_size * 0.45
    return (
        OutputStroke((point, left), color, sizing.line_width),
        OutputStroke((point, right), color, sizing.line_width),
    )


def _architectural_tick_stroke(point, direction, perpendicular, color, sizing):
    tick_direction = (direction + perpendicular).normalized()
    half_length = sizing.arrow_size * 0.5
    return OutputStroke(
        (point - tick_direction * half_length, point + tick_direction * half_length),
        color,
        sizing.line_width,
    )


def _endpoint_strokes(point, direction, perpendicular, style, color, sizing):
    if style == "ARCHITECTURAL_TICK":
        return (_architectural_tick_stroke(point, direction, perpendicular, color, sizing),)
    if style == "NONE":
        return ()
    if style == "DOT":
        radius = sizing.arrow_size * 0.38
        points = tuple(
            point + (direction * cos(index * tau / 12.0) + perpendicular * sin(index * tau / 12.0)) * radius
            for index in range(13)
        )
        return (
            OutputStroke(points, color, sizing.line_width),
            OutputStroke((point - direction * radius, point + direction * radius), color, sizing.line_width),
            OutputStroke((point - perpendicular * radius, point + perpendicular * radius), color, sizing.line_width),
        )
    strokes = _open_arrow_strokes(point, direction, perpendicular, color, sizing)
    if style == "FILLED":
        left = strokes[0].points[-1]
        right = strokes[1].points[-1]
        return strokes + (
            OutputStroke((left, right), color, sizing.line_width),
            OutputStroke((point + direction * sizing.arrow_size * 0.5 - perpendicular * sizing.arrow_size * 0.22, point + direction * sizing.arrow_size * 0.5 + perpendicular * sizing.arrow_size * 0.22), color, sizing.line_width),
        )
    return strokes


def _resolved_endpoint_style(props, property_name):
    style = getattr(props, property_name, "OPEN")
    if style == "OPEN" and getattr(props, "arrow_end_style", "ARROW") == "ARCHITECTURAL_TICK":
        return "ARCHITECTURAL_TICK"
    return style


def linear_dimension_output_spec(dimension_object, source_key, sizing):
    """Convert one live linear dimension to a world-space Grease Pencil spec.

    ``sizing`` must be supplied by the caller because overlay pixels have no
    view-independent conversion to Grease Pencil world-space stroke widths.
    ``None`` means the object cannot currently resolve to a valid line dimension.
    """
    if not isinstance(sizing, WorldSizingPolicy):
        raise TypeError("sizing must be a WorldSizingPolicy")
    if not isinstance(source_key, str) or not source_key.strip():
        raise ValueError("source_key must be a non-empty string")

    props = getattr(dimension_object, "dimension_props", None)
    if (
        props is None
        or not getattr(props, "enabled", False)
        or getattr(props, "annotation_kind", "LINEAR") != "LINEAR"
        or annotation_output_state(dimension_object) not in {"LIVE", "CAPTURED"}
    ):
        return None

    start_world = resolve_anchor(props.start)
    end_world = resolve_anchor(props.end)
    if start_world is None or end_world is None:
        return None

    geometry = get_dimension_world_geometry(
        props.dimension_type,
        start_world,
        end_world,
        Vector(props.offset_plane_normal),
        props.offset_distance,
        props.offset_angle,
        props.measurement_mode,
    )
    if geometry is None:
        return None

    presentation_offset = Vector(getattr(props, "presentation_offset", (0.0, 0.0, 0.0)))
    line_start = geometry["line_start_world"] + presentation_offset
    line_end = geometry["line_end_world"] + presentation_offset
    line_direction = (line_end - line_start).normalized()
    perpendicular = geometry["offset_direction_world"].normalized()
    color = tuple(float(channel) for channel in props.color)
    pixel_to_world = sizing.arrow_size / max(float(getattr(props, "arrow_size", 10.0)), 1e-6)
    gap = float(getattr(props, "extension_gap", 0.0)) * pixel_to_world
    overshoot = float(getattr(props, "extension_overshoot", 0.0)) * pixel_to_world
    start_extension = line_start - start_world
    end_extension = line_end - end_world
    if start_extension.length <= 1e-6:
        start_extension = perpendicular
    else:
        start_extension.normalize()
    if end_extension.length <= 1e-6:
        end_extension = perpendicular
    else:
        end_extension.normalize()
    strokes = [
        OutputStroke((line_start, line_end), color, sizing.line_width),
        OutputStroke((start_world + start_extension * min(gap, (line_start - start_world).length), line_start + start_extension * overshoot), color, sizing.line_width),
        OutputStroke((end_world + end_extension * min(gap, (line_end - end_world).length), line_end + end_extension * overshoot), color, sizing.line_width),
    ]
    strokes.extend(
        _endpoint_strokes(
            line_start,
            line_direction,
            perpendicular,
            _resolved_endpoint_style(props, "start_end_style"),
            color,
            sizing,
        )
    )
    strokes.extend(
        _endpoint_strokes(
            line_end,
            -line_direction,
            perpendicular,
            _resolved_endpoint_style(props, "end_end_style"),
            color,
            sizing,
        )
    )
    return GreasePencilOutputSpec(
        source_key=source_key,
        strokes=tuple(strokes),
        name=getattr(dimension_object, "name", "Dimensions Output"),
    )


def angle_dimension_output_spec(dimension_object, source_key, sizing):
    """Convert a live two-edge or three-point angle into world-space strokes."""
    if not isinstance(sizing, WorldSizingPolicy):
        raise TypeError("sizing must be a WorldSizingPolicy")
    if not isinstance(source_key, str) or not source_key.strip():
        raise ValueError("source_key must be a non-empty string")

    props = getattr(dimension_object, "dimension_props", None)
    if (
        props is None
        or not getattr(props, "enabled", False)
        or getattr(props, "annotation_kind", "LINEAR") != "ANGLE"
        or annotation_output_state(dimension_object) not in {"LIVE", "CAPTURED"}
    ):
        return None
    source = resolve_angle_source(props)
    if source is None:
        return None
    presentation_offset = Vector(getattr(props, "presentation_offset", (0.0, 0.0, 0.0)))
    start = Vector(source["start"]) + presentation_offset
    center = Vector(source["center"]) + presentation_offset
    end = Vector(source["end"]) + presentation_offset
    geometry = get_angle_world_geometry(
        start,
        center,
        end,
        float(props.angle_radius),
        source.get("arc_mode", "MINOR"),
    )
    if geometry is None:
        return None
    color = tuple(float(channel) for channel in props.color)
    strokes = [
        OutputStroke((center, start), color, sizing.line_width),
        OutputStroke((center, end), color, sizing.line_width),
        OutputStroke(tuple(geometry["arc_points_world"]), color, sizing.line_width),
    ]
    return GreasePencilOutputSpec(
        source_key=source_key,
        strokes=tuple(strokes),
        name=getattr(dimension_object, "name", "Dimensions Output"),
    )


def area_dimension_output_spec(dimension_object, source_key, sizing):
    """Convert a valid live or captured Area into a leader and center marker."""
    if not isinstance(sizing, WorldSizingPolicy):
        raise TypeError("sizing must be a WorldSizingPolicy")
    if not isinstance(source_key, str) or not source_key.strip():
        raise ValueError("source_key must be a non-empty string")

    props = getattr(dimension_object, "dimension_props", None)
    if (
        props is None
        or not getattr(props, "enabled", False)
        or getattr(props, "annotation_kind", "LINEAR") != "AREA"
        or annotation_output_state(dimension_object) not in {"LIVE", "CAPTURED"}
    ):
        return None
    result = evaluate_area_binding(props) if props.measurement_state != "CAPTURED" else None
    if result is not None and result.get("state", "LIVE") != "LIVE":
        return None
    if result is None:
        if props.measurement_state != "CAPTURED":
            return None
        center = resolve_anchor(props.start)
        value = float(props.area_value)
        if center is None or value <= 0.0:
            return None
    else:
        center = Vector(result["center"])
        value = float(result["area"])
    fallback_end = resolve_anchor(props.end)
    label = area_label_world(props, center, fallback_end)
    presentation_offset = Vector(getattr(props, "presentation_offset", (0.0, 0.0, 0.0)))
    label += presentation_offset
    color = tuple(float(channel) for channel in props.color)
    direction = label - center
    if direction.length <= 1e-6:
        direction = Vector((1.0, 0.0, 0.0))
    direction.normalize()
    normal = Vector(result["normal"]) if result is not None else direction.orthogonal()
    normal = normal - direction * normal.dot(direction)
    if normal.length <= 1e-6:
        normal = direction.orthogonal()
    normal.normalize()
    half_marker = sizing.arrow_size * 0.5
    marker_direction = normal.cross(direction)
    if marker_direction.length <= 1e-6:
        marker_direction = direction.orthogonal()
    marker_direction.normalize()
    marker_cross = marker_direction * half_marker
    marker_up = normal * half_marker
    strokes = [
        OutputStroke((center, label), color, sizing.line_width),
        OutputStroke((center - marker_cross, center + marker_cross), color, sizing.line_width),
        OutputStroke((center - marker_up, center + marker_up), color, sizing.line_width),
    ]
    return GreasePencilOutputSpec(
        source_key=source_key,
        strokes=tuple(strokes),
        name=getattr(dimension_object, "name", "Dimensions Output"),
    )


def _angle_dimension_label_text(context, props, value):
    precision = min(max(int(getattr(props, "precision", 3)), 0), 3)
    label = f"{props.value_prefix}{degrees(value):.{precision}f}\N{DEGREE SIGN}{props.value_suffix}"
    custom_text = props.custom_text.strip()
    if custom_text:
        label = f"{custom_text}\n{label}" if props.custom_text_position != "BELOW" else f"{label}\n{custom_text}"
    return label


def angle_dimension_label_strokes(context, dimension_object, text_height, line_width, camera=None):
    props = getattr(dimension_object, "dimension_props", None)
    if props is None or getattr(props, "annotation_kind", "LINEAR") != "ANGLE":
        return ()
    source = resolve_angle_source(props)
    if source is None:
        return ()
    offset = Vector(getattr(props, "presentation_offset", (0.0, 0.0, 0.0)))
    geometry = get_angle_world_geometry(
        Vector(source["start"]) + offset,
        Vector(source["center"]) + offset,
        Vector(source["end"]) + offset,
        float(props.angle_radius),
        source.get("arc_mode", "MINOR"),
    )
    if geometry is None:
        return ()
    color = tuple(float(channel) for channel in props.color)
    return _text_strokes_at(
        _angle_dimension_label_text(context, props, geometry["value"]),
        geometry["label_world"],
        text_height,
        line_width,
        color,
        camera,
        geometry["arc_points_world"][0] - geometry["center_world"],
        geometry["plane_normal_world"],
    )


def _area_dimension_label_text(context, props, value, face_count, state):
    precision = getattr(props, "precision", 3)
    label = f"Area {props.value_prefix}{format_area(context, value, precision, getattr(props, 'unit_style', None))}{props.value_suffix}"
    if face_count > 1:
        label += f" ({face_count} faces)"
    if state == "CAPTURED":
        label += " [Captured]"
    custom_text = props.custom_text.strip()
    if custom_text:
        label = f"{custom_text}\n{label}" if props.custom_text_position != "BELOW" else f"{label}\n{custom_text}"
    return label


def area_dimension_label_strokes(context, dimension_object, text_height, line_width, camera=None):
    props = getattr(dimension_object, "dimension_props", None)
    if (
        props is None
        or getattr(props, "annotation_kind", "LINEAR") != "AREA"
        or props.measurement_state not in {"LIVE", "CAPTURED"}
    ):
        return ()
    result = evaluate_area_binding(props) if props.measurement_state != "CAPTURED" else None
    if result is not None and result.get("state", "LIVE") != "LIVE":
        return ()
    if result is None:
        if props.measurement_state != "CAPTURED":
            return ()
        center = resolve_anchor(props.start)
        value = float(props.area_value)
        face_count = int(props.area_face_count)
        if center is None or value <= 0.0:
            return ()
    else:
        center = Vector(result["center"])
        value = float(result["area"])
        face_count = int(result["face_count"])
    label_position = area_label_world(props, center, resolve_anchor(props.end))
    label_position += Vector(getattr(props, "presentation_offset", (0.0, 0.0, 0.0)))
    color = tuple(float(channel) for channel in props.color)
    direction = label_position - center
    return _text_strokes_at(
        _area_dimension_label_text(context, props, value, face_count, props.measurement_state),
        label_position,
        text_height,
        line_width,
        color,
        camera,
        direction,
        Vector((0.0, 0.0, 1.0)),
    )


def _linear_dimension_label_text(context, props, value):
    precision = getattr(props, "precision", 3)
    unit_style = getattr(props, "unit_style", None)
    value_text = format_dual_length(
        context, value, precision, unit_style,
        getattr(props, "secondary_unit_style", "NONE"),
        getattr(props, "secondary_precision", 2),
        getattr(props, "dual_unit_arrangement", "BRACKETS"),
    )
    label = f"{props.value_prefix}{value_text}{props.value_suffix}"
    if props.tolerance_mode == "SYMMETRIC" and props.tolerance_upper > 0.0:
        label += f" ±{format_length(context, props.tolerance_upper, precision, unit_style)}"
    elif props.tolerance_mode == "DEVIATION" and (
        props.tolerance_upper > 0.0 or props.tolerance_lower > 0.0
    ):
        label += (
            f" +{format_length(context, props.tolerance_upper, precision, unit_style)}"
            f" / -{format_length(context, props.tolerance_lower, precision, unit_style)}"
        )
    custom_text = props.custom_text.strip()
    if custom_text:
        if props.custom_text_position == "BELOW":
            label = f"{label}\n{custom_text}"
        else:
            label = f"{custom_text}\n{label}"
    return label


def _label_axes(geometry, camera):
    if camera is not None and getattr(camera, "type", None) == "CAMERA":
        rotation = camera.matrix_world.to_quaternion()
        return (
            (rotation @ Vector((1.0, 0.0, 0.0))).normalized(),
            (rotation @ Vector((0.0, 1.0, 0.0))).normalized(),
        )
    return (
        (geometry["line_end_world"] - geometry["line_start_world"]).normalized(),
        Vector(geometry["offset_direction_world"]).normalized(),
    )


def linear_dimension_label_layout(
    context,
    dimension_object,
    text_height,
    line_width,
    arrow_size,
    camera=None,
):
    """Build a vector label using the live Inline/Above/Outside presentation rules."""
    text_height = float(text_height)
    line_width = float(line_width)
    arrow_size = float(arrow_size)
    if text_height <= 0.0 or line_width <= 0.0 or arrow_size <= 0.0:
        raise ValueError("text height, line width, and arrow size must be greater than zero")

    props = getattr(dimension_object, "dimension_props", None)
    if props is None or getattr(props, "annotation_kind", "LINEAR") != "LINEAR":
        return LinearLabelLayout(())
    start_world = resolve_anchor(props.start)
    end_world = resolve_anchor(props.end)
    if start_world is None or end_world is None:
        return LinearLabelLayout(())
    geometry = get_dimension_world_geometry(
        props.dimension_type,
        start_world,
        end_world,
        Vector(props.offset_plane_normal),
        props.offset_distance,
        props.offset_angle,
        props.measurement_mode,
    )
    if geometry is None:
        return LinearLabelLayout(())

    placement_offset = Vector(getattr(props, "presentation_offset", (0.0, 0.0, 0.0)))
    line_start = geometry["line_start_world"] + placement_offset
    line_end = geometry["line_end_world"] + placement_offset
    line_mid = (line_start + line_end) * 0.5
    line_direction = (line_end - line_start).normalized()
    x_axis, y_axis = _label_axes(geometry, camera)
    if getattr(props, "label_orientation", "HORIZONTAL") == "ALIGNED":
        x_axis = line_direction
        y_axis = Vector(geometry["offset_direction_world"]).normalized()
    x_axis, y_axis = _readable_axes(x_axis, y_axis, camera)
    projected = Vector((line_direction.dot(x_axis), line_direction.dot(y_axis)))
    projection_scale = projected.length
    if projection_scale <= 1e-6:
        projected = Vector((1.0, 0.0))
        projection_scale = 1.0
    else:
        projected.normalize()
    screen_direction = (x_axis * projected.x + y_axis * projected.y).normalized()
    perpendicular_2d = Vector((-projected.y, projected.x))
    if perpendicular_2d.y < 0.0:
        perpendicular_2d.negate()
    screen_perpendicular = (
        x_axis * perpendicular_2d.x + y_axis * perpendicular_2d.y
    ).normalized()

    label = _linear_dimension_label_text(context, props, geometry["value"])
    block_width, block_height = text_block_dimensions(label, text_height)
    half_along = (
        abs(projected.x) * block_width * 0.5
        + abs(projected.y) * block_height * 0.5
    )
    half_across = (
        abs(perpendicular_2d.x) * block_width * 0.5
        + abs(perpendicular_2d.y) * block_height * 0.5
    )
    margin = text_height * (5.0 / 14.0)
    placement = getattr(context.scene.dimensions_settings, "text_placement", "INLINE")
    if placement == "INLINE":
        placement = "ABOVE" if getattr(props, "label_line_mode", "BROKEN") == "ABOVE" else "INLINE"
    dimension_line_strokes = ()
    if placement == "ABOVE":
        center = line_mid + screen_perpendicular * (half_across + margin)
    elif placement == "OUTSIDE":
        center = line_end + screen_direction * (arrow_size + margin + half_along)
    elif placement == "OUTSIDE_START":
        center = line_start - screen_direction * (arrow_size + margin + half_along)
    else:
        gap_half_length = (half_along + margin) / projection_scale
        line_length = (line_end - line_start).length
        if line_length < (gap_half_length * 2.0) + (arrow_size * 2.0):
            center = line_end + screen_direction * (arrow_size + margin + half_along)
            leader_end = center - screen_direction * (half_along + margin * 0.5)
            color = tuple(float(channel) for channel in props.color)
            dimension_line_strokes = (
                OutputStroke((line_start, line_end), color, line_width),
                OutputStroke((line_end, leader_end), color, line_width),
            )
        else:
            center = line_mid
            color = tuple(float(channel) for channel in props.color)
            dimension_line_strokes = (
                OutputStroke(
                    (line_start, line_mid - line_direction * gap_half_length),
                    color,
                    line_width,
                ),
                OutputStroke(
                    (line_mid + line_direction * gap_half_length, line_end),
                    color,
                    line_width,
                ),
            )

    first_baseline_offset = block_height * 0.5 - text_height
    origin = center + y_axis * first_baseline_offset

    color = tuple(float(channel) for channel in props.color)
    strokes = tuple(
        OutputStroke(points=polyline, color=color, line_width=line_width)
        for polyline in text_strokes(label, origin, x_axis, y_axis, text_height, "CENTER")
    )
    return LinearLabelLayout(strokes, dimension_line_strokes)


def linear_dimension_label_strokes(
    context,
    dimension_object,
    text_height,
    line_width,
    camera=None,
    arrow_size=None,
):
    """Build vector label strokes while preserving the legacy helper API."""
    if arrow_size is None:
        arrow_size = text_height
    return linear_dimension_label_layout(
        context,
        dimension_object,
        text_height,
        line_width,
        arrow_size,
        camera,
    ).strokes

def build_annotation_output_spec(
    context,
    resolved,
    source_key,
    sizing,
    text_height,
    camera=None,
):
    """Build a complete output spec with linework and labels for any annotation kind."""
    props = resolved.dimension_props
    kind = getattr(props, "annotation_kind", "LINEAR")
    if kind == "LINEAR":
        spec = linear_dimension_output_spec(resolved, source_key, sizing)
        if spec is None:
            return None
        label_layout = linear_dimension_label_layout(
            context,
            resolved,
            text_height,
            sizing.line_width,
            sizing.arrow_size,
            camera,
        )
        line_strokes = label_layout.dimension_line_strokes
        base_strokes = spec.strokes[1:] if line_strokes else spec.strokes
        output_strokes = line_strokes + base_strokes + label_layout.strokes
        return replace(spec, strokes=output_strokes)
    if kind == "ANGLE":
        spec = angle_dimension_output_spec(resolved, source_key, sizing)
        if spec is None:
            return None
        return replace(
            spec,
            strokes=spec.strokes + angle_dimension_label_strokes(
                context, resolved, text_height, sizing.line_width, camera,
            ),
        )
    if kind == "AREA":
        spec = area_dimension_output_spec(resolved, source_key, sizing)
        if spec is None:
            return None
        return replace(
            spec,
            strokes=spec.strokes + area_dimension_label_strokes(
                context, resolved, text_height, sizing.line_width, camera,
            ),
        )
    return None
