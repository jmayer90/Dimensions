import bpy
from mathutils import Matrix

from .anchors import resolve_anchor, set_world_anchor
from .constants import (
    DEFAULT_EMPTY_DISPLAY_TYPE,
    DIMENSION_COLLECTION_NAME,
    GUIDE_COLLECTION_NAME,
)
from .properties import (
    apply_scene_style_to_dimension,
    clear_dimension_style_overrides,
    is_dimension_object,
    is_read_only_dimensions_object,
)
from .preferences import get_preferences


MEASUREMENT_SNAP_PROXY_FLAG = "dimensions_measurement_snap_proxy"
GUIDE_POINT_SNAP_PROXY_FLAG = "dimensions_guide_point_snap_proxy"


def _collection_in_scene(scene, collection):
    if scene.collection == collection:
        return True

    return collection in scene.collection.children_recursive


def _get_or_create_scene_collection(context, base_name, role):
    scene = context.scene

    for collection in scene.collection.children_recursive:
        if (
            collection.get("dimensions_collection_role") == role
            and collection.library is None
            and collection.override_library is None
        ):
            return collection

    named_collection = bpy.data.collections.get(base_name)
    if (
        named_collection is not None
        and named_collection.library is None
        and named_collection.override_library is None
        and _collection_in_scene(scene, named_collection)
    ):
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


def get_scene_collection(scene, role):
    """Return a Dimensions-owned collection without creating data during drawing."""
    if scene is None:
        return None
    collections = tuple(
        collection for collection in scene.collection.children_recursive
        if collection.get("dimensions_collection_role") == role
    )
    for collection in collections:
        if collection.library is None and collection.override_library is None:
            return collection
    return collections[0] if collections else None


def iter_scene_role_objects(scene, role):
    """Yield each owned object once across local and linked role collections."""
    if scene is None:
        return
    collections = tuple(
        collection for collection in scene.collection.children_recursive
        if collection.get("dimensions_collection_role") == role
    )
    if len(collections) == 1:
        yield from collections[0].all_objects
        return
    seen = set()
    for collection in collections:
        for obj in collection.all_objects:
            pointer = obj.as_pointer()
            if pointer not in seen:
                seen.add(pointer)
                yield obj


def create_dimension_object(context, name="DIM Dimension"):
    from .migrations import prepare_scene_for_write

    prepare_scene_for_write(context.scene)
    collection = get_or_create_dimension_collection(context)

    dimension_object = bpy.data.objects.new(name, object_data=None)
    dimension_object.empty_display_type = DEFAULT_EMPTY_DISPLAY_TYPE
    dimension_object.empty_display_size = get_preferences(context).empty_display_size
    dimension_object.hide_render = True

    collection.objects.link(dimension_object)

    if hasattr(dimension_object, "dimension_props"):
        from .transform_policy import enforce_annotation_transform_policy

        enforce_annotation_transform_policy(dimension_object)
        # Scene synchronization distinguishes a freshly created locator from a
        # legacy object whose pre-schema location may be a meaningful offset.
        # Operators place new locators on their canonical geometry before the
        # first sync; an untouched new locator should be moved there rather
        # than interpreting the origin as a user-authored displacement.
        dimension_object["_dimensions_new_locator"] = True
        dimension_object.dimension_props.enabled = True
        settings = getattr(context.scene, "dimensions_settings", None)
        if settings is not None:
            apply_scene_style_to_dimension(settings, dimension_object.dimension_props)
            clear_dimension_style_overrides(dimension_object.dimension_props)
        from .migrations import mark_object_current, stamp_scene_if_needed

        mark_object_current(dimension_object)
        stamp_scene_if_needed(context.scene)

    return dimension_object


def get_or_create_guide_collection(context):
    return _get_or_create_scene_collection(
        context,
        GUIDE_COLLECTION_NAME,
        "GUIDES",
    )


def create_guide_object(context, name="GUIDE Construction Line"):
    from .migrations import prepare_scene_for_write

    prepare_scene_for_write(context.scene)
    collection = get_or_create_guide_collection(context)
    guide_object = bpy.data.objects.new(name, object_data=None)
    guide_object.empty_display_type = DEFAULT_EMPTY_DISPLAY_TYPE
    guide_object.empty_display_size = get_preferences(context).empty_display_size
    guide_object.hide_render = True
    collection.objects.link(guide_object)
    guide_object.guide_props.enabled = True
    from .migrations import mark_object_current, stamp_scene_if_needed

    mark_object_current(guide_object)
    stamp_scene_if_needed(context.scene)
    return guide_object


