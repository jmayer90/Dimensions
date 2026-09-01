"""Scene data synchronization and dependency-graph cache invalidation."""

import bpy
from bpy.app.handlers import persistent
from math import cos, sin
from mathutils import Vector

from .anchors import refresh_anchor_resolution, refresh_dimension_anchor_resolutions, resolve_anchor
from .area_binding import area_label_world, evaluate_area_binding
from .angle_binding import resolve_angle_source
from .collections import (
    ensure_guide_point_snap_proxy,
    ensure_measurement_snap_proxy,
    remove_orphan_guide_point_snap_proxies,
    remove_orphan_measurement_snap_proxies,
)
from .dimension_geometry import get_angle_world_geometry, get_dimension_world_geometry
from .dimension_sets import (
    dimension_set_state,
    dimension_set_world_geometry,
    refresh_dimension_set_state,
)
from .circle_binding import circle_geometry, store_circle_fit
from .projected_snap import clear_projected_snap_cache, invalidate_projected_snap_cache_from_depsgraph
from .properties import is_dimension_object, is_guide_object
from .volume import clear_volume_cache, invalidate_volume_cache_from_depsgraph
from .viewport_state import clear_all_states
from .transform_policy import annotation_world_location, enforce_annotation_transform_policy


_sync_active = False
_sync_scheduled = False
_selection_sync_owner = object()


def register_scene_sync():
    if _depsgraph_sync_handler not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_depsgraph_sync_handler)
    for handlers in (bpy.app.handlers.undo_post, bpy.app.handlers.redo_post):
        if _undo_redo_handler not in handlers:
            handlers.append(_undo_redo_handler)
    _subscribe_selection_sync()
    schedule_scene_sync()


def unregister_scene_sync():
    global _sync_scheduled
    if _depsgraph_sync_handler in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_depsgraph_sync_handler)
    for handlers in (bpy.app.handlers.undo_post, bpy.app.handlers.redo_post):
        if _undo_redo_handler in handlers:
            handlers.remove(_undo_redo_handler)
    if bpy.app.timers.is_registered(_run_scheduled_sync):
        bpy.app.timers.unregister(_run_scheduled_sync)
    bpy.msgbus.clear_by_owner(_selection_sync_owner)
    _sync_scheduled = False
    clear_volume_cache()
    invalidate_projected_snap_cache_from_depsgraph(None)
    clear_all_states()


def schedule_scene_sync():
    global _sync_scheduled
    if _sync_scheduled:
        return
    _sync_scheduled = True
    bpy.app.timers.register(_run_scheduled_sync, first_interval=0.0)


def _subscribe_selection_sync():
    """Schedule manager-index synchronization when a viewport active object changes."""
    bpy.msgbus.clear_by_owner(_selection_sync_owner)
    try:
        bpy.msgbus.subscribe_rna(
            key=(bpy.types.LayerObjects, "active"),
            owner=_selection_sync_owner,
            args=(),
            notify=schedule_scene_sync,
            options={"PERSISTENT"},
        )
    except (AttributeError, TypeError, ValueError):
        # Background and restricted registration contexts can omit LayerObjects.
        pass


def _run_scheduled_sync():
    global _sync_scheduled
    _sync_scheduled = False
    for scene in bpy.data.scenes:
        sync_scene_objects(scene)
    return None


@persistent
def _depsgraph_sync_handler(scene, depsgraph):
    invalidate_volume_cache_from_depsgraph(depsgraph)
    invalidate_projected_snap_cache_from_depsgraph(depsgraph)
    if depsgraph is None or any(True for _update in depsgraph.updates):
        from .drawing import invalidate_dimension_geometry_cache

        invalidate_dimension_geometry_cache()
    sync_scene_objects(scene)


@persistent
def _undo_redo_handler(_dummy=None):
    clear_projected_snap_cache()
    clear_volume_cache()
    clear_all_states()
    from .drawing import invalidate_dimension_geometry_cache

    invalidate_dimension_geometry_cache()
    for scene in bpy.data.scenes:
        sync_scene_objects(scene)


def sync_scene_objects(scene):
    global _sync_active
    if _sync_active or scene is None:
        return
    _sync_active = True
    try:
        from .migrations import stamp_scene_if_needed

        stamp_scene_if_needed(scene)
        remove_orphan_measurement_snap_proxies(scene)
        remove_orphan_guide_point_snap_proxies(scene)
        for obj in list(scene.objects):
            if not _is_editable(obj):
                continue
            if is_guide_object(obj):
                _sync_guide(obj, scene)
            elif is_dimension_object(obj):
                _sync_dimension(obj)
        from .annotation_manager import sync_annotation_manager

        sync_annotation_manager(scene)
        _sync_annotation_manager_selection(scene)
    finally:
        _sync_active = False


def _is_editable(obj):
    from .properties import is_read_only_dimensions_object

    return not is_read_only_dimensions_object(obj)


