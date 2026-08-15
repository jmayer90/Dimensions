"""Shared modal input conventions for Dimensions viewport tools."""

from mathutils import Vector
from bpy_extras.view3d_utils import location_3d_to_region_2d


CONFIRM_EVENTS = {"RET", "NUMPAD_ENTER"}
NAVIGATION_EVENTS = {"MIDDLEMOUSE", "WHEELUPMOUSE", "WHEELDOWNMOUSE"}
AXIS_EVENTS = {"A", "X", "Y", "Z"}

_DISTANCE_START_CHARACTERS = "0123456789.-"
_DISTANCE_CHARACTERS = "0123456789.-/'\" abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"


def is_confirm_event(event):
    from .keymaps import modal_action_from_event

    return modal_action_from_event(event) == "CONFIRM" or (
        event.value == "PRESS" and event.type in CONFIRM_EVENTS
    )


def is_navigation_event(event):
    return event.type in NAVIGATION_EVENTS


def axis_from_event(event):
    """Return a Blender-style axis lock before or after numeric entry."""
    from .keymaps import modal_action_from_event

    action = modal_action_from_event(event)
    if action is not None:
        return {
            "CONSTRAIN_ALIGNED": "ALIGNED",
            "CONSTRAIN_X": "X",
            "CONSTRAIN_Y": "Y",
            "CONSTRAIN_Z": "Z",
        }.get(action)
    if event.value == "PRESS" and event.type in AXIS_EVENTS:
        return "ALIGNED" if event.type == "A" else event.type
    return None


def update_distance_text(current_text, event):
    """Apply one Blender event to a typed distance, returning (text, handled)."""
    if event.value != "PRESS":
        return current_text, False

    if event.type in {"BACK_SPACE", "DEL"}:
        if not current_text:
            return current_text, False
        return current_text[:-1], True

    character = event.ascii
    if not character:
        return current_text, False
    if current_text:
        if character not in _DISTANCE_CHARACTERS:
            return current_text, False
    elif character not in _DISTANCE_START_CHARACTERS:
        return current_text, False
    return current_text + character, True


def constrained_delta(raw_delta, axis):
    if axis == "X":
        return Vector((raw_delta.x, 0.0, 0.0))
    if axis == "Y":
        return Vector((0.0, raw_delta.y, 0.0))
    if axis == "Z":
        return Vector((0.0, 0.0, raw_delta.z))
    return raw_delta.copy()


def nearest_axis_from_screen_vectors(mouse_delta, axis_vectors):
    """Choose the projected global axis closest to a mouse-drag direction."""
    mouse_delta = Vector(mouse_delta)
    if mouse_delta.length < 1e-6:
        return None
    mouse_delta.normalize()
    best = None
    for axis, vector in axis_vectors.items():
        vector = Vector(vector)
        if vector.length < 1e-6:
            continue
        vector.normalize()
        score = abs(mouse_delta.dot(vector))
        if best is None or score > best[0]:
            best = (score, axis)
    return None if best is None else best[1]


def axis_from_mouse_direction(context, origin_world, mouse_x, mouse_y):
    if context.region is None or context.region_data is None or origin_world is None:
        return None
    origin_world = Vector(origin_world)
    origin_screen = location_3d_to_region_2d(context.region, context.region_data, origin_world)
    if origin_screen is None:
        return None
    scale = max(float(context.region_data.view_distance) * 0.25, 0.1)
    axis_vectors = {}
    for axis, direction in {
        "X": Vector((1.0, 0.0, 0.0)),
        "Y": Vector((0.0, 1.0, 0.0)),
        "Z": Vector((0.0, 0.0, 1.0)),
    }.items():
        projected = location_3d_to_region_2d(
            context.region,
            context.region_data,
            origin_world + direction * scale,
        )
        if projected is not None:
            axis_vectors[axis] = projected - origin_screen
    return nearest_axis_from_screen_vectors(
        Vector((mouse_x, mouse_y)) - origin_screen,
        axis_vectors,
    )
