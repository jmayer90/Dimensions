"""World-space stroke specs for generated linear-dimension output.

This adapter deliberately shares the persistent-anchor and dimension-frame logic
with the live annotation.  It emits only line work: text requires a separate
text-to-stroke implementation and is not represented by the current output spec.
"""

from dataclasses import dataclass

from mathutils import Vector

from .anchors import resolve_anchor
from .dimension_geometry import get_dimension_world_geometry
from .grease_pencil_output import GreasePencilOutputSpec, OutputStroke


TEXT_OUTPUT_SUPPORTED = False


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
