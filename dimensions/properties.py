import bpy

from .constants import DEFAULT_OFFSET_DISTANCE, DEFAULT_PRECISION


def poll_mesh_objects(_self, obj):
    return obj is not None and obj.type == "MESH"


def clamp_anchor_vertex_index(anchor):
    obj = anchor.target_object

    if obj is None or obj.type != "MESH":
        anchor.vertex_index = -1
        return

    vertex_count = len(obj.data.vertices)
    if vertex_count == 0:
        anchor.vertex_index = -1
        return

    anchor.vertex_index = max(0, min(anchor.vertex_index, vertex_count - 1))


def update_anchor_target_object(anchor, _context):
    clamp_anchor_vertex_index(anchor)


def update_anchor_vertex_index(anchor, _context):
    clamp_anchor_vertex_index(anchor)


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
        name="Dimension Type",
        items=[
            ("ALIGNED", "Aligned", "True point-to-point distance"),
            ("X", "X Axis", "Distance projected onto the global X axis"),
            ("Y", "Y Axis", "Distance projected onto the global Y axis"),
            ("Z", "Z Axis", "Distance projected onto the global Z axis"),
        ],
        default="ALIGNED",
    )

    offset_distance: bpy.props.FloatProperty(
        name="Offset",
        default=DEFAULT_OFFSET_DISTANCE,
        soft_min=-120.0,
        soft_max=120.0,
        subtype="DISTANCE",
    )

    offset_plane_normal: bpy.props.FloatVectorProperty(
        name="Placement Plane Normal",
        size=3,
        subtype="XYZ",
        default=(0.0, 0.0, 1.0),
    )

    precision: bpy.props.IntProperty(
        name="Precision",
        default=DEFAULT_PRECISION,
        min=0,
        max=8,
    )

    visible: bpy.props.BoolProperty(
        name="Visible",
        default=True,
    )

    locked: bpy.props.BoolProperty(
        name="Locked",
        default=False,
    )

    color: bpy.props.FloatVectorProperty(
        name="Color",
        subtype="COLOR",
        size=4,
        default=(0.9, 0.65, 0.1, 1.0),
        min=0.0,
        max=1.0,
    )

    selected_color: bpy.props.FloatVectorProperty(
        name="Selected Color",
        subtype="COLOR",
        size=4,
        default=(1.0, 0.9, 0.2, 1.0),
        min=0.0,
        max=1.0,
    )


class CADDIM_PG_SceneSettings(bpy.types.PropertyGroup):
    unit_style: bpy.props.EnumProperty(
        name="Unit Style",
        items=[
            ("AUTO", "Auto", "Follow Blender's current unit settings"),
            ("FEET_INCHES", "Feet + Inches", "Display imperial values using feet and inches"),
            ("INCH_DECIMAL", "Inches Decimal", "Display imperial values as decimal inches"),
            ("INCH_FRACTION", "Inches Fraction", "Display imperial values as fractional inches"),
            ("BLENDER", "Blender Native", "Use Blender's default unit formatting"),
        ],
        default="AUTO",
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

    show_selected_object_overlay: bpy.props.BoolProperty(
        name="Show Selected Object HUD",
        default=True,
    )

    show_overlay_object_name: bpy.props.BoolProperty(
        name="Show Object Name",
        default=True,
    )

    enable_click_select: bpy.props.BoolProperty(
        name="Enable Draw Click Select",
        default=True,
    )


def is_dimension_object(obj):
    return bool(obj and hasattr(obj, "dimension_props") and obj.dimension_props.enabled)


def get_anchor_vertex_count(anchor):
    obj = anchor.target_object
    if obj is None or obj.type != "MESH":
        return 0

    return len(obj.data.vertices)


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