def create_measurement_object(context, name="MEASURE Construction Segment"):
    measurement_object = create_guide_object(context, name)
    measurement_object.guide_props.kind = "MEASUREMENT"
    return measurement_object


def create_guide_point_object(context, name="POINT Construction Point", location=None):
    point_object = create_guide_object(context, name)
    point_object.guide_props.kind = "POINT"
    if location is not None:
        # Setting the world matrix updates it immediately, before depsgraph evaluation,
        # so the snap proxy built next starts at the right place.
        point_object.matrix_world = Matrix.Translation(location)
    return point_object


def create_guide_plane_object(context, frame, extent=None, spacing=None, name="PLANE Construction Grid"):
    """Create a construction grid mesh on ``frame``.

    The grid is a real mesh so Blender's own snapping, selection, and transform
    tools work on it. It is construction data in the Construction Guides
    collection, never rendered and never part of the user's model.
    """
    from .migrations import prepare_scene_for_write, stamp_scene_if_needed

    prepare_scene_for_write(context.scene)
    collection = get_or_create_guide_collection(context)
    plane_object = build_guide_plane_object(collection, frame, extent, spacing, name)
    stamp_scene_if_needed(context.scene)
    return plane_object


def build_guide_plane_object(collection, frame, extent=None, spacing=None, name="PLANE Construction Grid"):
    """Create a construction grid object in ``collection`` without needing a context."""
    from .construction import GUIDE_PLANE_FLAG, fill_grid_mesh, frame_matrix, nice_grid_spacing

    extent = 2.0 if extent is None else max(float(extent), 0.01)
    spacing = nice_grid_spacing(extent) if spacing is None else max(float(spacing), 0.001)
    mesh = bpy.data.meshes.new(name)
    fill_grid_mesh(mesh, extent, spacing)
    plane_object = bpy.data.objects.new(name, mesh)
    plane_object[GUIDE_PLANE_FLAG] = True
    plane_object.display_type = "WIRE"
    plane_object.hide_render = True
    plane_object.visible_shadow = False
    plane_object.matrix_world = frame_matrix(frame)
    collection.objects.link(plane_object)
    props = plane_object.guide_props
    # Size first: the kind is not PLANE yet, so these updates do not rebuild the grid again.
    props.plane_extent = extent
    props.plane_spacing = spacing
    props.enabled = True
    props.kind = "PLANE"
    from .migrations import mark_object_current

    mark_object_current(plane_object)
    return plane_object


def ensure_guide_point_snap_proxy(point_object, scene=None):
    """Expose a guide point to Blender's native vertex snapper."""
    if (
        point_object is None
        or not hasattr(point_object, "guide_props")
        or not point_object.guide_props.enabled
        or getattr(point_object.guide_props, "kind", "GUIDE") != "POINT"
    ):
        return None
    point_world = point_object.matrix_world.translation.copy()
    flagged = [child for child in point_object.children if child.get(GUIDE_POINT_SNAP_PROXY_FLAG, False)]
    proxy = next((child for child in flagged if child.type == "MESH"), None)
    for duplicate in flagged:
        if duplicate == proxy:
            continue
        duplicate_mesh = duplicate.data if duplicate.type == "MESH" else None
        bpy.data.objects.remove(duplicate, do_unlink=True)
        if duplicate_mesh is not None and duplicate_mesh.users == 0:
            bpy.data.meshes.remove(duplicate_mesh)
    if proxy is None:
        mesh = bpy.data.meshes.new(f"{point_object.name} Snap Target")
        proxy = bpy.data.objects.new(f"{point_object.name} Snap Target", mesh)
        for collection in point_object.users_collection:
            collection.objects.link(proxy)
        proxy.parent = point_object
        proxy.matrix_parent_inverse = point_object.matrix_world.inverted_safe()
        proxy[GUIDE_POINT_SNAP_PROXY_FLAG] = True
        proxy.hide_render = True
        proxy.hide_select = True
        proxy.display_type = "WIRE"
        proxy.show_in_front = True
    elif proxy.data.users > 1:
        proxy.data = proxy.data.copy()
    proxy.matrix_world = point_object.matrix_world.copy()
    local_point = proxy.matrix_world.inverted_safe() @ point_world
    if len(proxy.data.vertices) != 1 or (proxy.data.vertices[0].co - local_point).length > 1e-6:
        proxy.data.clear_geometry()
        proxy.data.from_pydata([local_point], [], [])
        proxy.data.update()
    if scene is None:
        scene = getattr(getattr(bpy, "context", None), "scene", None)
    settings = getattr(scene, "dimensions_settings", None)
    globally_visible = settings is None or settings.show_construction_guides
    try:
        point_hidden = point_object.hide_get()
    except (AttributeError, RuntimeError):
        point_hidden = False
    should_hide = (
        not point_object.guide_props.visible or not globally_visible
        or point_object.hide_viewport or point_hidden
    )
    try:
        proxy.hide_set(should_hide)
    except (AttributeError, RuntimeError):
        proxy.hide_viewport = should_hide
    return proxy


