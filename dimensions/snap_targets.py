"""Shared snap-target configuration for preferences, scenes, and modal tools."""


TARGETS = (
    ("vertex", "Vertex", "VERTEXSEL"),
    ("edge", "Edge", "EDGESEL"),
    ("midpoint", "Midpoint", "SNAP_MIDPOINT"),
    ("face_center", "Face Center", "SNAP_FACE_CENTER"),
    ("face_point", "Face Point", "FACESEL"),
    ("guide", "Guide", "EMPTY_AXIS"),
    ("guide_point", "Guide Point", "SNAP_ON"),
    ("guide_plane", "Guide Plane", "MESH_GRID"),
    ("measurement_endpoint", "Measurement Endpoint", "SNAP_ON"),
    ("measurement_midpoint", "Measurement Midpoint", "SNAP_MIDPOINT"),
    ("measurement_segment", "Measurement Segment", "DRIVER_DISTANCE"),
)
TARGET_IDS = tuple(identifier for identifier, _label, _icon in TARGETS)
TARGET_SHORT_LABELS = {
    "vertex": "V", "edge": "E", "midpoint": "Mid", "face_center": "FC",
    "face_point": "FP", "guide": "G", "guide_point": "GP", "guide_plane": "PL",
    "measurement_endpoint": "ME",
    "measurement_midpoint": "MM", "measurement_segment": "MS",
}


def enabled_snap_targets(context):
    """Resolve the scene override, falling back to persistent user preferences."""
    from .preferences import get_preferences

    settings = getattr(getattr(context, "scene", None), "dimensions_settings", None)
    source = (
        settings
        if settings is not None and getattr(settings, "use_snap_target_override", False)
        else get_preferences(context)
    )
    return frozenset(
        identifier
        for identifier in TARGET_IDS
        if bool(getattr(source, f"snap_{identifier}", True))
    )


def snap_target_status(context):
    enabled = enabled_snap_targets(context)
    if not enabled:
        return "Snap: Free"
    if len(enabled) == len(TARGET_IDS):
        return "Snap: All"
    labels = [TARGET_SHORT_LABELS[identifier] for identifier in TARGET_IDS if identifier in enabled]
    return "Snap: " + ", ".join(labels)


def cycle_snap_targets(context):
    """Cycle all targets -> one target at a time -> all, using the active source."""
    from .preferences import get_preferences

    settings = getattr(getattr(context, "scene", None), "dimensions_settings", None)
    source = (
        settings
        if settings is not None and getattr(settings, "use_snap_target_override", False)
        else get_preferences(context)
    )
    enabled = [identifier for identifier in TARGET_IDS if getattr(source, f"snap_{identifier}", True)]
    if len(enabled) == 1:
        next_index = TARGET_IDS.index(enabled[0]) + 1
        next_identifier = TARGET_IDS[next_index] if next_index < len(TARGET_IDS) else None
    else:
        next_identifier = TARGET_IDS[0]
    for identifier in TARGET_IDS:
        setattr(source, f"snap_{identifier}", next_identifier is None or identifier == next_identifier)
    return enabled_snap_targets(context)


def handle_snap_target_event(context, event):
    from .keymaps import modal_action_from_event

    if modal_action_from_event(event) != "CYCLE_SNAP_TARGETS":
        return False
    cycle_snap_targets(context)
    return True


def draw_snap_target_row(layout, source):
    row = layout.row(align=True)
    for identifier, _label, icon in TARGETS:
        row.prop(
            source,
            f"snap_{identifier}",
            text="",
            icon=icon,
            toggle=True,
            emboss=True,
        )
    return row
