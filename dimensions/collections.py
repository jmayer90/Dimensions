import bpy

from .anchors import resolve_anchor
from .constants import (
    DEFAULT_EMPTY_DISPLAY_SIZE,
    DEFAULT_EMPTY_DISPLAY_TYPE,
    DIMENSION_COLLECTION_NAME,
    GUIDE_COLLECTION_NAME,
)
from .properties import apply_scene_style_to_dimension


MEASUREMENT_SNAP_PROXY_FLAG = "dimensions_measurement_snap_proxy"


def _collection_in_scene(scene, collection):
    if scene.collection == collection:
        return True

    return collection in scene.collection.children_recursive


def _get_or_create_scene_collection(context, base_name, role):
    scene = context.scene

    for collection in scene.collection.children_recursive:
        if collection.get("dimensions_collection_role") == role:
            return collection

    named_collection = bpy.data.collections.get(base_name)
    if named_collection is not None and _collection_in_scene(scene, named_collection):
        named_collection["dimensions_collection_role"] = role
        return named_collection

    collection_name = base_name
    if named_collection is not None:
        collection_name = f"{base_name} ({scene.name})"

    collection = bpy.data.collections.new(collection_name)
    collection["dimensions_collection_role"] = role
    scene.collection.children.link(collection)
    return collection


def get_or_create_dimension_collection(context):
    return _get_or_create_scene_collection(
        context,
        DIMENSION_COLLECTION_NAME,
        "DIMENSIONS",
    )


def create_dimension_object(context, name="DIM Dimension"):
    collection = get_or_create_dimension_collection(context)

    dimension_object = bpy.data.objects.new(name, object_data=None)
    dimension_object.empty_display_type = DEFAULT_EMPTY_DISPLAY_TYPE
    dimension_object.empty_display_size = DEFAULT_EMPTY_DISPLAY_SIZE
    dimension_object.hide_render = True

    collection.objects.link(dimension_object)

    if hasattr(dimension_object, "dimension_props"):
        dimension_object.dimension_props.enabled = True
        settings = getattr(context.scene, "dimensions_settings", None)
        if settings is not None:
            apply_scene_style_to_dimension(settings, dimension_object.dimension_props)

    return dimension_object


def get_or_create_guide_collection(context):
    return _get_or_create_scene_collection(
        context,
        GUIDE_COLLECTION_NAME,
        "GUIDES",
    )


def create_guide_object(context, name="GUIDE Construction Line"):
    collection = get_or_create_guide_collection(context)
    guide_object = bpy.data.objects.new(name, object_data=None)
    guide_object.empty_display_type = DEFAULT_EMPTY_DISPLAY_TYPE
    guide_object.empty_display_size = DEFAULT_EMPTY_DISPLAY_SIZE
    guide_object.hide_render = True
    collection.objects.link(guide_object)
    guide_object.guide_props.enabled = True
    return guide_object


def create_measurement_object(context, name="MEASURE Construction Segment"):
    measurement_object = create_guide_object(context, name)
    measurement_object.guide_props.kind = "MEASUREMENT"
    measurement_object.guide_props.axis = "ALIGNED"
    return measurement_object


def ensure_measurement_snap_proxy(measurement_object, scene=None):
    """Expose fixed measurement endpoints to Blender's native vertex snapper."""
    if (
        measurement_object is None
        or not hasattr(measurement_object, "guide_props")
        or not measurement_object.guide_props.enabled
        or getattr(measurement_object.guide_props, "kind", "GUIDE") != "MEASUREMENT"
    ):
        return None

    start_world, _start_status = resolve_anchor(measurement_object.guide_props.start)
    end_world, _end_status = resolve_anchor(measurement_object.guide_props.end)
    if start_world is None or end_world is None or (end_world - start_world).length < 1e-6:
        return None

    proxy = next(
        (
            child
            for child in measurement_object.children
            if child.get(MEASUREMENT_SNAP_PROXY_FLAG, False)
        ),
        None,
    )
    if proxy is None or proxy.type != "MESH":
        mesh = bpy.data.meshes.new(f"{measurement_object.name} Snap Targets")
        proxy = bpy.data.objects.new(f"{measurement_object.name} Snap Targets", mesh)
        for collection in measurement_object.users_collection:
            collection.objects.link(proxy)
        proxy.parent = measurement_object
        proxy.matrix_parent_inverse = measurement_object.matrix_world.inverted_safe()
        proxy[MEASUREMENT_SNAP_PROXY_FLAG] = True
        proxy.hide_render = True
        proxy.hide_select = True
        proxy.display_type = "WIRE"
        proxy.show_in_front = True

    if (proxy.matrix_world.translation - measurement_object.matrix_world.translation).length > 1e-6:
        proxy.matrix_world = measurement_object.matrix_world.copy()

    inverse = proxy.matrix_world.inverted_safe()
    local_points = [inverse @ start_world, inverse @ end_world]
    geometry_changed = len(proxy.data.vertices) != 2 or any(
        (proxy.data.vertices[index].co - point).length > 1e-6
        for index, point in enumerate(local_points)
    )
    if geometry_changed:
        proxy.data.clear_geometry()
        proxy.data.from_pydata(local_points, [], [])
        proxy.data.update()

    if scene is None:
        scene = getattr(getattr(bpy, "context", None), "scene", None)
    settings = getattr(scene, "dimensions_settings", None)
    globally_visible = settings is None or settings.show_construction_guides
    try:
        measurement_hidden = measurement_object.hide_get()
    except (AttributeError, RuntimeError):
        measurement_hidden = False
    should_hide = (
        not measurement_object.guide_props.visible
        or not globally_visible
        or measurement_object.hide_viewport
        or measurement_hidden
    )
    try:
        if proxy.hide_get() != should_hide:
            proxy.hide_set(should_hide)
    except (AttributeError, RuntimeError):
        proxy.hide_viewport = should_hide
    return proxy


def remove_measurement_snap_proxies(measurement_object):
    for child in list(getattr(measurement_object, "children", ())):
        if not child.get(MEASUREMENT_SNAP_PROXY_FLAG, False):
            continue
        mesh = child.data if child.type == "MESH" else None
        bpy.data.objects.remove(child, do_unlink=True)
        if mesh is not None and mesh.users == 0:
            bpy.data.meshes.remove(mesh)


def remove_orphan_measurement_snap_proxies(scene):
    for obj in list(scene.objects):
        if not obj.get(MEASUREMENT_SNAP_PROXY_FLAG, False):
            continue
        parent = obj.parent
        if (
            parent is not None
            and hasattr(parent, "guide_props")
            and parent.guide_props.enabled
            and getattr(parent.guide_props, "kind", "GUIDE") == "MEASUREMENT"
        ):
            continue
        mesh = obj.data if obj.type == "MESH" else None
        bpy.data.objects.remove(obj, do_unlink=True)
        if mesh is not None and mesh.users == 0:
            bpy.data.meshes.remove(mesh)
