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


UNIT_STYLE_ITEMS = [
    ("AUTO", "Auto", "Follow the scene unit configuration"),
    ("METRIC_AUTO", "Metric Auto", "Choose a metric unit from the value"),
    ("MILLIMETERS", "Millimeters", "Display values in millimeters"),
    ("CENTIMETERS", "Centimeters", "Display values in centimeters"),
    ("METERS", "Meters", "Display values in meters"),
    ("FEET_INCHES", "Feet + Inches", "Display values using feet and inches"),
    ("INCH_DECIMAL", "Inches Decimal", "Display values as decimal inches"),
    ("INCH_FRACTION", "Inches Fraction", "Display values as fractional inches"),
    ("BLENDER", "Blender Native", "Use Blender's native unit formatting"),
]

STYLE_PROPERTY_NAMES = (
    "color", "selected_color", "line_width", "text_size", "precision",
    "arrow_size", "arrow_end_style", "start_end_style", "end_end_style",
    "extension_gap", "extension_overshoot", "value_prefix", "value_suffix",
    "tolerance", "unit_style", "secondary_unit_style", "secondary_precision",
    "dual_unit_arrangement", "label_orientation", "label_line_mode",
)

END_STYLE_ITEMS = [
    ("OPEN", "Open Arrow", "Open triangular arrowhead"),
    ("FILLED", "Filled Arrow", "Filled triangular arrowhead"),
    ("ARCHITECTURAL_TICK", "Architectural Tick", "Diagonal architectural tick"),
    ("DOT", "Dot", "Circular endpoint dot"),
    ("NONE", "None", "No endpoint mark"),
]

SECONDARY_UNIT_STYLE_ITEMS = [("NONE", "None", "Show only the primary unit")] + [
    item for item in UNIT_STYLE_ITEMS if item[0] != "AUTO"
]

DUAL_UNIT_ARRANGEMENT_ITEMS = [
    ("BRACKETS", "Primary [Secondary]", "Place the secondary value in square brackets"),
    ("PARENTHESES", "Primary (Secondary)", "Place the secondary value in parentheses"),
    ("STACKED", "Stacked", "Place the secondary value on a second line"),
]

LABEL_ORIENTATION_ITEMS = [
    ("ALIGNED", "Aligned", "Align text with the dimension line"),
    ("HORIZONTAL", "Horizontal", "Keep text horizontal in the view or output camera"),
]

LABEL_LINE_MODE_ITEMS = [
    ("ABOVE", "Above", "Place text above an unbroken dimension line"),
    ("BROKEN", "Broken", "Center text in a break in the dimension line"),
]


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


def update_annotation_manager_index(settings, context):
    try:
        from .annotation_manager import select_manager_index

        select_manager_index(settings, context)
    except (AttributeError, ImportError, RuntimeError):
        pass


