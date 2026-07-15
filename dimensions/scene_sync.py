"""Scene data synchronization and dependency-graph cache invalidation."""

import bpy
from bpy.app.handlers import persistent
from mathutils import Vector

from .anchors import migrate_anchor_identity, resolve_anchor
from .area_binding import area_label_world, evaluate_area_binding
from .angle_binding import resolve_angle_source
from .collections import ensure_measurement_snap_proxy, remove_orphan_measurement_snap_proxies
from .dimension_geometry import get_angle_world_geometry, get_dimension_world_geometry
from .projected_snap import invalidate_projected_snap_cache_from_depsgraph
from .properties import is_dimension_object, is_guide_object
from .volume import clear_volume_cache, invalidate_volume_cache_from_depsgraph


_sync_active = False
_sync_scheduled = False


def register_scene_sync():
    if _depsgraph_sync_handler not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_depsgraph_sync_handler)
    schedule_scene_sync()


def unregister_scene_sync():
    global _sync_scheduled
    if _depsgraph_sync_handler in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_depsgraph_sync_handler)
    if bpy.app.timers.is_registered(_run_scheduled_sync):
        bpy.app.timers.unregister(_run_scheduled_sync)
    _sync_scheduled = False
    clear_volume_cache()
    invalidate_projected_snap_cache_from_depsgraph(None)


def schedule_scene_sync():
    global _sync_scheduled
    if _sync_scheduled:
        return
    _sync_scheduled = True
    bpy.app.timers.register(_run_scheduled_sync, first_interval=0.0)


def _run_scheduled_sync():
    global _sync_scheduled
    _sync_scheduled = False
    scene = getattr(bpy.context, "scene", None)
    if scene is not None:
        sync_scene_objects(scene)
    return None


@persistent
def _depsgraph_sync_handler(scene, depsgraph):
    invalidate_volume_cache_from_depsgraph(depsgraph)
    invalidate_projected_snap_cache_from_depsgraph(depsgraph)
    sync_scene_objects(scene)


def sync_scene_objects(scene):
    global _sync_active
    if _sync_active or scene is None:
        return
    _sync_active = True
    try:
        remove_orphan_measurement_snap_proxies(scene)
        for obj in list(scene.objects):
            if is_guide_object(obj):
                _sync_guide(obj, scene)
            elif is_dimension_object(obj):
                _sync_dimension(obj)
    finally:
        _sync_active = False


def _sync_guide(obj, scene):
    migrate_anchor_identity(obj.guide_props.start)
    migrate_anchor_identity(obj.guide_props.end)
    start_world = resolve_anchor(obj.guide_props.start)
    target_world = start_world
    if getattr(obj.guide_props, "kind", "GUIDE") == "MEASUREMENT":
        end_world = resolve_anchor(obj.guide_props.end)
        if start_world is not None and end_world is not None:
            target_world = (start_world + end_world) * 0.5
    _set_translation(obj, target_world)
    if getattr(obj.guide_props, "kind", "GUIDE") == "MEASUREMENT":
        ensure_measurement_snap_proxy(obj, scene)


def _sync_dimension(obj):
    props = obj.dimension_props
    migrate_anchor_identity(props.start)
    migrate_anchor_identity(props.end)
    start_world = resolve_anchor(props.start)
    end_world = resolve_anchor(props.end)
    if start_world is None or end_world is None:
        return
    annotation_kind = getattr(props, "annotation_kind", "LINEAR")
    if annotation_kind == "AREA":
        if props.measurement_state != "CAPTURED":
            if len(props.area_faces) == 0:
                # Pre-live-binding files contain only a stored area value.
                _set_measurement_state(props, "CAPTURED")
            else:
                result = evaluate_area_binding(props)
                if result is None:
                    _set_measurement_state(props, "NEEDS_REPAIR")
                else:
                    _set_measurement_state(props, "LIVE")
                    props.area_value = result["area"]
                    props.area_face_count = result["face_count"]
                    _set_area_source_anchor(props, result["center"])
                    start_world = result["center"]
                    end_world = area_label_world(props, result["center"], end_world)
        _sync_annotation_placement(obj, props, end_world)
        return
    if annotation_kind == "ANGLE":
        if props.angle_source_mode == "EDGES":
            for anchor in (
                props.angle_a_start,
                props.angle_a_end,
                props.angle_b_start,
                props.angle_b_end,
            ):
                migrate_anchor_identity(anchor)
        else:
            migrate_anchor_identity(props.center)
        source = resolve_angle_source(props)
        center_world = None if source is None else source["center"]
        angle_geometry = None if source is None else get_angle_world_geometry(
            source["start"],
            center_world,
            source["end"],
            props.angle_radius,
            source["arc_mode"],
        )
        _set_measurement_state(props, "LIVE" if angle_geometry is not None else "NEEDS_REPAIR")
        _sync_annotation_placement(obj, props, center_world)
        return
    geometry = get_dimension_world_geometry(
        props.dimension_type,
        start_world,
        end_world,
        Vector(props.offset_plane_normal),
        props.offset_distance,
        props.offset_angle,
        props.measurement_mode,
    )
    if geometry is not None:
        _sync_annotation_placement(obj, props, geometry["line_mid_world"])


def _set_translation(obj, target_world):
    current_world = Vector(obj.location) if obj.parent is None else obj.matrix_world.translation
    if target_world is None or (current_world - target_world).length <= 1e-6:
        return
    if obj.parent is None:
        obj.location = target_world
        return
    matrix_world = obj.matrix_world.copy()
    matrix_world.translation = target_world
    obj.matrix_world = matrix_world


def _sync_annotation_placement(obj, props, canonical_world):
    if canonical_world is None:
        return
    canonical_world = Vector(canonical_world)
    offset = Vector(props.presentation_offset)
    if props.placement_initialized:
        previous_canonical = Vector(props.canonical_location)
        expected = previous_canonical + offset
        current_world = Vector(obj.location) if obj.parent is None else obj.matrix_world.translation
        user_delta = current_world - expected
        if user_delta.length > 1e-6:
            offset += user_delta
            props.presentation_offset = tuple(offset)
    else:
        # New and legacy objects already sit on their canonical placement.
        # Preserve a meaningful existing displacement when one is present.
        current_world = Vector(obj.location) if obj.parent is None else obj.matrix_world.translation
        existing_delta = current_world - canonical_world
        if existing_delta.length > 1e-5:
            offset += existing_delta
            props.presentation_offset = tuple(offset)
        props.placement_initialized = True
    props.canonical_location = tuple(canonical_world)
    _set_translation(obj, canonical_world + offset)


def _set_area_source_anchor(props, center_world):
    source = props.area_source_object
    if source is None:
        return
    anchor = props.start
    local = source.matrix_world.inverted_safe() @ center_world
    anchor.anchor_type = "OBJECT_POINT"
    if anchor.target_object != source:
        anchor.target_object = source
    anchor.vertex_index = -1
    anchor.vertex_id = 0
    if (Vector(anchor.fallback_local_co) - local).length > 1e-7:
        anchor.fallback_local_co = tuple(local)
    anchor.world_co = tuple(center_world)


def _set_measurement_state(props, state):
    if props.measurement_state != state:
        props.measurement_state = state
