from math import pi

import bpy

from .constants import (
    DEFAULT_ARROW_SIZE,
    DEFAULT_LINE_WIDTH,
    DEFAULT_GUIDE_LINE_WIDTH,
    DEFAULT_OFFSET_DISTANCE,
    DEFAULT_PRECISION,
    DEFAULT_SNAP_PIXEL_THRESHOLD,
    DEFAULT_TEXT_SIZE,
)


def poll_mesh_objects(_self, obj):
    return obj is not None and obj.type == "MESH"


def clamp_anchor_vertex_index(anchor):
    if getattr(anchor, "anchor_type", "VERTEX") != "VERTEX":
        if anchor.vertex_index != -1:
            anchor.vertex_index = -1
        return

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
    _refresh_anchor_vertex_id(anchor)
    _schedule_dimension_location_sync()


def update_anchor_vertex_index(anchor, _context):
    clamp_anchor_vertex_index(anchor)
    _refresh_anchor_vertex_id(anchor)
    _schedule_dimension_location_sync()


def _refresh_anchor_vertex_id(anchor):
    if getattr(anchor, "anchor_type", "VERTEX") != "VERTEX":
        anchor.vertex_id = 0
        return
    obj = anchor.target_object
    vertex_index = anchor.vertex_index
    if obj is None or obj.type != "MESH" or not (0 <= vertex_index < len(obj.data.vertices)):
        anchor.vertex_id = 0
        return
    from .anchors import ensure_object_vertex_id

    anchor.vertex_id = ensure_object_vertex_id(obj, vertex_index)


def update_dimension_display(_dimension, context):
    try:
        from .drawing import invalidate_dimension_geometry_cache, tag_redraw_all_view3d

        invalidate_dimension_geometry_cache()
        tag_redraw_all_view3d()
    except (ImportError, RuntimeError):
        if context is not None and context.area is not None:
            context.area.tag_redraw()
    _schedule_dimension_location_sync()


def _schedule_dimension_location_sync():
    try:
        from .scene_sync import schedule_scene_sync

        schedule_scene_sync()
    except (ImportError, RuntimeError):
        pass


class CADDIM_PG_Anchor(bpy.types.PropertyGroup):
    anchor_type: bpy.props.EnumProperty(
        name="Anchor Type",
        items=[
            ("VERTEX", "Vertex", "Anchor follows a mesh vertex"),
            ("OBJECT_POINT", "Object Point", "Anchor follows a fixed local point on a mesh object"),
            ("WORLD", "World Point", "Anchor is a fixed world coordinate"),
        ],
        default="VERTEX",
    )

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

    vertex_id: bpy.props.IntProperty(
        name="Persistent Vertex ID",
        description="Stable mesh attribute ID used to survive vertex reindexing",
        default=0,
        min=0,
        options={"HIDDEN"},
    )

    fallback_local_co: bpy.props.FloatVectorProperty(
        name="Fallback Local Coordinate",
        size=3,
        subtype="XYZ",
        default=(0.0, 0.0, 0.0),
    )

    world_co: bpy.props.FloatVectorProperty(
        name="World Coordinate",
        size=3,
        subtype="XYZ",
        default=(0.0, 0.0, 0.0),
    )


class CADDIM_PG_AreaFaceBinding(bpy.types.PropertyGroup):
    face_id: bpy.props.IntProperty(name="Persistent Face ID", default=0, min=0)
    fallback_center: bpy.props.FloatVectorProperty(name="Fallback Center", size=3, subtype="XYZ")
    fallback_normal: bpy.props.FloatVectorProperty(
        name="Fallback Normal",
        size=3,
        subtype="XYZ",
        default=(0.0, 0.0, 1.0),
    )
    fallback_area: bpy.props.FloatProperty(name="Fallback Area", default=0.0, min=0.0)
    vertex_count: bpy.props.IntProperty(name="Vertex Count", default=0, min=0)

