"""Shared modal input conventions for Dimensions viewport tools."""

from mathutils import Vector


CONFIRM_EVENTS = {"RET", "NUMPAD_ENTER"}
NAVIGATION_EVENTS = {"MIDDLEMOUSE", "WHEELUPMOUSE", "WHEELDOWNMOUSE"}
AXIS_EVENTS = {"A", "X", "Y", "Z"}

_DISTANCE_START_CHARACTERS = "0123456789.-"
_DISTANCE_CHARACTERS = "0123456789.-/'\" abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"


def is_confirm_event(event):
    return event.value == "PRESS" and event.type in CONFIRM_EVENTS


def is_navigation_event(event):
    return event.type in NAVIGATION_EVENTS


def axis_from_event(event, current_text=""):
    """Return a Blender-style axis lock before or after numeric entry."""
    if event.value != "PRESS" or event.type not in AXIS_EVENTS:
        return None
    return "ALIGNED" if event.type == "A" else event.type


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
