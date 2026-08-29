"""Shared modal input conventions for Dimensions viewport tools."""

from mathutils import Vector
from bpy_extras.view3d_utils import location_3d_to_region_2d


CONFIRM_EVENTS = {"RET", "NUMPAD_ENTER"}
NAVIGATION_EVENTS = {"MIDDLEMOUSE", "WHEELUPMOUSE", "WHEELDOWNMOUSE"}
AXIS_EVENTS = {"A", "X", "Y", "Z"}


def session_axis(context):
    """Return the validated starting axis for a new placement session."""
    from .preferences import get_preferences

    axis = getattr(get_preferences(context), "default_axis_mode", "ALIGNED")
    return axis if axis in {"ALIGNED", "X", "Y", "Z"} else "ALIGNED"


def continuous_placement_enabled(context):
    from .preferences import get_preferences

    return bool(getattr(get_preferences(context), "continuous_placement", True))


def _active_object(context):
    view_layer = getattr(context, "view_layer", None)
    layer_objects = getattr(view_layer, "objects", None)
    return getattr(layer_objects, "active", getattr(context, "active_object", None))


def remember_session_context(operator, context):
    """Remember the user-controlled context that a modal session started in."""
    operator._session_mode = getattr(context, "mode", None)
    operator._session_active_object = _active_object(context)


def session_context_changed(operator, context):
    """Return whether mode or active object changed outside the modal workflow."""
    return (
        getattr(context, "mode", None) != getattr(operator, "_session_mode", None)
        or _active_object(context) is not getattr(operator, "_session_active_object", None)
    )


def axis_label(axis):
    if axis == "ALIGNED":
        return "Auto"
    if isinstance(axis, str) and axis.startswith("LOCAL_"):
        return f"Local {axis[-1]}"
    return axis


def push_undo_step(message):
    """Place an undo boundary after one item in a continuous modal session."""
    import bpy

    try:
        bpy.ops.ed.undo_push(message=message)
    except RuntimeError:
        # Background state-model tests have no interactive undo stack.
        pass


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


def constrained_delta(raw_delta, axis, context=None):
    direction = axis_world_direction(context, axis)
    if direction is not None:
        raw_delta = Vector(raw_delta)
        return direction * raw_delta.dot(direction)
    return raw_delta.copy()


def axis_world_direction(context, axis):
    """Return the shared X/Y/Z direction in world or active-plane space."""
    if axis not in {"X", "Y", "Z"}:
        return None
    from .guide_planes import active_plane_frame

    scene = None if context is None else getattr(context, "scene", None)
    frame = active_plane_frame(scene)
    if frame is not None:
        return {"X": frame[1], "Y": frame[2], "Z": frame[3]}[axis].copy()
    return {
        "X": Vector((1.0, 0.0, 0.0)),
        "Y": Vector((0.0, 1.0, 0.0)),
        "Z": Vector((0.0, 0.0, 1.0)),
    }[axis]


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
    directions = {axis: axis_world_direction(context, axis) for axis in ("X", "Y", "Z")}
    axis_vectors = {}
    for axis, direction in directions.items():
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