def ensure_measurement_snap_proxy(measurement_object, scene=None):
    """Expose fixed measurement endpoints to Blender's native vertex snapper."""
    if (
        measurement_object is None
        or not hasattr(measurement_object, "guide_props")
        or not measurement_object.guide_props.enabled
        or getattr(measurement_object.guide_props, "kind", "GUIDE") != "MEASUREMENT"
    ):
        return None

    start_world = resolve_anchor(measurement_object.guide_props.start)
    end_world = resolve_anchor(measurement_object.guide_props.end)
    if start_world is None or end_world is None or (end_world - start_world).length < 1e-6:
        return None

    flagged_children = [
        child
        for child in measurement_object.children
        if child.get(MEASUREMENT_SNAP_PROXY_FLAG, False)
    ]
    proxy = next((child for child in flagged_children if child.type == "MESH"), None)
    for duplicate in flagged_children:
        if duplicate == proxy:
            continue
        duplicate_mesh = duplicate.data if duplicate.type == "MESH" else None
        bpy.data.objects.remove(duplicate, do_unlink=True)
        if duplicate_mesh is not None and duplicate_mesh.users == 0:
            bpy.data.meshes.remove(duplicate_mesh)
    if proxy is None:
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
    elif proxy.data.users > 1:
        proxy.data = proxy.data.copy()

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


def detach_annotations_from(sources):
    """Fix anchors bound to ``sources`` at their current position before the sources are deleted.

    Dimensions follow the guides and grids they were snapped to; deleting a guide
    through Dimensions keeps those dimensions where they are instead of breaking them.
    """
    pointers = {source.as_pointer() for source in sources}
    detached = 0
    for obj in bpy.data.objects:
        if not is_dimension_object(obj) or is_read_only_dimensions_object(obj):
            continue
        props = obj.dimension_props
        for anchor in (
            props.start, props.end, props.center,
            props.angle_a_start, props.angle_a_end, props.angle_b_start, props.angle_b_end,
        ):
            target = anchor.target_object
            if target is not None and target.as_pointer() in pointers:
                set_world_anchor(anchor, resolve_anchor(anchor))
                detached += 1
    return detached


def remove_guide_point_snap_proxies(point_object):
    for child in list(getattr(point_object, "children", ())):
        if not child.get(GUIDE_POINT_SNAP_PROXY_FLAG, False):
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
            and obj.type == "MESH"
            and hasattr(parent, "guide_props")
            and parent.guide_props.enabled
            and getattr(parent.guide_props, "kind", "GUIDE") == "MEASUREMENT"
        ):
            continue
        mesh = obj.data if obj.type == "MESH" else None
        bpy.data.objects.remove(obj, do_unlink=True)
        if mesh is not None and mesh.users == 0:
            bpy.data.meshes.remove(mesh)


def remove_orphan_guide_point_snap_proxies(scene):
    for obj in list(scene.objects):
        if not obj.get(GUIDE_POINT_SNAP_PROXY_FLAG, False):
            continue
        parent = obj.parent
        if (
            parent is not None and obj.type == "MESH"
            and hasattr(parent, "guide_props") and parent.guide_props.enabled
            and getattr(parent.guide_props, "kind", "GUIDE") == "POINT"
        ):
            continue
        mesh = obj.data if obj.type == "MESH" else None
        bpy.data.objects.remove(obj, do_unlink=True)
        if mesh is not None and mesh.users == 0:
            bpy.data.meshes.remove(mesh)