def update_annotation_manager_reference(settings, context):
    try:
        from .annotation_manager import capture_reference_object

        capture_reference_object(settings, context)
    except (AttributeError, ImportError, RuntimeError):
        pass


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

    resolution_status: bpy.props.EnumProperty(
        name="Resolution Status",
        items=[
            ("BY_ID", "Resolved by ID", "The source identity resolves uniquely"),
            ("BY_FALLBACK", "Resolved by Fallback", "The stored position is being used because source identity is missing or ambiguous"),
            ("UNRESOLVABLE", "Unresolvable", "The bound source object is unavailable"),
        ],
        default="BY_ID",
        options={"HIDDEN"},
    )

    source_object_name: bpy.props.StringProperty(
        name="Last Source Object",
        description="Last known source object name retained after a binding is lost",
        default="",
        options={"HIDDEN"},
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


class CADDIM_PG_AnnotationStyle(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(name="Name", default="Style", update=update_dimension_display)
    color: bpy.props.FloatVectorProperty(name="Color", subtype="COLOR", size=4, default=(1.0, 1.0, 1.0, 1.0), min=0.0, max=1.0, update=update_dimension_display)
    selected_color: bpy.props.FloatVectorProperty(name="Selected Color", subtype="COLOR", size=4, default=(1.0, 0.72, 0.25, 1.0), min=0.0, max=1.0, update=update_dimension_display)
    line_width: bpy.props.FloatProperty(name="Line Width", default=DEFAULT_LINE_WIDTH, min=1.0, max=10.0, update=update_dimension_display)
    text_size: bpy.props.IntProperty(name="Text Size", default=DEFAULT_TEXT_SIZE, min=8, max=64, update=update_dimension_display)
    precision: bpy.props.IntProperty(name="Precision", default=DEFAULT_PRECISION, min=0, max=8, update=update_dimension_display)
    arrow_size: bpy.props.FloatProperty(name="Arrow Size", default=DEFAULT_ARROW_SIZE, min=2.0, max=40.0, update=update_dimension_display)
    arrow_end_style: bpy.props.EnumProperty(
        name="Arrow End Style",
        items=[("ARROW", "Arrow", "Open arrowheads"), ("ARCHITECTURAL_TICK", "Architectural Tick", "Diagonal ticks")],
        default="ARROW", update=update_dimension_display,
    )
    start_end_style: bpy.props.EnumProperty(name="Start Endpoint", items=END_STYLE_ITEMS, default="OPEN", update=update_dimension_display)
    end_end_style: bpy.props.EnumProperty(name="End Endpoint", items=END_STYLE_ITEMS, default="OPEN", update=update_dimension_display)
    extension_gap: bpy.props.FloatProperty(name="Extension Gap", description="Viewport-pixel gap between source and extension line", default=0.0, min=0.0, max=100.0, update=update_dimension_display)
    extension_overshoot: bpy.props.FloatProperty(name="Extension Overshoot", description="Viewport-pixel extension beyond the dimension line", default=0.0, min=0.0, max=100.0, update=update_dimension_display)
    value_prefix: bpy.props.StringProperty(name="Prefix", default="", update=update_dimension_display)
    value_suffix: bpy.props.StringProperty(name="Suffix", default="", update=update_dimension_display)
    tolerance_mode: bpy.props.EnumProperty(
        name="Tolerance",
        items=[("NONE", "None", "No tolerance"), ("SYMMETRIC", "Plus / Minus", "Symmetric tolerance"), ("DEVIATION", "Upper / Lower", "Independent deviations")],
        default="NONE", update=update_dimension_display,
    )
    tolerance_upper: bpy.props.FloatProperty(name="Upper Tolerance", default=0.0, min=0.0, subtype="DISTANCE", update=update_dimension_display)
    tolerance_lower: bpy.props.FloatProperty(name="Lower Tolerance", default=0.0, min=0.0, subtype="DISTANCE", update=update_dimension_display)
    unit_style: bpy.props.EnumProperty(name="Unit Format", items=UNIT_STYLE_ITEMS, default="AUTO", update=update_dimension_display)
    secondary_unit_style: bpy.props.EnumProperty(name="Secondary Unit", items=SECONDARY_UNIT_STYLE_ITEMS, default="NONE", update=update_dimension_display)
    secondary_precision: bpy.props.IntProperty(name="Secondary Precision", default=2, min=0, max=8, update=update_dimension_display)
    dual_unit_arrangement: bpy.props.EnumProperty(name="Dual Unit Arrangement", items=DUAL_UNIT_ARRANGEMENT_ITEMS, default="BRACKETS", update=update_dimension_display)
    label_orientation: bpy.props.EnumProperty(name="Label Orientation", items=LABEL_ORIENTATION_ITEMS, default="HORIZONTAL", update=update_dimension_display)
    label_line_mode: bpy.props.EnumProperty(name="Label Line", items=LABEL_LINE_MODE_ITEMS, default="BROKEN", update=update_dimension_display)


class CADDIM_PG_AnnotationManagerItem(bpy.types.PropertyGroup):
    annotation: bpy.props.PointerProperty(type=bpy.types.Object)
    kind: bpy.props.StringProperty(default="")
    state: bpy.props.StringProperty(default="")
    display_value: bpy.props.StringProperty(default="")


class CADDIM_PG_AnnotationIsolateRecord(bpy.types.PropertyGroup):
    annotation: bpy.props.PointerProperty(type=bpy.types.Object)
    was_hidden: bpy.props.BoolProperty(default=False)
    was_property_visible: bpy.props.BoolProperty(default=True)


class CADDIM_PG_DimensionSetMember(bpy.types.PropertyGroup):
    """One independently repairable source binding inside a dimension set."""

    start: bpy.props.PointerProperty(type=CADDIM_PG_Anchor)
    end: bpy.props.PointerProperty(type=CADDIM_PG_Anchor)
    measurement_state: bpy.props.EnumProperty(
        name="State",
        items=[
            ("LIVE", "Live", "Both member anchors resolve to their sources"),
            ("FALLBACK", "Fallback", "A stored source position is in use"),
            ("NEEDS_REPAIR", "Needs Repair", "A member source is missing or ambiguous"),
        ],
        default="LIVE",
        options={"HIDDEN"},
    )

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
            ("DIMENSION_SET", "Dimension Set", "Persistent chain or baseline dimension set"),
            ("CIRCLE", "Radial / Diameter / Arc", "Dimension fitted to persistent circular mesh points"),
            ("COORDINATE", "Coordinate", "Point coordinates relative to a named datum"),
            ("ELEVATION", "Elevation", "Point elevation relative to a named datum or elevation"),
        ],
        default="LINEAR",
    )

    start: bpy.props.PointerProperty(
        type=CADDIM_PG_Anchor,
    )

    end: bpy.props.PointerProperty(
        type=CADDIM_PG_Anchor,
    )

    datum_object: bpy.props.PointerProperty(
        name="Datum", type=bpy.types.Object, update=update_dimension_display,
    )
    coordinate_components: bpy.props.EnumProperty(
        name="Components", items=[
            ("X", "X", "Show X only"), ("Y", "Y", "Show Y only"),
            ("XY", "X + Y", "Show X and Y"), ("XYZ", "X + Y + Z", "Show all axes"),
        ], default="XY", update=update_dimension_display,
    )
    coordinate_alignment: bpy.props.EnumProperty(
        name="Alignment", items=[
            ("FREE", "Free", "Use this annotation's label position"),
            ("ROW", "Row", "Align labels sharing a datum to a horizontal row"),
            ("COLUMN", "Column", "Align labels sharing a datum to a vertical column"),
        ], default="FREE", update=update_dimension_display,
    )
    coordinate_alignment_offset: bpy.props.FloatProperty(
        name="Alignment Offset", default=0.0, subtype="DISTANCE", update=update_dimension_display,
    )
    coordinate_sign: bpy.props.EnumProperty(
        name="Sign Convention", items=[
            ("DATUM", "Datum Axes", "Use the datum's positive axes"),
            ("REVERSED", "Reversed", "Reverse the datum axis signs"),
        ], default="DATUM", update=update_dimension_display,
    )
    coordinate_show_plus: bpy.props.BoolProperty(
        name="Show Positive Sign", default=False, update=update_dimension_display,
    )
    coordinate_show_negative: bpy.props.BoolProperty(
        name="Show Negative Sign", default=True, update=update_dimension_display,
    )
    elevation_axis: bpy.props.EnumProperty(
        name="Up Axis", items=[
            ("DATUM_Z", "Datum Z", "Use the datum's local Z axis"),
            ("WORLD_X", "World X", "Use world X"), ("WORLD_Y", "World Y", "Use world Y"),
            ("WORLD_Z", "World Z", "Use world Z"),
        ], default="WORLD_Z", update=update_dimension_display,
    )
    elevation_mode: bpy.props.EnumProperty(
        name="Elevation Mode", items=[
            ("ABSOLUTE", "Absolute", "Measure from the named datum"),
            ("RELATIVE", "Relative", "Measure from another elevation annotation"),
        ], default="ABSOLUTE", update=update_dimension_display,
    )
    elevation_reference: bpy.props.PointerProperty(
        name="Relative To", type=bpy.types.Object, update=update_dimension_display,
    )
    elevation_precision: bpy.props.IntProperty(
        name="Elevation Precision", default=3, min=0, max=8, update=update_dimension_display,
    )
    elevation_show_plus: bpy.props.BoolProperty(
        name="Show Positive Sign", default=True, update=update_dimension_display,
    )
    elevation_prefix: bpy.props.StringProperty(
        name="Elevation Prefix", default="", update=update_dimension_display,
    )
    elevation_suffix: bpy.props.StringProperty(
        name="Elevation Suffix", default="", update=update_dimension_display,
    )

    set_kind: bpy.props.EnumProperty(
        name="Set Type",
        items=[
            ("CHAIN", "Chain", "Sequential dimensions sharing one dimension line"),
            ("BASELINE", "Baseline", "Dimensions from one datum on automatically spaced rows"),
        ],
        default="CHAIN",
        update=update_dimension_display,
    )
    set_members: bpy.props.CollectionProperty(type=CADDIM_PG_DimensionSetMember)
    active_set_member_index: bpy.props.IntProperty(name="Active Member", default=0, min=0)
    set_spacing: bpy.props.FloatProperty(
        name="Baseline Spacing",
        description="Zero uses automatic spacing derived from text size",
        default=0.0,
        min=0.0,
        soft_max=10.0,
        subtype="DISTANCE",
        update=update_dimension_display,
    )
    set_expanded: bpy.props.BoolProperty(name="Expand Members", default=False)

    circle_kind: bpy.props.EnumProperty(
        name="Circular Dimension",
        items=[
            ("RADIUS", "Radius", "Show the fitted radius with an R prefix"),
            ("DIAMETER", "Diameter", "Show the fitted diameter with a diameter prefix"),
            ("ARC_LENGTH", "Arc Length", "Show length along the bound fitted arc"),
        ], default="RADIUS", update=update_dimension_display,
    )
    circle_fit_mode: bpy.props.EnumProperty(
        name="Measurement",
        items=[
            ("FITTED", "Fitted", "Least-squares fitted radius"),
            ("INSCRIBED", "Inscribed", "Across-flats radius of the selected polygon"),
            ("CIRCUMSCRIBED", "Circumscribed", "Largest radius from the fitted center"),
        ], default="FITTED", update=update_dimension_display,
    )
    circle_source_object: bpy.props.PointerProperty(name="Circle Source", type=bpy.types.Object, poll=poll_mesh_objects, update=update_dimension_display)
    circle_vertices: bpy.props.CollectionProperty(type=CADDIM_PG_Anchor)
    circle_closed: bpy.props.BoolProperty(name="Closed Circle", default=True, options={"HIDDEN"})
    circle_fit_error: bpy.props.FloatProperty(name="Relative Fit Error", default=0.0, min=0.0, options={"HIDDEN"})
    circle_fit_warning_threshold: bpy.props.FloatProperty(name="Fit Warning", description="Relative RMS error above which the fit is not authoritative", default=0.02, min=0.0001, max=1.0, precision=4, update=update_dimension_display)
    circle_center: bpy.props.FloatVectorProperty(name="Fitted Center", size=3, subtype="XYZ", options={"HIDDEN"})
    circle_normal: bpy.props.FloatVectorProperty(name="Fitted Plane Normal", size=3, subtype="DIRECTION", default=(0.0, 0.0, 1.0), options={"HIDDEN"})
    circle_start_direction: bpy.props.FloatVectorProperty(name="Arc Start Direction", size=3, subtype="DIRECTION", default=(1.0, 0.0, 0.0), options={"HIDDEN"})
    circle_radius: bpy.props.FloatProperty(name="Fitted Radius", default=0.0, min=0.0, options={"HIDDEN"})
    circle_sweep: bpy.props.FloatProperty(name="Arc Sweep", default=6.283185307179586, min=0.0, max=6.283185307179586, options={"HIDDEN"})
    circle_leader_angle: bpy.props.FloatProperty(name="Leader Angle", default=0.7853981633974483, subtype="ANGLE", update=update_dimension_display)
    circle_label_distance: bpy.props.FloatProperty(name="Label Distance", default=0.0, min=0.0, subtype="DISTANCE", update=update_dimension_display)

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
            ("FALLBACK", "Fallback", "Value uses a visible stored-position fallback pending confirmation"),
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

    style_name: bpy.props.StringProperty(
        name="Style", description="Named scene style; empty uses scene defaults",
        default="", update=update_dimension_display,
    )
    override_color: bpy.props.BoolProperty(default=False, options={"HIDDEN"}, update=update_dimension_display)
    override_selected_color: bpy.props.BoolProperty(default=False, options={"HIDDEN"}, update=update_dimension_display)
    override_line_width: bpy.props.BoolProperty(default=False, options={"HIDDEN"}, update=update_dimension_display)
    override_text_size: bpy.props.BoolProperty(default=False, options={"HIDDEN"}, update=update_dimension_display)
    override_precision: bpy.props.BoolProperty(default=False, options={"HIDDEN"}, update=update_dimension_display)
    override_arrow_size: bpy.props.BoolProperty(default=False, options={"HIDDEN"}, update=update_dimension_display)
    override_arrow_end_style: bpy.props.BoolProperty(default=False, options={"HIDDEN"}, update=update_dimension_display)
    override_start_end_style: bpy.props.BoolProperty(default=False, options={"HIDDEN"}, update=update_dimension_display)
    override_end_end_style: bpy.props.BoolProperty(default=False, options={"HIDDEN"}, update=update_dimension_display)
    override_extension_gap: bpy.props.BoolProperty(default=False, options={"HIDDEN"}, update=update_dimension_display)
    override_extension_overshoot: bpy.props.BoolProperty(default=False, options={"HIDDEN"}, update=update_dimension_display)
    override_value_prefix: bpy.props.BoolProperty(default=False, options={"HIDDEN"}, update=update_dimension_display)
    override_value_suffix: bpy.props.BoolProperty(default=False, options={"HIDDEN"}, update=update_dimension_display)
    override_tolerance: bpy.props.BoolProperty(default=False, options={"HIDDEN"}, update=update_dimension_display)
    override_unit_style: bpy.props.BoolProperty(default=False, options={"HIDDEN"}, update=update_dimension_display)
    override_secondary_unit_style: bpy.props.BoolProperty(default=False, options={"HIDDEN"}, update=update_dimension_display)
    override_secondary_precision: bpy.props.BoolProperty(default=False, options={"HIDDEN"}, update=update_dimension_display)
    override_dual_unit_arrangement: bpy.props.BoolProperty(default=False, options={"HIDDEN"}, update=update_dimension_display)
    override_label_orientation: bpy.props.BoolProperty(default=False, options={"HIDDEN"}, update=update_dimension_display)
    override_label_line_mode: bpy.props.BoolProperty(default=False, options={"HIDDEN"}, update=update_dimension_display)

    precision: bpy.props.IntProperty(name="Precision", default=DEFAULT_PRECISION, min=0, max=8, update=update_dimension_display)
    unit_style: bpy.props.EnumProperty(name="Unit Format", items=UNIT_STYLE_ITEMS, default="AUTO", update=update_dimension_display)
    secondary_unit_style: bpy.props.EnumProperty(name="Secondary Unit", items=SECONDARY_UNIT_STYLE_ITEMS, default="NONE", update=update_dimension_display)
    secondary_precision: bpy.props.IntProperty(name="Secondary Precision", default=2, min=0, max=8, update=update_dimension_display)
    dual_unit_arrangement: bpy.props.EnumProperty(name="Dual Unit Arrangement", items=DUAL_UNIT_ARRANGEMENT_ITEMS, default="BRACKETS", update=update_dimension_display)
    label_orientation: bpy.props.EnumProperty(name="Label Orientation", items=LABEL_ORIENTATION_ITEMS, default="HORIZONTAL", update=update_dimension_display)
    label_line_mode: bpy.props.EnumProperty(name="Label Line", items=LABEL_LINE_MODE_ITEMS, default="BROKEN", update=update_dimension_display)

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
    start_end_style: bpy.props.EnumProperty(name="Start Endpoint", items=END_STYLE_ITEMS, default="OPEN", update=update_dimension_display)
    end_end_style: bpy.props.EnumProperty(name="End Endpoint", items=END_STYLE_ITEMS, default="OPEN", update=update_dimension_display)
    extension_gap: bpy.props.FloatProperty(name="Extension Gap", description="Viewport-pixel gap between source and extension line", default=0.0, min=0.0, max=100.0, update=update_dimension_display)
    extension_overshoot: bpy.props.FloatProperty(name="Extension Overshoot", description="Viewport-pixel extension beyond the dimension line", default=0.0, min=0.0, max=100.0, update=update_dimension_display)

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


