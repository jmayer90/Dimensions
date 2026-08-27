"""World-space stroke specs for generated linear-dimension output.

This adapter deliberately shares the persistent-anchor and dimension-frame logic
with the live annotation. It emits dimension linework and legible vector-font
labels as world-space strokes for the Grease Pencil backend.
"""

from dataclasses import dataclass

from mathutils import Vector

from .anchors import resolve_anchor
from .dimension_geometry import get_dimension_world_geometry
from .grease_pencil_output import GreasePencilOutputSpec, OutputStroke
from .stroke_font import text_block_dimensions, text_strokes
from .units import format_length


TEXT_OUTPUT_SUPPORTED = True


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
    return _open_arrow_strokes(point, direction, perpendicular, color, sizing)


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
    arrow_style = getattr(props, "arrow_end_style", "ARROW")
    strokes = [
        OutputStroke((line_start, line_end), color, sizing.line_width),
        OutputStroke((start_world, line_start), color, sizing.line_width),
        OutputStroke((end_world, line_end), color, sizing.line_width),
    ]
    strokes.extend(
        _endpoint_strokes(
            line_start,
            line_direction,
            perpendicular,
            arrow_style,
            color,
            sizing,
        )
    )
    strokes.extend(
        _endpoint_strokes(
            line_end,
            -line_direction,
            perpendicular,
            arrow_style,
            color,
            sizing,
        )
    )
    return GreasePencilOutputSpec(
        source_key=source_key,
        strokes=tuple(strokes),
        name=getattr(dimension_object, "name", "Dimensions Output"),
    )


def _linear_dimension_label_text(context, props, value):
    scene_settings = getattr(context.scene, "dimensions_settings", None)
    precision = getattr(scene_settings, "precision", 3)
    value_text = format_length(context, value, precision)
    label = f"{props.value_prefix}{value_text}{props.value_suffix}"
    if props.tolerance_mode == "SYMMETRIC" and props.tolerance_upper > 0.0:
        label += f" ±{format_length(context, props.tolerance_upper, precision)}"
    elif props.tolerance_mode == "DEVIATION" and (
        props.tolerance_upper > 0.0 or props.tolerance_lower > 0.0
    ):
        label += (
            f" +{format_length(context, props.tolerance_upper, precision)}"
            f" / -{format_length(context, props.tolerance_lower, precision)}"
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
    dimension_line_strokes = ()
    if placement == "ABOVE":
        center = line_mid + screen_perpendicular * (half_across + margin)
    elif placement == "OUTSIDE":
        center = line_end + screen_direction * (arrow_size + margin + half_along)
    else:
        gap_half_length = (half_along + margin) / projection_scale
        line_length = (line_end - line_start).length
        if line_length < (gap_half_length * 2.0) + (arrow_size * 2.0):
            center = line_end + screen_direction * (arrow_size + margin + half_along)
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
