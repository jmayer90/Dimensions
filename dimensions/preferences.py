"""Per-user Dimensions preferences and safe access from Blender callbacks."""

from types import SimpleNamespace

import bpy

from .constants import (
    DEFAULT_ARROW_SIZE,
    DEFAULT_EMPTY_DISPLAY_SIZE,
    DEFAULT_HOVER_MARKER_SIZE,
    DEFAULT_LINE_WIDTH,
    DEFAULT_OFFSET_DISTANCE,
    DEFAULT_PRECISION,
    DEFAULT_SELECTION_PIXEL_THRESHOLD,
    DEFAULT_SNAP_PIXEL_THRESHOLD,
    DEFAULT_TEXT_SIZE,
)


# The add-on key in ``context.preferences.addons`` — and therefore the required
# ``AddonPreferences.bl_idname`` — is the full package name. Installed as an
# extension that is ``bl_ext.<repository>.dimensions``, not a bare ``dimensions``.
ADDON_ID = __package__
DEFAULT_PREFERENCES = SimpleNamespace(
    snap_pixel_threshold=DEFAULT_SNAP_PIXEL_THRESHOLD,
    selection_pixel_threshold=DEFAULT_SELECTION_PIXEL_THRESHOLD,
    hover_marker_size=DEFAULT_HOVER_MARKER_SIZE,
    line_width=DEFAULT_LINE_WIDTH,
    text_size=DEFAULT_TEXT_SIZE,
    arrow_size=DEFAULT_ARROW_SIZE,
    default_precision=DEFAULT_PRECISION,
    default_offset_distance=DEFAULT_OFFSET_DISTANCE,
    empty_display_size=DEFAULT_EMPTY_DISPLAY_SIZE,
    continuous_placement=True,
    default_axis_mode="ALIGNED",
    **{f"snap_{identifier}": True for identifier in (
        "vertex", "edge", "midpoint", "face_center", "face_point", "guide",
        "guide_point", "guide_plane",
        "measurement_endpoint", "measurement_midpoint", "measurement_segment",
    )},
    **{f"inference_{identifier}": True for identifier in (
        "parallel", "perpendicular", "extension", "intersection", "local_axis", "active_plane",
    )},
)
_reregistered_values = {}


def remember_preferences_for_reregister(context=None):
    """Retain user values across Blender's in-session add-on disable/enable cycle."""
    preferences = get_preferences(context)
    if preferences is DEFAULT_PREFERENCES:
        return
    _reregistered_values.clear()
    _reregistered_values.update({
        name: getattr(preferences, name)
        for name in vars(DEFAULT_PREFERENCES)
    })


def restore_preferences_after_reregister(context=None):
    """Restore values captured before Blender removed the AddonPreferences instance."""
    if not _reregistered_values:
        return
    preferences = get_preferences(context)
    if preferences is DEFAULT_PREFERENCES:
        return
    for name, value in _reregistered_values.items():
        setattr(preferences, name, value)
    _reregistered_values.clear()


def _tag_redraw(_self, _context):
    try:
        from .drawing import tag_redraw_all_view3d

        tag_redraw_all_view3d()
    except (ImportError, RuntimeError):
        pass


def get_preferences(context=None):
    """Return live add-on preferences, or defaults during registration/background work."""
    try:
        context = context or bpy.context
        addon = context.preferences.addons.get(ADDON_ID)
        preferences = None if addon is None else addon.preferences
        return preferences if isinstance(preferences, DIMENSIONS_AddonPreferences) else DEFAULT_PREFERENCES
    except (AttributeError, KeyError, RuntimeError):
        return DEFAULT_PREFERENCES


class DIMENSIONS_OT_ResetPreferences(bpy.types.Operator):
    bl_idname = "dimensions.reset_preferences"
    bl_label = "Reset Dimensions Preferences"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        preferences = get_preferences(context)
        for name, value in vars(DEFAULT_PREFERENCES).items():
            setattr(preferences, name, value)
        return {"FINISHED"}