class CADDIM_PG_Dimension(bpy.types.PropertyGroup):
    enabled: bpy.props.BoolProperty(
        name="Enabled",
        default=False,
    )

    annotation_kind: bpy.props.EnumProperty(
        name="Annotation Type",
        items=[
            ("LINEAR", "Linear", "Distance between two points"),
            ("AREA", "Area", "Live or captured area of a bound face set"),
            ("ANGLE", "Angle", "Live direction angle between two persistent edges"),
        ],
        default="LINEAR",
    )

    start: bpy.props.PointerProperty(
        type=CADDIM_PG_Anchor,
    )

    end: bpy.props.PointerProperty(
        type=CADDIM_PG_Anchor,
    )

    center: bpy.props.PointerProperty(
        type=CADDIM_PG_Anchor,
    )

    angle_a_start: bpy.props.PointerProperty(type=CADDIM_PG_Anchor)
    angle_a_end: bpy.props.PointerProperty(type=CADDIM_PG_Anchor)
    angle_b_start: bpy.props.PointerProperty(type=CADDIM_PG_Anchor)
    angle_b_end: bpy.props.PointerProperty(type=CADDIM_PG_Anchor)

    angle_source_mode: bpy.props.EnumProperty(
        name="Angle Source",
        items=[
            ("THREE_POINT", "Legacy Three Point", "Angle defined by three point anchors"),
            ("EDGES", "Two Edges", "Angle follows two persistent mesh edges"),
        ],
        default="THREE_POINT",
        options={"HIDDEN"},
    )

    presentation_offset: bpy.props.FloatVectorProperty(
        name="Placement Offset",
        description="User translation applied to the source-derived annotation placement",
        size=3,
        subtype="TRANSLATION",
        default=(0.0, 0.0, 0.0),
        update=update_dimension_display,
    )

    canonical_location: bpy.props.FloatVectorProperty(
        name="Canonical Placement",
        size=3,
        subtype="XYZ",
        default=(0.0, 0.0, 0.0),
        options={"HIDDEN"},
    )

    placement_initialized: bpy.props.BoolProperty(
        name="Placement Initialized",
        default=False,
        options={"HIDDEN"},
    )

    area_value: bpy.props.FloatProperty(
        name="Area",
        default=0.0,
        min=0.0,
        options={"HIDDEN"},
    )

    measurement_state: bpy.props.EnumProperty(
        name="Measurement State",
        items=[
            ("LIVE", "Live", "Value updates from its bound source geometry"),
            ("CAPTURED", "Captured", "Value is an intentional fixed snapshot"),
            ("NEEDS_REPAIR", "Needs Repair", "Source geometry is missing or ambiguous"),
        ],
        default="LIVE",
        update=update_dimension_display,
    )

    area_source_object: bpy.props.PointerProperty(
        name="Area Source",
        type=bpy.types.Object,
        poll=poll_mesh_objects,
        update=update_dimension_display,
    )

    area_faces: bpy.props.CollectionProperty(type=CADDIM_PG_AreaFaceBinding)

    area_face_count: bpy.props.IntProperty(
        name="Face Count",
        default=0,
        min=0,
        options={"HIDDEN"},
    )

    area_label_direction: bpy.props.FloatVectorProperty(
        name="Area Label Direction",
        description="Persistent world direction from the live Area center to its canonical label",
        size=3,
        subtype="DIRECTION",
        default=(1.0, 0.0, 0.0),
        options={"HIDDEN"},
    )

    area_placement_locked: bpy.props.BoolProperty(
        name="Constrained Area Placement",
        default=False,
        options={"HIDDEN"},
    )

    angle_radius: bpy.props.FloatProperty(
        name="Arc Radius",
        description="World-space radius of the angle arc",
        default=0.25,
        min=0.001,
        soft_max=10.0,
        subtype="DISTANCE",
        update=update_dimension_display,
    )

    angle_mode: bpy.props.EnumProperty(
        name="Angle",
        items=[
            ("MINOR", "Minor", "Show the smaller angle between the rays"),
            ("SUPPLEMENT", "Supplement", "Show the supplementary angle"),
            ("REFLEX", "Reflex", "Show the reflex angle around the opposite side"),
        ],
        default="MINOR",
        update=update_dimension_display,
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

    measurement_mode: bpy.props.EnumProperty(
        name="Measured Distance",
        items=[
            ("TRUE", "True / Aligned", "Measure the true distance between the anchors"),
            ("DELTA_X", "X Projection", "Measure only the global X component"),
            ("DELTA_Y", "Y Projection", "Measure only the global Y component"),
            ("DELTA_Z", "Z Projection", "Measure only the global Z component"),
        ],
        default="TRUE",
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
        update=update_dimension_display,
    )

    color: bpy.props.FloatVectorProperty(
        name="Color",
        subtype="COLOR",
        size=4,
        default=(1.0, 1.0, 1.0, 1.0),
        min=0.0,
        max=1.0,
        update=update_dimension_display,
    )

    selected_color: bpy.props.FloatVectorProperty(
        name="Selected Color",
        subtype="COLOR",
        size=4,
        default=(1.0, 0.72, 0.25, 1.0),
        min=0.0,
        max=1.0,
        update=update_dimension_display,
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
        description="Fixed viewport text size in pixels; view zoom and source transforms do not change it",
        default=DEFAULT_TEXT_SIZE,
        min=8,
        max=64,
        update=update_dimension_display,
    )

    arrow_size: bpy.props.FloatProperty(
        name="Arrow Size",
        description="Fixed viewport arrowhead size in pixels; view zoom and source transforms do not change it",
        default=DEFAULT_ARROW_SIZE,
        min=2.0,
        max=40.0,
        update=update_dimension_display,
    )

    arrow_end_style: bpy.props.EnumProperty(
        name="Arrow End Style",
        description="Presentation mark used at both ends of a linear dimension",
        items=[
            ("ARROW", "Arrow", "Open arrowheads at both dimension-line ends"),
            (
                "ARCHITECTURAL_TICK",
                "Architectural Tick",
                "Diagonal architectural ticks at both dimension-line ends",
            ),
        ],
        default="ARROW",
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

    value_prefix: bpy.props.StringProperty(
        name="Value Prefix",
        description="Text placed immediately before the formatted measurement",
        default="",
        update=update_dimension_display,
    )

    value_suffix: bpy.props.StringProperty(
        name="Value Suffix",
        description="Text placed immediately after the formatted measurement",
        default="",
        update=update_dimension_display,
    )

    tolerance_mode: bpy.props.EnumProperty(
        name="Tolerance",
        items=[
            ("NONE", "None", "Do not display a tolerance"),
            ("SYMMETRIC", "Plus / Minus", "Display one symmetric plus/minus tolerance"),
            ("DEVIATION", "Upper / Lower", "Display independent upper and lower deviations"),
        ],
        default="NONE",
        update=update_dimension_display,
    )

    tolerance_upper: bpy.props.FloatProperty(
        name="Upper Tolerance",
        default=0.0,
        min=0.0,
        subtype="DISTANCE",
        update=update_dimension_display,
    )

    tolerance_lower: bpy.props.FloatProperty(
        name="Lower Tolerance",
        default=0.0,
        min=0.0,
        subtype="DISTANCE",
        update=update_dimension_display,
    )


class CADDIM_PG_Guide(bpy.types.PropertyGroup):
    enabled: bpy.props.BoolProperty(name="Enabled", default=False)
    kind: bpy.props.EnumProperty(
        name="Construction Type",
        items=[
            ("GUIDE", "Infinite Guide", "An infinite construction line"),
            ("MEASUREMENT", "Measurement", "A persistent finite measured segment"),
        ],
        default="GUIDE",
        update=update_dimension_display,
    )
    start: bpy.props.PointerProperty(type=CADDIM_PG_Anchor)
    end: bpy.props.PointerProperty(type=CADDIM_PG_Anchor)
    axis: bpy.props.EnumProperty(
        name="Direction",
        items=[
            ("ALIGNED", "Aligned", "Use the direction between the two anchors"),
            ("X", "X Axis", "Use the global X axis through the start anchor"),
            ("Y", "Y Axis", "Use the global Y axis through the start anchor"),
            ("Z", "Z Axis", "Use the global Z axis through the start anchor"),
        ],
        default="ALIGNED",
        update=update_dimension_display,
    )
    visible: bpy.props.BoolProperty(name="Visible", default=True, update=update_dimension_display)


class CADDIM_PG_SceneSettings(bpy.types.PropertyGroup):
    schema_version: bpy.props.IntProperty(
        name="Dimensions Schema Version",
        description="Internal version of persistent Dimensions scene data",
        default=0,
        min=0,
        options={"HIDDEN"},
    )

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
        update=update_dimension_display,
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
        update=update_dimension_display,
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
        default=(1.0, 1.0, 1.0, 1.0),
        min=0.0,
        max=1.0,
        update=update_dimension_display,
    )

    selected_dimension_color: bpy.props.FloatVectorProperty(
        name="Selected Color",
        subtype="COLOR",
        size=4,
        default=(1.0, 0.72, 0.25, 1.0),
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
        description="Fixed viewport text size in pixels; view zoom and source transforms do not change it",
        default=DEFAULT_TEXT_SIZE,
        min=8,
        max=64,
        update=update_dimension_display,
    )

    dimension_arrow_size: bpy.props.FloatProperty(
        name="Arrow Size",
        description="Fixed viewport arrowhead size in pixels; view zoom and source transforms do not change it",
        default=DEFAULT_ARROW_SIZE,
        min=2.0,
        max=40.0,
        update=update_dimension_display,
    )

    dimension_arrow_end_style: bpy.props.EnumProperty(
        name="Arrow End Style",
        description="Default endpoint presentation for new dimensions",
        items=[
            ("ARROW", "Arrow", "Open arrowheads at both dimension-line ends"),
            (
                "ARCHITECTURAL_TICK",
                "Architectural Tick",
                "Diagonal architectural ticks at both dimension-line ends",
            ),
        ],
        default="ARROW",
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

    snap_pixel_radius: bpy.props.IntProperty(
        name="Snap Radius",
        description="Screen-space capture radius for logical vertices, corners, midpoints, and construction points",
        default=int(DEFAULT_SNAP_PIXEL_THRESHOLD),
        min=8,
        max=64,
        subtype="PIXEL",
    )

    show_overlay_volume: bpy.props.BoolProperty(
        name="Show Volume",
        description="Show evaluated volume for closed selected meshes and N/A for open meshes",
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

    show_construction_guides: bpy.props.BoolProperty(
        name="Show Guides",
        default=True,
        update=update_dimension_display,
    )

    guide_color: bpy.props.FloatVectorProperty(
        name="Guide Color",
        subtype="COLOR",
        size=4,
        default=(0.22, 0.70, 1.0, 0.70),
        min=0.0,
        max=1.0,
        update=update_dimension_display,
    )

    guide_line_width: bpy.props.FloatProperty(
        name="Guide Line Width",
        default=DEFAULT_GUIDE_LINE_WIDTH,
        min=1.0,
        max=5.0,
        update=update_dimension_display,
    )


def is_dimension_object(obj):
    return bool(obj and hasattr(obj, "dimension_props") and obj.dimension_props.enabled)


def is_guide_object(obj):
    return bool(obj and hasattr(obj, "guide_props") and obj.guide_props.enabled)


def apply_scene_style_to_dimension(scene_settings, dimension_props):
    dimension_props.color = tuple(scene_settings.dimension_color)
    dimension_props.selected_color = tuple(scene_settings.selected_dimension_color)
    dimension_props.line_width = scene_settings.dimension_line_width
    dimension_props.text_size = scene_settings.dimension_text_size
    dimension_props.arrow_size = scene_settings.dimension_arrow_size
    dimension_props.arrow_end_style = scene_settings.dimension_arrow_end_style


def apply_dimension_style_to_scene(dimension_props, scene_settings):
    scene_settings.dimension_color = tuple(dimension_props.color)
    scene_settings.selected_dimension_color = tuple(dimension_props.selected_color)
    scene_settings.dimension_line_width = dimension_props.line_width
    scene_settings.dimension_text_size = dimension_props.text_size
    scene_settings.dimension_arrow_size = dimension_props.arrow_size
    scene_settings.dimension_arrow_end_style = dimension_props.arrow_end_style


def register_properties():
    bpy.types.Object.dimension_props = bpy.props.PointerProperty(
        type=CADDIM_PG_Dimension,
    )
    bpy.types.Object.guide_props = bpy.props.PointerProperty(type=CADDIM_PG_Guide)
    bpy.types.Scene.dimensions_settings = bpy.props.PointerProperty(
        type=CADDIM_PG_SceneSettings,
    )


def unregister_properties():
    if hasattr(bpy.types.Object, "guide_props"):
        del bpy.types.Object.guide_props
    if hasattr(bpy.types.Object, "dimension_props"):
        del bpy.types.Object.dimension_props
    if hasattr(bpy.types.Scene, "dimensions_settings"):
        del bpy.types.Scene.dimensions_settings


classes = (
    CADDIM_PG_Anchor,
    CADDIM_PG_AreaFaceBinding,
    CADDIM_PG_Dimension,
    CADDIM_PG_Guide,
    CADDIM_PG_SceneSettings,
)