class CADDIM_PG_GuideSource(bpy.types.PropertyGroup):
    kind: bpy.props.EnumProperty(
        name="Source Type",
        items=[
            ("NONE", "None", "No derived source"),
            ("EDGE", "Edge", "A persistent mesh edge source"),
            ("GUIDE", "Guide", "Another construction guide"),
            ("FACE", "Face", "A persistent mesh face plane"),
        ],
        default="NONE",
    )
    target_object: bpy.props.PointerProperty(name="Mesh Source", type=bpy.types.Object, poll=poll_mesh_objects)
    guide_object: bpy.props.PointerProperty(name="Guide Source", type=bpy.types.Object)
    start: bpy.props.PointerProperty(type=CADDIM_PG_Anchor)
    end: bpy.props.PointerProperty(type=CADDIM_PG_Anchor)
    face_id: bpy.props.IntProperty(name="Persistent Face ID", default=0, min=0)
    face_vertex_count: bpy.props.IntProperty(name="Face Vertex Count", default=0, min=0)
    fallback_center: bpy.props.FloatVectorProperty(name="Fallback Center", size=3, subtype="XYZ")
    fallback_normal: bpy.props.FloatVectorProperty(
        name="Fallback Normal", size=3, subtype="XYZ", default=(0.0, 0.0, 1.0),
    )
    source_name: bpy.props.StringProperty(name="Last Source", default="", options={"HIDDEN"})


