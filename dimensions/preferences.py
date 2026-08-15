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
)


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
    text_size: bpy.props.IntProperty(name="Default Text Size", default=DEFAULT_TEXT_SIZE, min=8, max=64, update=_tag_redraw)
    arrow_size: bpy.props.FloatProperty(name="Default Arrow Size", default=DEFAULT_ARROW_SIZE, min=2.0, max=40.0, update=_tag_redraw)
    default_precision: bpy.props.IntProperty(name="Default Precision", default=DEFAULT_PRECISION, min=0, max=8, update=_tag_redraw)
    default_offset_distance: bpy.props.FloatProperty(name="Default Offset", default=DEFAULT_OFFSET_DISTANCE, min=0.0, subtype="DISTANCE", update=_tag_redraw)
    empty_display_size: bpy.props.FloatProperty(name="Empty Display Size", default=DEFAULT_EMPTY_DISPLAY_SIZE, min=0.001, max=10.0, update=_tag_redraw)

    def draw(self, _context):
        layout = self.layout
        interaction = layout.box()
        interaction.label(text="Interaction")
        interaction.prop(self, "selection_pixel_threshold")
        interaction.prop(self, "hover_marker_size")
        snapping = layout.box()
        snapping.label(text="Snapping")
        snapping.prop(self, "snap_pixel_threshold")
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
