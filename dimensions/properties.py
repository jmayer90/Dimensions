from math import pi

import bpy

from .constants import (
    DEFAULT_ARROW_SIZE,
    DEFAULT_LINE_WIDTH,
    DEFAULT_OFFSET_DISTANCE,
    DEFAULT_PRECISION,
    DEFAULT_TEXT_SIZE,
)


def poll_mesh_objects(_self, obj):
    return obj is not None and obj.type == "MESH"


def clamp_anchor_vertex_index(anchor):
    obj = anchor.target_object

    if obj is None or obj.type != "MESH":
        if anchor.vertex_index != -1:
            anchor.vertex_index = -1
        return

    vertex_count = len(obj.data.vertices)
    if vertex_count == 0:
        if anchor.vertex_index != -1:
            anchor.vertex_index = -1
        return

    clamped_index = max(0, min(anchor.vertex_index, vertex_count - 1))
    if anchor.vertex_index != clamped_index:
        anchor.vertex_index = clamped_index


def update_anchor_target_object(anchor, _context):
    clamp_anchor_vertex_index(anchor)
    _schedule_dimension_location_sync()


def update_anchor_vertex_index(anchor, _context):
    clamp_anchor_vertex_index(anchor)
    _schedule_dimension_location_sync()


def update_dimension_display(_dimension, context):
    if context is not None and context.area is not None:
        context.area.tag_redraw()
    _schedule_dimension_location_sync()


def _schedule_dimension_location_sync():
    try:
        from .drawing import schedule_dimension_location_sync

        schedule_dimension_location_sync()
    except (ImportError, RuntimeError):
        pass


class CADDIM_PG_Anchor(bpy.types.PropertyGroup):
    target_object: bpy.props.PointerProperty(
        name="Object",
        type=bpy.types.Object,
        poll=poll_mesh_objects,
        update=update_anchor_target_object,
    )

    vertex_index: bpy.props.IntProperty(
        name="Vertex Index",
        default=-1,
        update=update_anchor_vertex_index,
    )

    fallback_local_co: bpy.props.FloatVectorProperty(
        name="Fallback Local Coordinate",
        size=3,
        subtype="XYZ",
        default=(0.0, 0.0, 0.0),
    )

    status: bpy.props.EnumProperty(
        name="Status",
        items=[
            ("LINKED", "Linked", "The anchor is linked to a valid base-mesh vertex"),
            ("DETACHED", "Detached", "The anchor fell back to its stored local coordinate"),
            ("MISSING_OBJECT", "Missing Object", "The anchor's target object no longer exists"),
        ],
        default="LINKED",
    )


class CADDIM_PG_Dimension(bpy.types.PropertyGroup):
    enabled: bpy.props.BoolProperty(
        name="Enabled",
        default=False,
    )

    start: bpy.props.PointerProperty(
        type=CADDIM_PG_Anchor,
    )

    end: bpy.props.PointerProperty(
        type=CADDIM_PG_Anchor,
    )

    dimension_type: bpy.props.EnumProperty(
        name="Extension Axis",
        items=[
            ("ALIGNED", "Auto", "Choose the closest usable global axis during placement"),
            ("X", "X Axis", "Extend the dimension along the global X axis"),
            ("Y", "Y Axis", "Extend the dimension along the global Y axis"),
            ("Z", "Z Axis", "Extend the dimension along the global Z axis"),
        ],
        default="ALIGNED",
        update=update_dimension_display,
    )

    offset_distance: bpy.props.FloatProperty(
        name="Offset",
        default=DEFAULT_OFFSET_DISTANCE,
        soft_min=-120.0,
        soft_max=120.0,
        subtype="DISTANCE",
        update=update_dimension_display,
    )

    offset_angle: bpy.props.FloatProperty(
        name="Offset Angle",
        description="Tilt the dimension placement plane around the measured edge",
        default=0.0,
        min=-pi,
        max=pi,
        subtype="ANGLE",
        update=update_dimension_display,
    )

    offset_plane_normal: bpy.props.FloatVectorProperty(
        name="Placement Plane Normal",
        size=3,
        subtype="XYZ",
        default=(0.0, 0.0, 1.0),
    )

    visible: bpy.props.BoolProperty(
        name="Visible",
        default=True,
    )

    color: bpy.props.FloatVectorProperty(
        name="Color",
        subtype="COLOR",
        size=4,
        default=(0.08, 0.58, 1.0, 1.0),
        min=0.0,
        max=1.0,
    )

    selected_color: bpy.props.FloatVectorProperty(
        name="Selected Color",
        subtype="COLOR",
        size=4,
        default=(0.35, 0.82, 1.0, 1.0),
        min=0.0,
        max=1.0,
    )

    line_width: bpy.props.FloatProperty(
        name="Line Width",
        default=DEFAULT_LINE_WIDTH,
        min=1.0,
        max=10.0,
        update=update_dimension_display,
    )

    text_size: bpy.props.IntProperty(
        name="Text Size",
        default=DEFAULT_TEXT_SIZE,
        min=8,
        max=64,
        update=update_dimension_display,
    )

    arrow_size: bpy.props.FloatProperty(
        name="Arrow Size",
        default=DEFAULT_ARROW_SIZE,
        min=2.0,
        max=40.0,
        update=update_dimension_display,
    )

    custom_text: bpy.props.StringProperty(
        name="Custom Text",
        description="Optional note displayed with the measured value",
        default="",
        update=update_dimension_display,
    )

    custom_text_position: bpy.props.EnumProperty(
        name="Custom Text Position",
        items=[
            ("ABOVE", "Above Value", "Display custom text above the measured value"),
            ("BELOW", "Below Value", "Display custom text below the measured value"),
        ],
        default="ABOVE",
        update=update_dimension_display,
    )