def _sync_guide(obj, scene):
    if getattr(obj.guide_props, "kind", "GUIDE") == "PLANE":
        from .guide_planes import guide_plane_resolution, store_guide_plane_resolution

        for anchor in (
            obj.guide_props.plane_point_a,
            obj.guide_props.plane_point_b,
            obj.guide_props.plane_point_c,
            obj.guide_props.source_a.start,
            obj.guide_props.source_a.end,
        ):
            refresh_anchor_resolution(anchor)
        frame, state = guide_plane_resolution(obj)
        store_guide_plane_resolution(obj.guide_props, frame, state)
        _set_translation(obj, None if state != "LIVE" or frame is None else frame[0])
        return
    for anchor in (
        obj.guide_props.start,
        obj.guide_props.end,
        obj.guide_props.construction_pivot,
        obj.guide_props.spacing_end,
        obj.guide_props.source_a.start,
        obj.guide_props.source_a.end,
        obj.guide_props.source_b.start,
        obj.guide_props.source_b.end,
    ):
        refresh_anchor_resolution(anchor)
    if getattr(obj.guide_props, "derived", False):
        from .derived_guides import derived_guide_resolution, store_derived_guide_resolution

        line, state = derived_guide_resolution(obj)
        store_derived_guide_resolution(obj.guide_props, line, state)
        start_world = None if state != "LIVE" or line is None else line[0]
    else:
        start_world = resolve_anchor(obj.guide_props.start)
    target_world = start_world
    if getattr(obj.guide_props, "kind", "GUIDE") == "MEASUREMENT":
        end_world = resolve_anchor(obj.guide_props.end)
        if start_world is not None and end_world is not None:
            target_world = (start_world + end_world) * 0.5
    _set_translation(obj, target_world)
    if getattr(obj.guide_props, "kind", "GUIDE") == "MEASUREMENT":
        ensure_measurement_snap_proxy(obj, scene)
    elif getattr(obj.guide_props, "kind", "GUIDE") == "POINT":
        ensure_guide_point_snap_proxy(obj, scene)


def _sync_dimension(obj):
    enforce_annotation_transform_policy(obj)
    props = obj.dimension_props
    annotation_kind = getattr(props, "annotation_kind", "LINEAR")
    if annotation_kind in {"COORDINATE", "ELEVATION"}:
        from .coordinate_dimensions import coordinate_values, elevation_value

        result = coordinate_values(props) if annotation_kind == "COORDINATE" else elevation_value(props)
        if result is None:
            _set_measurement_state(props, "NEEDS_REPAIR")
            return
        _set_measurement_state(props, result["state"])
        _sync_annotation_placement(obj, props, result["point"])
        return
    if annotation_kind == "DIMENSION_SET":
        refresh_dimension_set_state(props)
        geometry = dimension_set_world_geometry(props)
        _set_measurement_state(props, dimension_set_state(props))
        if geometry:
            center = sum((item["line_mid_world"] for item in geometry), Vector()) / len(geometry)
            _sync_annotation_placement(obj, props, center)
        return
    if annotation_kind == "CIRCLE":
        fit = circle_geometry(props)
        if fit is None:
            _set_measurement_state(props, "NEEDS_REPAIR")
            return
        store_circle_fit(props, fit)
        direction = fit["axis_u"] * cos(props.circle_leader_angle) + fit["axis_v"] * sin(props.circle_leader_angle)
        distance = props.circle_label_distance if props.circle_label_distance > 1e-6 else fit["radius"] * 1.35
        _sync_annotation_placement(obj, props, fit["center"] + direction * distance)
        return
    anchor_state = refresh_dimension_anchor_resolutions(props)
    start_world = resolve_anchor(props.start)
    end_world = resolve_anchor(props.end)
    if start_world is None or end_world is None:
        return
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
                    _set_measurement_state(props, result.get("state", "LIVE"))
                    props.area_value = result["area"]
                    props.area_face_count = result["face_count"]
                    _set_area_source_anchor(props, result["center"])
                    start_world = result["center"]
                    end_world = area_label_world(props, result["center"], end_world)
        _sync_annotation_placement(obj, props, end_world)
        return
    if annotation_kind == "ANGLE":
        source = resolve_angle_source(props)
        center_world = None if source is None else source["center"]
        angle_geometry = None if source is None else get_angle_world_geometry(
            source["start"],
            center_world,
            source["end"],
            props.angle_radius,
            source["arc_mode"],
        )
        _set_measurement_state(props, "NEEDS_REPAIR" if angle_geometry is None else anchor_state)
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
        _set_measurement_state(props, anchor_state)
        _sync_annotation_placement(obj, props, geometry["line_mid_world"])


def _set_translation(obj, target_world):
    current_world = annotation_world_location(obj)
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
        current_world = annotation_world_location(obj)
        user_delta = current_world - expected
        if user_delta.length > 1e-6:
            offset += user_delta
            props.presentation_offset = tuple(offset)
    else:
        # New and legacy objects already sit on their canonical placement.
        # Preserve a meaningful existing displacement when one is present.
        current_world = annotation_world_location(obj)
        existing_delta = current_world - canonical_world
        is_new_locator = bool(obj.get("_dimensions_new_locator", False))
        if not is_new_locator and existing_delta.length > 1e-5:
            offset += existing_delta
            props.presentation_offset = tuple(offset)
        if is_new_locator:
            del obj["_dimensions_new_locator"]
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


def _sync_annotation_manager_selection(scene):
    """Mirror the current viewport selection outside UI draw callbacks."""
    try:
        context = bpy.context
        if context.scene != scene:
            return
        active = context.view_layer.objects.active
        if active is None:
            return
        from .annotation_manager import set_active_index_from_viewport

        set_active_index_from_viewport(scene.dimensions_settings, active)
    except (AttributeError, RuntimeError):
        pass