class CADDIM_PG_Guide(bpy.types.PropertyGroup):
    enabled: bpy.props.BoolProperty(name="Enabled", default=False)
    kind: bpy.props.EnumProperty(
        name="Construction Type",
        items=[
            ("GUIDE", "Infinite Guide", "An infinite construction line"),
            ("MEASUREMENT", "Measurement", "A persistent finite measured segment"),
            ("POINT", "Guide Point", "A persistent construction point"),
            ("PLANE", "Guide Plane", "A persistent bounded construction plane"),
        ],
        default="GUIDE",
        update=update_dimension_display,
    )
    start: bpy.props.PointerProperty(type=CADDIM_PG_Anchor)
    end: bpy.props.PointerProperty(type=CADDIM_PG_Anchor)
    is_datum: bpy.props.BoolProperty(
        name="Datum", description="Use this guide point as an oriented measurement datum",
        default=False, update=update_dimension_display,
    )
    datum_name: bpy.props.StringProperty(
        name="Datum Name", default="Datum", update=update_dimension_display,
    )
    datum_orientation: bpy.props.FloatVectorProperty(
        name="Datum Orientation", description="Local datum axes", size=3, subtype="EULER",
        default=(0.0, 0.0, 0.0), update=update_dimension_display,
    )
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
    derived: bpy.props.BoolProperty(name="Derived", default=False, options={"HIDDEN"})
    derivation_mode: bpy.props.EnumProperty(
        name="Derivation",
        items=[
            ("NONE", "Fixed", "A fixed guide"),
            ("OFFSET", "Offset", "Offset from one edge, guide, or face"),
            ("CENTERLINE", "Centerline", "Midway between two parallel sources"),
            ("ANGULAR", "Angular", "Rotate a source direction about an anchored pivot"),
            ("SPACING", "Repeated Spacing", "One definition producing parallel snap lines"),
        ],
        default="NONE",
    )
    source_a: bpy.props.PointerProperty(type=CADDIM_PG_GuideSource)
    source_b: bpy.props.PointerProperty(type=CADDIM_PG_GuideSource)
    construction_pivot: bpy.props.PointerProperty(type=CADDIM_PG_Anchor)
    spacing_end: bpy.props.PointerProperty(type=CADDIM_PG_Anchor)
    guide_angle: bpy.props.FloatProperty(name="Angle", default=0.7853981633974483, subtype="ANGLE", update=update_dimension_display)
    spacing_mode: bpy.props.EnumProperty(
        name="Spacing Mode", items=[
            ("COUNT", "Interval + Count", "Repeat at an interval for a fixed count"),
            ("EXTENT", "Interval + Extent", "Repeat at an interval until an extent"),
            ("DISTRIBUTE", "Distribute Evenly", "Distribute a fixed count across an extent"),
        ], default="COUNT", update=update_dimension_display,
    )
    spacing_interval: bpy.props.FloatProperty(name="Interval", default=1.0, min=0.000001, subtype="DISTANCE", update=update_dimension_display)
    spacing_count: bpy.props.IntProperty(name="Count", default=5, min=2, max=10000, update=update_dimension_display)
    spacing_extent: bpy.props.FloatProperty(name="Extent", default=4.0, min=0.000001, subtype="DISTANCE", update=update_dimension_display)
    offset_distance: bpy.props.FloatProperty(name="Offset", default=0.0, min=0.0, subtype="DISTANCE")
    offset_side: bpy.props.IntProperty(name="Side", default=1, min=-1, max=1)
    derived_direction: bpy.props.FloatVectorProperty(
        name="Derived Direction", size=3, subtype="DIRECTION", default=(0.0, 1.0, 0.0),
    )
    derived_state: bpy.props.EnumProperty(
        name="Derived State",
        items=[
            ("LIVE", "Live", "Every derived source resolves"),
            ("NEEDS_REPAIR", "Needs Repair", "A source is missing or invalid"),
            ("CYCLE", "Cycle", "The guide dependency contains a cycle"),
        ],
        default="LIVE",
        options={"HIDDEN"},
    )
    last_resolved_origin: bpy.props.FloatVectorProperty(name="Last Origin", size=3, subtype="XYZ", options={"HIDDEN"})
    last_resolved_direction: bpy.props.FloatVectorProperty(
        name="Last Direction", size=3, subtype="DIRECTION", default=(1.0, 0.0, 0.0), options={"HIDDEN"},
    )
    plane_definition: bpy.props.EnumProperty(
        name="Plane Definition",
        items=[
            ("THREE_POINTS", "Three Points", "Plane through three persistent points"),
            ("POINT_NORMAL", "Point + Normal", "Plane through one point with a stored normal"),
            ("FACE", "Face", "Plane following a persistent mesh face"),
            ("OFFSET", "Offset", "Plane offset from another guide plane"),
        ],
        default="POINT_NORMAL",
    )
    plane_point_a: bpy.props.PointerProperty(type=CADDIM_PG_Anchor)
    plane_point_b: bpy.props.PointerProperty(type=CADDIM_PG_Anchor)
    plane_point_c: bpy.props.PointerProperty(type=CADDIM_PG_Anchor)
    plane_normal: bpy.props.FloatVectorProperty(
        name="Normal", size=3, subtype="DIRECTION", default=(0.0, 0.0, 1.0),
    )
    plane_axis_u: bpy.props.FloatVectorProperty(
        name="In-Plane X", size=3, subtype="DIRECTION", default=(1.0, 0.0, 0.0),
    )
    plane_extent: bpy.props.FloatProperty(
        name="Grid Extent", description="Presentation-only half-size of the bounded plane grid",
        default=2.0, min=0.01, soft_max=100.0, subtype="DISTANCE", update=update_dimension_display,
    )
    plane_state: bpy.props.EnumProperty(
        name="Plane State",
        items=[
            ("LIVE", "Live", "Every plane source resolves"),
            ("NEEDS_REPAIR", "Needs Repair", "A plane source is missing or degenerate"),
            ("CYCLE", "Cycle", "The plane dependency contains a cycle"),
        ],
        default="LIVE", options={"HIDDEN"},
    )