class DIMENSIONS_AddonPreferences(bpy.types.AddonPreferences):
    bl_idname = ADDON_ID

    snap_pixel_threshold: bpy.props.FloatProperty(name="Snap Radius", default=DEFAULT_SNAP_PIXEL_THRESHOLD, min=4.0, max=128.0, subtype="PIXEL", update=_tag_redraw)
    selection_pixel_threshold: bpy.props.FloatProperty(name="Selection Radius", default=DEFAULT_SELECTION_PIXEL_THRESHOLD, min=4.0, max=128.0, subtype="PIXEL", update=_tag_redraw)
    hover_marker_size: bpy.props.FloatProperty(name="Hover Marker Size", default=DEFAULT_HOVER_MARKER_SIZE, min=2.0, max=64.0, update=_tag_redraw)
    line_width: bpy.props.FloatProperty(name="Default Line Width", default=DEFAULT_LINE_WIDTH, min=1.0, max=10.0, update=_tag_redraw)
    text_size: bpy.props.IntProperty(
        name="Default Text Size",
        description="Fixed viewport text size in pixels for new annotations",
        default=DEFAULT_TEXT_SIZE,
        min=8,
        max=64,
        update=_tag_redraw,
    )
    arrow_size: bpy.props.FloatProperty(
        name="Default Arrow Size",
        description="Fixed viewport arrowhead size in pixels for new annotations",
        default=DEFAULT_ARROW_SIZE,
        min=2.0,
        max=40.0,
        update=_tag_redraw,
    )
    default_precision: bpy.props.IntProperty(name="Default Precision", default=DEFAULT_PRECISION, min=0, max=8, update=_tag_redraw)
    default_offset_distance: bpy.props.FloatProperty(name="Default Offset", default=DEFAULT_OFFSET_DISTANCE, min=0.0, subtype="DISTANCE", update=_tag_redraw)
    empty_display_size: bpy.props.FloatProperty(name="Empty Display Size", default=DEFAULT_EMPTY_DISPLAY_SIZE, min=0.001, max=10.0, update=_tag_redraw)
    continuous_placement: bpy.props.BoolProperty(
        name="Continuous Placement",
        description="Keep creation tools active after each committed annotation",
        default=True,
    )
    default_axis_mode: bpy.props.EnumProperty(
        name="Default Session Axis",
        description="Starting Auto/X/Y/Z mode for a new placement session",
        items=(
            ("ALIGNED", "Auto", "Choose the extension direction from the annotation"),
            ("X", "X", "Use the global X axis"),
            ("Y", "Y", "Use the global Y axis"),
            ("Z", "Z", "Use the global Z axis"),
        ),
        default="ALIGNED",
    )
    snap_vertex: bpy.props.BoolProperty(name="Vertex", default=True, update=_tag_redraw)
    snap_edge: bpy.props.BoolProperty(name="Edge", default=True, update=_tag_redraw)
    snap_midpoint: bpy.props.BoolProperty(name="Midpoint", default=True, update=_tag_redraw)
    snap_face_center: bpy.props.BoolProperty(name="Face Center", default=True, update=_tag_redraw)
    snap_face_point: bpy.props.BoolProperty(name="Face Point", default=True, update=_tag_redraw)
    snap_guide: bpy.props.BoolProperty(name="Guide", default=True, update=_tag_redraw)
    snap_guide_point: bpy.props.BoolProperty(name="Guide Point", default=True, update=_tag_redraw)
    snap_guide_plane: bpy.props.BoolProperty(name="Guide Plane", default=True, update=_tag_redraw)
    snap_measurement_endpoint: bpy.props.BoolProperty(
        name="Measurement Endpoint", default=True, update=_tag_redraw
    )
    snap_measurement_midpoint: bpy.props.BoolProperty(
        name="Measurement Midpoint", default=True, update=_tag_redraw
    )
    snap_measurement_segment: bpy.props.BoolProperty(
        name="Measurement Segment", default=True, update=_tag_redraw
    )
    inference_parallel: bpy.props.BoolProperty(name="Parallel", default=True, update=_tag_redraw)
    inference_perpendicular: bpy.props.BoolProperty(name="Perpendicular", default=True, update=_tag_redraw)
    inference_extension: bpy.props.BoolProperty(name="Extension", default=True, update=_tag_redraw)
    inference_intersection: bpy.props.BoolProperty(name="Intersection", default=True, update=_tag_redraw)
    inference_local_axis: bpy.props.BoolProperty(name="Local Axis", default=True, update=_tag_redraw)
    inference_active_plane: bpy.props.BoolProperty(name="Active Plane", default=True, update=_tag_redraw)

    def draw(self, _context):
        layout = self.layout
        interaction = layout.box()
        interaction.label(text="Interaction")
        interaction.prop(self, "continuous_placement")
        interaction.prop(self, "default_axis_mode")
        interaction.prop(self, "selection_pixel_threshold")
        interaction.prop(self, "hover_marker_size")
        snapping = layout.box()
        snapping.label(text="Snapping")
        snapping.prop(self, "snap_pixel_threshold")
        from .snap_targets import draw_snap_target_row

        draw_snap_target_row(snapping, self)
        inference = layout.box()
        inference.label(text="Drafting Inference")
        from .inference import draw_inference_preferences

        draw_inference_preferences(inference, self)
        defaults = layout.box()
        defaults.label(text="Defaults for New Annotations")
        for name in ("line_width", "text_size", "arrow_size", "default_precision", "default_offset_distance", "empty_display_size"):
            defaults.prop(self, name)
        keymaps = layout.box()
        keymaps.label(text="Keymap")
        try:
            from .keymaps import draw_keymaps

            draw_keymaps(keymaps, bpy.context)
        except RuntimeError:
            keymaps.label(text="Keymap entries are unavailable during registration")
        layout.operator("dimensions.reset_preferences", icon="LOOP_BACK")


classes = (DIMENSIONS_AddonPreferences, DIMENSIONS_OT_ResetPreferences)