class CADDIM_PG_SceneSettings(bpy.types.PropertyGroup):
    unit_style: bpy.props.EnumProperty(
        name="Unit Style",
        items=[
            ("AUTO", "Auto", "Follow Blender's current unit settings"),
            ("METRIC_AUTO", "Metric Auto", "Choose millimeters, centimeters, or meters from the value"),
            ("MILLIMETERS", "Millimeters", "Display metric values in millimeters"),
            ("CENTIMETERS", "Centimeters", "Display metric values in centimeters"),
            ("METERS", "Meters", "Display metric values in meters"),
            ("FEET_INCHES", "Feet + Inches", "Display imperial values using feet and inches"),
            ("INCH_DECIMAL", "Inches Decimal", "Display imperial values as decimal inches"),
            ("INCH_FRACTION", "Inches Fraction", "Display imperial values as fractional inches"),
            ("BLENDER", "Blender Native", "Use Blender's default unit formatting"),
        ],
        default="AUTO",
    )

    metric_unit_style: bpy.props.EnumProperty(
        name="Metric Unit Style",
        items=[
            ("AUTO", "Auto", "Follow Blender's current metric length unit"),
            ("METRIC_AUTO", "Metric Auto", "Choose millimeters, centimeters, or meters from the value"),
            ("MILLIMETERS", "Millimeters", "Display values in millimeters"),
            ("CENTIMETERS", "Centimeters", "Display values in centimeters"),
            ("METERS", "Meters", "Display values in meters"),
            ("BLENDER", "Blender Native", "Use Blender's native metric formatting"),
        ],
        default="AUTO",
        update=update_dimension_display,
    )

    imperial_unit_style: bpy.props.EnumProperty(
        name="Imperial Unit Style",
        items=[
            ("AUTO", "Auto", "Follow Blender's current imperial length unit"),
            ("FEET_INCHES", "Feet + Inches", "Display values using feet and inches"),
            ("INCH_DECIMAL", "Inches Decimal", "Display values as decimal inches"),
            ("INCH_FRACTION", "Inches Fraction", "Display values as fractional inches"),
            ("BLENDER", "Blender Native", "Use Blender's native imperial formatting"),
        ],
        default="AUTO",
        update=update_dimension_display,
    )

    imperial_denominator: bpy.props.EnumProperty(
        name="Fraction Denominator",
        items=[
            ("2", "1/2", "Round fractions to the nearest half inch"),
            ("4", "1/4", "Round fractions to the nearest quarter inch"),
            ("8", "1/8", "Round fractions to the nearest eighth inch"),
            ("16", "1/16", "Round fractions to the nearest sixteenth inch"),
            ("32", "1/32", "Round fractions to the nearest thirty-second inch"),
            ("64", "1/64", "Round fractions to the nearest sixty-fourth inch"),
        ],
        default="32",
    )

    precision: bpy.props.IntProperty(
        name="Precision",
        description="Number of decimal places used by dimension values",
        default=DEFAULT_PRECISION,
        min=0,
        max=8,
        update=update_dimension_display,
    )

    dimension_color: bpy.props.FloatVectorProperty(
        name="Color",
        subtype="COLOR",
        size=4,
        default=(0.08, 0.58, 1.0, 1.0),
        min=0.0,
        max=1.0,
        update=update_dimension_display,
    )

    selected_dimension_color: bpy.props.FloatVectorProperty(
        name="Selected Color",
        subtype="COLOR",
        size=4,
        default=(0.35, 0.82, 1.0, 1.0),
        min=0.0,
        max=1.0,
        update=update_dimension_display,
    )

    dimension_line_width: bpy.props.FloatProperty(
        name="Line Width",
        default=DEFAULT_LINE_WIDTH,
        min=1.0,
        max=10.0,
        update=update_dimension_display,
    )

    dimension_text_size: bpy.props.IntProperty(
        name="Text Size",
        default=DEFAULT_TEXT_SIZE,
        min=8,
        max=64,
        update=update_dimension_display,
    )

    dimension_arrow_size: bpy.props.FloatProperty(
        name="Arrow Size",
        default=DEFAULT_ARROW_SIZE,
        min=2.0,
        max=40.0,
        update=update_dimension_display,
    )

    text_placement: bpy.props.EnumProperty(
        name="Text Placement",
        items=[
            ("INLINE", "Inline (Gap)", "Center values in a break in each dimension line"),
            ("ABOVE", "Above Line", "Place values above their dimension lines"),
            ("OUTSIDE", "Outside End", "Place values beyond their end arrows"),
        ],
        default="INLINE",
        update=update_dimension_display,
    )

    show_selected_object_overlay: bpy.props.BoolProperty(
        name="Show Selected Mesh Size HUD",
        default=True,
        update=update_dimension_display,
    )

    show_overlay_object_name: bpy.props.BoolProperty(
        name="Show Mesh Names",
        default=True,
        update=update_dimension_display,
    )

    hud_corner: bpy.props.EnumProperty(
        name="Corner",
        items=[
            ("BOTTOM_LEFT", "Bottom Left", "Place the HUD in the bottom-left corner"),
            ("BOTTOM_RIGHT", "Bottom Right", "Place the HUD in the bottom-right corner"),
            ("TOP_LEFT", "Top Left", "Place the HUD in the top-left corner"),
            ("TOP_RIGHT", "Top Right", "Place the HUD in the top-right corner"),
        ],
        default="BOTTOM_LEFT",
        update=update_dimension_display,
    )

    hud_padding_horizontal: bpy.props.IntProperty(
        name="Horizontal Padding",
        description="Distance from the left or right viewport edge in pixels",
        default=20,
        min=0,
        max=1000,
        update=update_dimension_display,
    )

    hud_padding_vertical: bpy.props.IntProperty(
        name="Vertical Padding",
        description="Distance from the top or bottom viewport edge in pixels",
        default=28,
        min=0,
        max=1000,
        update=update_dimension_display,
    )

    enable_click_select: bpy.props.BoolProperty(
        name="Select Dimensions in Viewport",
        description="Allow clicking a drawn dimension line or label to select its dimension object",
        default=True,
        update=update_dimension_display,
    )


def is_dimension_object(obj):
    return bool(obj and hasattr(obj, "dimension_props") and obj.dimension_props.enabled)


def apply_scene_style_to_dimension(scene_settings, dimension_props):
    dimension_props.color = tuple(scene_settings.dimension_color)
    dimension_props.selected_color = tuple(scene_settings.selected_dimension_color)
    dimension_props.line_width = scene_settings.dimension_line_width
    dimension_props.text_size = scene_settings.dimension_text_size
    dimension_props.arrow_size = scene_settings.dimension_arrow_size


def register_properties():
    bpy.types.Object.dimension_props = bpy.props.PointerProperty(
        type=CADDIM_PG_Dimension,
    )
    bpy.types.Scene.dimensions_settings = bpy.props.PointerProperty(
        type=CADDIM_PG_SceneSettings,
    )


def unregister_properties():
    if hasattr(bpy.types.Object, "dimension_props"):
        del bpy.types.Object.dimension_props
    if hasattr(bpy.types.Scene, "dimensions_settings"):
        del bpy.types.Scene.dimensions_settings


classes = (
    CADDIM_PG_Anchor,
    CADDIM_PG_Dimension,
    CADDIM_PG_SceneSettings,
)