class CADDIM_PG_OutputSourceBinding(bpy.types.PropertyGroup):
    """Scene-owned identity for one generated-output source annotation."""

    source: bpy.props.PointerProperty(type=bpy.types.Object)
    key: bpy.props.StringProperty(default="", options={"HIDDEN"})


class CADDIM_PG_SceneSettings(bpy.types.PropertyGroup):
    schema_version: bpy.props.IntProperty(
        name="Dimensions Schema Version",
        description="Internal version of persistent Dimensions scene data",
        default=0,
        min=0,
        options={"HIDDEN"},
    )

    annotation_styles: bpy.props.CollectionProperty(type=CADDIM_PG_AnnotationStyle)
    active_annotation_style_index: bpy.props.IntProperty(default=0, min=0)
    annotation_manager_items: bpy.props.CollectionProperty(
        type=CADDIM_PG_AnnotationManagerItem,
        options={"HIDDEN"},
    )
    active_annotation_manager_index: bpy.props.IntProperty(
        default=-1, min=-1, update=update_annotation_manager_index,
    )
    annotation_manager_search: bpy.props.StringProperty(name="Search", default="")
    annotation_manager_kind_linear: bpy.props.BoolProperty(name="Linear", default=True)
    annotation_manager_kind_dimension_set: bpy.props.BoolProperty(name="Sets", default=True)
    annotation_manager_kind_circle: bpy.props.BoolProperty(name="Circular", default=True)
    annotation_manager_kind_angle: bpy.props.BoolProperty(name="Angle", default=True)
    annotation_manager_kind_area: bpy.props.BoolProperty(name="Area", default=True)
    annotation_manager_kind_measurement: bpy.props.BoolProperty(name="Measurement", default=True)
    annotation_manager_kind_guide: bpy.props.BoolProperty(name="Guide", default=True)
    annotation_manager_kind_point: bpy.props.BoolProperty(name="Point", default=True)
    annotation_manager_kind_plane: bpy.props.BoolProperty(name="Plane", default=True)
    annotation_manager_kind_coordinate: bpy.props.BoolProperty(name="Coordinate", default=True)
    annotation_manager_kind_elevation: bpy.props.BoolProperty(name="Elevation", default=True)
    annotation_manager_kind_datum: bpy.props.BoolProperty(name="Datum", default=True)
    annotation_manager_state_live: bpy.props.BoolProperty(name="Live", default=True)
    annotation_manager_state_fallback: bpy.props.BoolProperty(name="Fallback", default=True)
    annotation_manager_state_captured: bpy.props.BoolProperty(name="Captured", default=True)
    annotation_manager_state_needs_repair: bpy.props.BoolProperty(name="Needs Repair", default=True)
    annotation_manager_references_active: bpy.props.BoolProperty(
        name="References Active", default=False, update=update_annotation_manager_reference,
    )
    annotation_manager_reference_object: bpy.props.PointerProperty(
        name="Reference Object", type=bpy.types.Object,
    )
    annotation_manager_bulk_scope: bpy.props.EnumProperty(
        name="Bulk Scope",
        items=[
            ("FILTERED", "Filtered", "Operate on every row matching the manager filters"),
            ("SELECTED", "Selected", "Operate on selected managed objects"),
        ],
        default="FILTERED",
    )
    annotation_manager_isolate_records: bpy.props.CollectionProperty(
        type=CADDIM_PG_AnnotationIsolateRecord,
        options={"HIDDEN"},
    )
    annotation_manager_isolate_active: bpy.props.BoolProperty(default=False, options={"HIDDEN"})

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
    dimension_start_end_style: bpy.props.EnumProperty(name="Start Endpoint", items=END_STYLE_ITEMS, default="OPEN", update=update_dimension_display)
    dimension_end_end_style: bpy.props.EnumProperty(name="End Endpoint", items=END_STYLE_ITEMS, default="OPEN", update=update_dimension_display)
    dimension_extension_gap: bpy.props.FloatProperty(name="Extension Gap", description="Viewport-pixel source gap", default=0.0, min=0.0, max=100.0, update=update_dimension_display)
    dimension_extension_overshoot: bpy.props.FloatProperty(name="Extension Overshoot", description="Viewport-pixel overshoot beyond the dimension line", default=0.0, min=0.0, max=100.0, update=update_dimension_display)
    dimension_secondary_unit_style: bpy.props.EnumProperty(name="Secondary Unit", items=SECONDARY_UNIT_STYLE_ITEMS, default="NONE", update=update_dimension_display)
    dimension_secondary_precision: bpy.props.IntProperty(name="Secondary Precision", default=2, min=0, max=8, update=update_dimension_display)
    dimension_dual_unit_arrangement: bpy.props.EnumProperty(name="Dual Unit Arrangement", items=DUAL_UNIT_ARRANGEMENT_ITEMS, default="BRACKETS", update=update_dimension_display)
    dimension_label_orientation: bpy.props.EnumProperty(name="Label Orientation", items=LABEL_ORIENTATION_ITEMS, default="HORIZONTAL", update=update_dimension_display)
    dimension_label_line_mode: bpy.props.EnumProperty(name="Label Line", items=LABEL_LINE_MODE_ITEMS, default="BROKEN", update=update_dimension_display)

    output_sizing_mode: bpy.props.EnumProperty(
        name="Output Sizing",
        description="Use camera pixels or explicit scene units for generated Grease Pencil output",
        items=[
            ("CAMERA", "Camera Relative", "Convert output sizes from pixels at each annotation depth"),
            ("WORLD", "World Scale", "Use the configured output sizes as scene units"),
        ],
        default="CAMERA",
        update=update_dimension_display,
    )

    output_line_width: bpy.props.FloatProperty(
        name="Camera Line Width",
        description="Generated line width in output pixels for Camera Relative sizing",
        default=2.0,
        min=0.1,
        max=100.0,
        update=update_dimension_display,
    )

    output_text_height: bpy.props.FloatProperty(
        name="Camera Text Height",
        description="Generated vector-label height in output pixels for Camera Relative sizing",
        default=14.0,
        min=1.0,
        max=100.0,
        update=update_dimension_display,
    )

    output_arrow_size: bpy.props.FloatProperty(
        name="Camera Arrow Size",
        description="Generated endpoint size in output pixels for Camera Relative sizing",
        default=10.0,
        min=1.0,
        max=100.0,
        update=update_dimension_display,
    )

    output_world_line_width: bpy.props.FloatProperty(
        name="World Line Width",
        description="Generated line width in scene units for World Scale sizing",
        default=0.01,
        min=0.0001,
        max=10.0,
        subtype="DISTANCE",
        update=update_dimension_display,
    )

    output_world_text_height: bpy.props.FloatProperty(
        name="World Text Height",
        description="Generated vector-label height in scene units for World Scale sizing",
        default=0.2,
        min=0.0001,
        max=100.0,
        subtype="DISTANCE",
        update=update_dimension_display,
    )

    output_world_arrow_size: bpy.props.FloatProperty(
        name="World Arrow Size",
        description="Generated endpoint size in scene units for World Scale sizing",
        default=0.15,
        min=0.0001,
        max=100.0,
        subtype="DISTANCE",
        update=update_dimension_display,
    )

    output_scope: bpy.props.EnumProperty(
        name="Output Scope",
        description="Choose which visible annotations receive generated output",
        items=[
            ("SELECTED", "Selected", "Generate output for selected visible annotations"),
            ("VISIBLE", "Visible", "Generate output for every visible annotation"),
        ],
        default="VISIBLE",
        update=update_dimension_display,
    )

    output_source_bindings: bpy.props.CollectionProperty(
        type=CADDIM_PG_OutputSourceBinding,
        options={"HIDDEN"},
    )

    vector_paper_size: bpy.props.EnumProperty(
        name="Paper Size",
        description="Physical page size for SVG and PDF export",
        items=[
            ("A4", "A4", "210 × 297 mm"),
            ("A3", "A3", "297 × 420 mm"),
            ("LETTER", "US Letter", "8.5 × 11 inches"),
        ],
        default="A4",
    )

    vector_orientation: bpy.props.EnumProperty(
        name="Orientation",
        items=[
            ("PORTRAIT", "Portrait", "Use the paper's shorter edge as its width"),
            ("LANDSCAPE", "Landscape", "Use the paper's longer edge as its width"),
        ],
        default="PORTRAIT",
    )

    vector_scale_denominator: bpy.props.FloatProperty(
        name="Drawing Scale 1 :",
        description="Model-to-paper scale denominator; 10 exports at 1:10",
        default=10.0,
        min=0.01,
        max=100000.0,
        precision=2,
    )

    vector_line_width_mm: bpy.props.FloatProperty(
        name="Line Weight",
        description="Physical exported stroke width in millimetres",
        default=0.25,
        min=0.05,
        max=5.0,
        precision=2,
    )

    vector_text_height_mm: bpy.props.FloatProperty(
        name="Text Height",
        description="Physical exported vector-label height in millimetres",
        default=3.5,
        min=0.5,
        max=25.0,
        precision=2,
    )

    vector_arrow_size_mm: bpy.props.FloatProperty(
        name="Endpoint Size",
        description="Physical exported arrow or tick size in millimetres",
        default=2.5,
        min=0.5,
        max=25.0,
        precision=2,
    )

    text_placement: bpy.props.EnumProperty(
        name="Text Placement",
        items=[
            ("INLINE", "Inline (Gap)", "Center values in a break in each dimension line"),
            ("ABOVE", "Above Line", "Place values above their dimension lines"),
            ("OUTSIDE", "Outside End", "Place values beyond their end arrows"),
            ("OUTSIDE_START", "Outside Start", "Place values beyond their start arrows"),
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
    use_snap_target_override: bpy.props.BoolProperty(
        name="Override Snap Targets",
        description="Store snap-target choices in this scene instead of using add-on preferences",
        default=False,
        update=update_dimension_display,
    )
    snap_vertex: bpy.props.BoolProperty(name="Vertex", default=True, update=update_dimension_display)
    snap_edge: bpy.props.BoolProperty(name="Edge", default=True, update=update_dimension_display)
    snap_midpoint: bpy.props.BoolProperty(name="Midpoint", default=True, update=update_dimension_display)
    snap_face_center: bpy.props.BoolProperty(name="Face Center", default=True, update=update_dimension_display)
    snap_face_point: bpy.props.BoolProperty(name="Face Point", default=True, update=update_dimension_display)
    snap_guide: bpy.props.BoolProperty(name="Guide", default=True, update=update_dimension_display)
    snap_guide_point: bpy.props.BoolProperty(name="Guide Point", default=True, update=update_dimension_display)
    snap_guide_plane: bpy.props.BoolProperty(name="Guide Plane", default=True, update=update_dimension_display)
    snap_measurement_endpoint: bpy.props.BoolProperty(
        name="Measurement Endpoint", default=True, update=update_dimension_display
    )
    snap_measurement_midpoint: bpy.props.BoolProperty(
        name="Measurement Midpoint", default=True, update=update_dimension_display
    )
    snap_measurement_segment: bpy.props.BoolProperty(
        name="Measurement Segment", default=True, update=update_dimension_display
    )
    active_plane_mode: bpy.props.EnumProperty(
        name="Active Construction Plane",
        items=[
            ("NONE", "None", "Use view-derived free placement and world axes"),
            ("GUIDE", "Guide Plane", "Use the selected saved guide plane"),
            ("FACE", "Face", "Use a captured mesh face plane"),
            ("VIEW", "Current View", "Use a captured plane facing the current view"),
            ("WORLD_XY", "World XY", "Use the world XY plane"),
            ("WORLD_YZ", "World YZ", "Use the world YZ plane"),
            ("WORLD_ZX", "World ZX", "Use the world ZX plane"),
        ],
        default="NONE", update=update_dimension_display,
    )
    active_plane_object: bpy.props.PointerProperty(
        name="Active Guide Plane", type=bpy.types.Object, update=update_dimension_display,
    )
    active_plane_origin: bpy.props.FloatVectorProperty(
        name="Active Plane Origin", size=3, subtype="XYZ", options={"HIDDEN"},
    )
    active_plane_normal: bpy.props.FloatVectorProperty(
        name="Active Plane Normal", size=3, subtype="DIRECTION", default=(0.0, 0.0, 1.0), options={"HIDDEN"},
    )
    active_plane_axis_u: bpy.props.FloatVectorProperty(
        name="Active Plane X", size=3, subtype="DIRECTION", default=(1.0, 0.0, 0.0), options={"HIDDEN"},
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


def is_read_only_dimensions_object(obj):
    if obj is None:
        return False
    data = getattr(obj, "data", None)
    return bool(
        getattr(obj, "library", None) is not None
        or getattr(data, "library", None) is not None
        or getattr(obj, "override_library", None) is not None
    )


def apply_scene_style_to_dimension(scene_settings, dimension_props):
    dimension_props.color = tuple(scene_settings.dimension_color)
    dimension_props.selected_color = tuple(scene_settings.selected_dimension_color)
    dimension_props.line_width = scene_settings.dimension_line_width
    dimension_props.text_size = scene_settings.dimension_text_size
    dimension_props.arrow_size = scene_settings.dimension_arrow_size
    dimension_props.arrow_end_style = scene_settings.dimension_arrow_end_style
    dimension_props.start_end_style = scene_settings.dimension_start_end_style
    dimension_props.end_end_style = scene_settings.dimension_end_end_style
    dimension_props.extension_gap = scene_settings.dimension_extension_gap
    dimension_props.extension_overshoot = scene_settings.dimension_extension_overshoot
    dimension_props.precision = scene_settings.precision
    dimension_props.unit_style = configured_scene_unit_style(scene_settings)
    dimension_props.secondary_unit_style = scene_settings.dimension_secondary_unit_style
    dimension_props.secondary_precision = scene_settings.dimension_secondary_precision
    dimension_props.dual_unit_arrangement = scene_settings.dimension_dual_unit_arrangement
    dimension_props.label_orientation = scene_settings.dimension_label_orientation
    dimension_props.label_line_mode = scene_settings.dimension_label_line_mode
    dimension_props.value_prefix = ""
    dimension_props.value_suffix = ""
    dimension_props.tolerance_mode = "NONE"
    dimension_props.tolerance_upper = 0.0
    dimension_props.tolerance_lower = 0.0
    dimension_props.style_name = ""
    for property_name in STYLE_PROPERTY_NAMES:
        setattr(dimension_props, f"override_{property_name}", True)


def apply_dimension_style_to_scene(dimension_props, scene_settings):
    scene_settings.dimension_color = tuple(dimension_props.color)
    scene_settings.selected_dimension_color = tuple(dimension_props.selected_color)
    scene_settings.dimension_line_width = dimension_props.line_width
    scene_settings.dimension_text_size = dimension_props.text_size
    scene_settings.dimension_arrow_size = dimension_props.arrow_size
    scene_settings.dimension_arrow_end_style = dimension_props.arrow_end_style
    scene_settings.dimension_start_end_style = dimension_props.start_end_style
    scene_settings.dimension_end_end_style = dimension_props.end_end_style
    scene_settings.dimension_extension_gap = dimension_props.extension_gap
    scene_settings.dimension_extension_overshoot = dimension_props.extension_overshoot
    scene_settings.dimension_secondary_unit_style = dimension_props.secondary_unit_style
    scene_settings.dimension_secondary_precision = dimension_props.secondary_precision
    scene_settings.dimension_dual_unit_arrangement = dimension_props.dual_unit_arrangement
    scene_settings.dimension_label_orientation = dimension_props.label_orientation
    scene_settings.dimension_label_line_mode = dimension_props.label_line_mode
    scene_settings.precision = dimension_props.precision
    scene_settings.unit_style = dimension_props.unit_style
    scene = getattr(scene_settings, "id_data", None)
    unit_system = getattr(getattr(scene, "unit_settings", None), "system", "NONE")
    if unit_system == "METRIC" and dimension_props.unit_style in {
        "AUTO", "METRIC_AUTO", "MILLIMETERS", "CENTIMETERS", "METERS", "BLENDER",
    }:
        scene_settings.metric_unit_style = dimension_props.unit_style
    elif unit_system == "IMPERIAL" and dimension_props.unit_style in {
        "AUTO", "FEET_INCHES", "INCH_DECIMAL", "INCH_FRACTION", "BLENDER",
    }:
        scene_settings.imperial_unit_style = dimension_props.unit_style


def clear_dimension_style_overrides(dimension_props):
    for property_name in STYLE_PROPERTY_NAMES:
        setattr(dimension_props, f"override_{property_name}", False)


def find_annotation_style(scene_settings, name):
    if not name:
        return None
    return next((style for style in scene_settings.annotation_styles if style.name == name), None)


def configured_scene_unit_style(scene_settings):
    scene = getattr(scene_settings, "id_data", None)
    unit_system = getattr(getattr(scene, "unit_settings", None), "system", "NONE")
    if unit_system == "METRIC":
        return scene_settings.metric_unit_style
    if unit_system == "IMPERIAL":
        return scene_settings.imperial_unit_style
    return scene_settings.unit_style


class ResolvedDimensionStyle:
    """Read-only presentation snapshot with source properties as a fallback."""

    def __init__(self, source, values):
        self._source = source
        self.__dict__.update(values)

    def __getattr__(self, name):
        return getattr(self._source, name)


def resolve_dimension_style(scene_settings, dimension_props):
    """Resolve each property once: annotation override, named style, scene default."""
    named_style = find_annotation_style(scene_settings, dimension_props.style_name)
    defaults = {
        "color": tuple(scene_settings.dimension_color),
        "selected_color": tuple(scene_settings.selected_dimension_color),
        "line_width": scene_settings.dimension_line_width,
        "text_size": scene_settings.dimension_text_size,
        "precision": scene_settings.precision,
        "arrow_size": scene_settings.dimension_arrow_size,
        "arrow_end_style": scene_settings.dimension_arrow_end_style,
        "start_end_style": scene_settings.dimension_start_end_style,
        "end_end_style": scene_settings.dimension_end_end_style,
        "extension_gap": scene_settings.dimension_extension_gap,
        "extension_overshoot": scene_settings.dimension_extension_overshoot,
        "value_prefix": "",
        "value_suffix": "",
        "tolerance_mode": "NONE",
        "tolerance_upper": 0.0,
        "tolerance_lower": 0.0,
        "unit_style": configured_scene_unit_style(scene_settings),
        "secondary_unit_style": scene_settings.dimension_secondary_unit_style,
        "secondary_precision": scene_settings.dimension_secondary_precision,
        "dual_unit_arrangement": scene_settings.dimension_dual_unit_arrangement,
        "label_orientation": scene_settings.dimension_label_orientation,
        "label_line_mode": scene_settings.dimension_label_line_mode,
    }
    if named_style is None and not (
        dimension_props.override_color
        or dimension_props.override_selected_color
        or dimension_props.override_line_width
        or dimension_props.override_text_size
        or dimension_props.override_precision
        or dimension_props.override_arrow_size
        or dimension_props.override_arrow_end_style
        or dimension_props.override_start_end_style
        or dimension_props.override_end_end_style
        or dimension_props.override_extension_gap
        or dimension_props.override_extension_overshoot
        or dimension_props.override_value_prefix
        or dimension_props.override_value_suffix
        or dimension_props.override_tolerance
        or dimension_props.override_unit_style
        or dimension_props.override_secondary_unit_style
        or dimension_props.override_secondary_precision
        or dimension_props.override_dual_unit_arrangement
        or dimension_props.override_label_orientation
        or dimension_props.override_label_line_mode
    ):
        return ResolvedDimensionStyle(dimension_props, defaults)
    values = {}
    for property_name in STYLE_PROPERTY_NAMES:
        override = bool(getattr(dimension_props, f"override_{property_name}"))
        if property_name == "tolerance":
            for field in ("tolerance_mode", "tolerance_upper", "tolerance_lower"):
                if override:
                    values[field] = getattr(dimension_props, field)
                elif named_style is not None:
                    values[field] = getattr(named_style, field)
                else:
                    values[field] = defaults[field]
            continue
        if override:
            values[property_name] = getattr(dimension_props, property_name)
        elif named_style is not None:
            values[property_name] = getattr(named_style, property_name)
        else:
            values[property_name] = defaults[property_name]
    return ResolvedDimensionStyle(dimension_props, values)


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
    CADDIM_PG_AnnotationStyle,
    CADDIM_PG_AnnotationManagerItem,
    CADDIM_PG_AnnotationIsolateRecord,
    CADDIM_PG_DimensionSetMember,
    CADDIM_PG_Dimension,
    CADDIM_PG_GuideSource,
    CADDIM_PG_Guide,
    CADDIM_PG_OutputSourceBinding,
    CADDIM_PG_SceneSettings,
)
