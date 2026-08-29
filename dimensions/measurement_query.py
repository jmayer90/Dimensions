"""Pure formatting and segment selection for transient measurement sessions."""

from mathutils import Vector

from .units import format_length


def measurement_components(start, end):
    delta = Vector(end) - Vector(start)
    return {
        "total": delta.length,
        "x": delta.x,
        "y": delta.y,
        "z": delta.z,
    }


def format_measurement_query(context, start, end, precision):
    values = measurement_components(start, end)
    formatted = {
        name: format_length(context, value, precision)
        for name, value in values.items()
    }
    lines = (
        f"Distance {formatted['total']}",
        f"ΔX {formatted['x']}   ΔY {formatted['y']}   ΔZ {formatted['z']}",
    )
    return {
        "values": values,
        "formatted": formatted,
        "lines": lines,
        "clipboard": f"{lines[0]} | {lines[1]}",
    }
