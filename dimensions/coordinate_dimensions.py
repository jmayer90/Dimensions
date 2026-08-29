"""Named oriented datums and coordinate/elevation evaluation."""

from mathutils import Euler, Vector

from .anchors import anchor_resolution, resolve_anchor
from .properties import is_dimension_object, is_guide_object


_STATE_PRIORITY = {"LIVE": 0, "FALLBACK": 1, "NEEDS_REPAIR": 2}


def _combined_state(*states):
    """Return the least authoritative state across dependent bindings."""
    return max(states, key=lambda state: _STATE_PRIORITY.get(state, 2))


def is_datum_object(obj):
    return bool(
        is_guide_object(obj)
        and getattr(obj.guide_props, "kind", "GUIDE") == "POINT"
        and getattr(obj.guide_props, "is_datum", False)
    )


def datum_frame(datum):
    """Return ``(origin, x, y, z, state)`` for a valid named datum."""
    if not is_datum_object(datum):
        return None
    origin, status = anchor_resolution(datum.guide_props.start)
    rotation = Euler(tuple(datum.guide_props.datum_orientation), "XYZ").to_matrix()
    return (
        Vector(origin),
        (rotation @ Vector((1.0, 0.0, 0.0))).normalized(),
        (rotation @ Vector((0.0, 1.0, 0.0))).normalized(),
        (rotation @ Vector((0.0, 0.0, 1.0))).normalized(),
        {"BY_ID": "LIVE", "BY_FALLBACK": "FALLBACK"}.get(status, "NEEDS_REPAIR"),
    )


def coordinate_values(props):
    frame = datum_frame(props.datum_object)
    point, point_status = anchor_resolution(props.start)
    if frame is None:
        return None
    origin, x_axis, y_axis, z_axis, datum_state = frame
    sign = -1.0 if props.coordinate_sign == "REVERSED" else 1.0
    delta = Vector(point) - origin
    state = datum_state
    if point_status == "UNRESOLVABLE":
        state = "NEEDS_REPAIR"
    elif point_status == "BY_FALLBACK" and state == "LIVE":
        state = "FALLBACK"
    return {
        "origin": origin, "point": Vector(point), "axes": (x_axis, y_axis, z_axis),
        "values": (delta.dot(x_axis) * sign, delta.dot(y_axis) * sign, delta.dot(z_axis) * sign),
        "state": state,
    }


def elevation_value(props, _visited=None):
    _visited = set() if _visited is None else _visited
    owner = getattr(props, "id_data", None)
    owner_key = id(owner)
    if owner_key in _visited:
        return None
    _visited.add(owner_key)
    frame = datum_frame(props.datum_object)
    point, point_status = anchor_resolution(props.start)
    if frame is None:
        return None
    origin, _x, _y, datum_z, datum_state = frame
    axes = {
        "WORLD_X": Vector((1.0, 0.0, 0.0)),
        "WORLD_Y": Vector((0.0, 1.0, 0.0)),
        "WORLD_Z": Vector((0.0, 0.0, 1.0)),
        "DATUM_Z": datum_z,
    }
    axis = axes.get(props.elevation_axis, Vector((0.0, 0.0, 1.0)))
    value = (Vector(point) - origin).dot(axis)
    state = datum_state
    if point_status == "UNRESOLVABLE":
        state = "NEEDS_REPAIR"
    elif point_status == "BY_FALLBACK" and state == "LIVE":
        state = "FALLBACK"
    reference = props.elevation_reference
    if props.elevation_mode == "RELATIVE":
        if (
            not is_dimension_object(reference)
            or reference == getattr(props, "id_data", None)
            or reference.dimension_props.annotation_kind != "ELEVATION"
        ):
            return {"origin": origin, "point": Vector(point), "axis": axis, "value": value, "state": "NEEDS_REPAIR"}
        reference_result = elevation_value(reference.dimension_props, _visited)
        if reference_result is None:
            state = "NEEDS_REPAIR"
        else:
            value -= reference_result["value"]
            state = _combined_state(state, reference_result["state"])
    return {"origin": origin, "point": Vector(point), "axis": axis, "value": value, "state": state}


def signed_number(value, precision, show_plus=False, show_negative=True):
    magnitude = f"{abs(float(value)):.{int(precision)}f}"
    if value < 0.0:
        return f"-{magnitude}" if show_negative else magnitude
    return f"+{magnitude}" if show_plus else magnitude


def coordinate_label(props, values, formatter):
    def field(name, default=None):
        return props.get(name, default) if isinstance(props, dict) else getattr(props, name, default)

    names = {"X": (0,), "Y": (1,), "XY": (0, 1), "XYZ": (0, 1, 2)}
    axes = "XYZ"
    labels = []
    for index in names.get(field("coordinate_components", "XY"), (0, 1)):
        value = values[index]
        formatted = formatter(abs(value))
        sign = "-" if value < 0.0 and field("coordinate_show_negative", True) else "+" if value >= 0.0 and field("coordinate_show_plus", False) else ""
        labels.append(f"{axes[index]} {sign}{formatted}")
    return "\n".join(labels)


def datum_dependents(scene, datum):
    return tuple(
        obj for obj in scene.objects
        if is_dimension_object(obj)
        and obj.dimension_props.annotation_kind in {"COORDINATE", "ELEVATION"}
        and obj.dimension_props.datum_object == datum
    )
