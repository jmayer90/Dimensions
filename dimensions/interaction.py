"""Shared modal input conventions for Dimensions viewport tools."""

from mathutils import Vector


CONFIRM_EVENTS = {"RET", "NUMPAD_ENTER"}
# View navigation passes through to Blender: mouse, trackpad, 3D mouse, and the
# numpad view keys. Tools check typed input first, so a numpad digit that types a
# distance is consumed before it could change the view.
NAVIGATION_EVENTS = {
    "MIDDLEMOUSE", "WHEELUPMOUSE", "WHEELDOWNMOUSE",
    "TRACKPADPAN", "TRACKPADZOOM", "MOUSEROTATE", "MOUSESMARTZOOM", "NDOF_MOTION",
    "NUMPAD_0", "NUMPAD_1", "NUMPAD_2", "NUMPAD_3", "NUMPAD_4", "NUMPAD_5",
    "NUMPAD_6", "NUMPAD_7", "NUMPAD_8", "NUMPAD_9",
    "NUMPAD_PERIOD", "NUMPAD_PLUS", "NUMPAD_MINUS", "HOME",
}
AXIS_EVENTS = {"A", "X", "Y", "Z"}


def session_axis(context):
    """Return the validated starting axis for a new placement session."""
    from .preferences import get_preferences

    axis = getattr(get_preferences(context), "default_axis_mode", "ALIGNED")
    return axis if axis in {"ALIGNED", "X", "Y", "Z"} else "ALIGNED"


def refuse_newer_scene(operator, context):
    """Warn and return True when the scene was saved by a newer Dimensions.

    Creation would otherwise stop with a traceback, because Dimensions never writes
    data whose newer shape it does not understand.
    """
    from . import messages
    from .migrations import scene_is_newer_than_supported

    if scene_is_newer_than_supported(getattr(context, "scene", None)):
        operator.report(messages.WARNING, messages.SCENE_SCHEMA_NEWER)
        return True
    return False


def continuous_placement_enabled(context):
    from .preferences import get_preferences

    return bool(getattr(get_preferences(context), "continuous_placement", True))


def _active_object(context):
    view_layer = getattr(context, "view_layer", None)
    layer_objects = getattr(view_layer, "objects", None)
    return getattr(layer_objects, "active", getattr(context, "active_object", None))


def remember_session_context(operator, context):
    """Remember the user-controlled context that a modal session started in."""
    from .viewport_state import viewport_key

    operator._session_mode = getattr(context, "mode", None)
    operator._session_active_object = _active_object(context)
    operator._session_viewport_key = viewport_key(context)


def session_context_changed(operator, context):
    """Return whether mode or active object changed outside the modal workflow."""
    from .viewport_state import viewport_key

    return (
        getattr(context, "mode", None) != getattr(operator, "_session_mode", None)
        or _active_object(context) is not getattr(operator, "_session_active_object", None)
        or viewport_key(context) != getattr(operator, "_session_viewport_key", None)
    )


def modal_cleanup_on_exception(modal):
    """Release an operator's transient state before surfacing a modal failure."""
    from functools import wraps

    @wraps(modal)
    def wrapped(operator, context, event):
        try:
            return modal(operator, context, event)
        except Exception:
            try:
                operator.cancel(context)
            except Exception:
                pass
            raise

    return wrapped


def axis_label(axis):
    if axis == "ALIGNED":
        return "Auto"
    if isinstance(axis, str) and axis.startswith("LOCAL_"):
        return f"Local {axis[-1]}"
    return axis


def set_tool_status_text(context, text):
    """Show modal key hints in Blender's status bar, or restore it with ``None``."""
    workspace = getattr(context, "workspace", None)
    if workspace is None:
        return
    try:
        workspace.status_text_set(text)
    except (AttributeError, RuntimeError, TypeError):
        pass


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


def continues_typed_distance(current_text, event):
    """Return whether a key press extends a typed distance rather than acting as a shortcut.

    Once a distance is being typed its letters spell a unit, as in ``2ft`` or
    ``3 meters``, so single-letter shortcuts such as snap cycling must not take them.
    """
    character = getattr(event, "ascii", "")
    return bool(current_text) and event.value == "PRESS" and bool(character) and character in _DISTANCE_CHARACTERS


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


def axis_world_direction(_context, axis):
    """Return the shared world X/Y/Z direction."""
    if axis not in {"X", "Y", "Z"}:
        return None
    return {
        "X": Vector((1.0, 0.0, 0.0)),
        "Y": Vector((0.0, 1.0, 0.0)),
        "Z": Vector((0.0, 0.0, 1.0)),
    }[axis]
