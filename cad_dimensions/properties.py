import bpy

from .constants import DEFAULT_OFFSET_PIXELS, DEFAULT_PRECISION


class CADDIM_PG_Anchor(bpy.types.PropertyGroup):
    target_object: bpy.props.PointerProperty(
        name="Object",
        type=bpy.types.Object,
    )

    vertex_index: bpy.props.IntProperty(
        name="Vertex Index",
        default=-1,
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
        ],
        default="ALIGNED",
    )

    offset_pixels: bpy.props.FloatProperty(
        name="Offset",
        default=DEFAULT_OFFSET_PIXELS,
        min=-1000.0,
        max=1000.0,
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


def is_dimension_object(obj):
    return bool(obj and hasattr(obj, "cad_dimension") and obj.cad_dimension.enabled)


def register_properties():
    bpy.types.Object.cad_dimension = bpy.props.PointerProperty(
        type=CADDIM_PG_Dimension,
    )


def unregister_properties():
    if hasattr(bpy.types.Object, "cad_dimension"):
        del bpy.types.Object.cad_dimension


classes = (
    CADDIM_PG_Anchor,
    CADDIM_PG_Dimension,
)
