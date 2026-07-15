"""Viewport-owned transient drawing state for modal tools."""

import bpy


_states = {
    "DIMENSION": {},
    "MEASURE": {},
    "GUIDE": {},
}


def viewport_key(context=None):
    context = context or bpy.context
    window = getattr(context, "window", None)
    area = getattr(context, "area", None)
    region = getattr(context, "region", None)
    if window is None or area is None or region is None:
        return None
    return window.as_pointer(), area.as_pointer(), region.as_pointer()


def set_state(kind, state, context=None):
    key = state.get("viewport_key") if state is not None else None
    key = key or viewport_key(context)
    if key is not None:
        _states[kind][key] = state
    tag_redraw_all_view3d()


def get_state(kind, context=None):
    key = viewport_key(context)
    return None if key is None else _states[kind].get(key)


def clear_state(kind, context=None, key=None):
    key = key or viewport_key(context)
    if key is None:
        _states[kind].clear()
    else:
        _states[kind].pop(key, None)
    tag_redraw_all_view3d()


def clear_all_states():
    for states in _states.values():
        states.clear()
    tag_redraw_all_view3d()


def prune_stale_states():
    live_keys = set()
    for window in bpy.context.window_manager.windows:
        screen = window.screen
        if screen is None:
            continue
        for area in screen.areas:
            if area.type != "VIEW_3D":
                continue
            for region in area.regions:
                if region.type == "WINDOW":
                    live_keys.add((window.as_pointer(), area.as_pointer(), region.as_pointer()))
    for states in _states.values():
        for key in set(states).difference(live_keys):
            states.pop(key, None)


def tag_redraw_all_view3d():
    for window in bpy.context.window_manager.windows:
        screen = window.screen
        if screen is None:
            continue
        for area in screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()
