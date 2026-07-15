"""Cached, depth-aware Object Mode projected-vertex acquisition."""

from collections import defaultdict
from math import floor

from bpy_extras import view3d_utils
from mathutils import Vector


_CELL_SIZE = 48.0
_MAX_DEPTH_CHECKS = 32
_viewport_caches = {}


def clear_projected_snap_cache():
    _viewport_caches.clear()


def invalidate_projected_snap_cache_from_depsgraph(depsgraph):
    if depsgraph is None or any(True for _update in depsgraph.updates):
        clear_projected_snap_cache()


def nearest_visible_projected_vertex(context, mouse_x, mouse_y, pixel_threshold, excluded_flag=None):
    cache = _get_cache(context, excluded_flag)
    if cache is None:
        return None
    mouse = Vector((mouse_x, mouse_y))
    radius = float(pixel_threshold)
    min_x = floor((mouse.x - radius) / _CELL_SIZE)
    max_x = floor((mouse.x + radius) / _CELL_SIZE)
    min_y = floor((mouse.y - radius) / _CELL_SIZE)
    max_y = floor((mouse.y + radius) / _CELL_SIZE)
    candidates = []
    for cell_x in range(min_x, max_x + 1):
        for cell_y in range(min_y, max_y + 1):
            for candidate in cache["grid"].get((cell_x, cell_y), ()):
                distance = (candidate["screen_co"] - mouse).length
                if distance < radius:
                    candidates.append((distance, candidate))
    candidates.sort(key=lambda item: item[0])
    for _distance, candidate in candidates[:_MAX_DEPTH_CHECKS]:
        if _is_visible(context, candidate):
            return dict(candidate)
    return None


def _get_cache(context, excluded_flag):
    region = getattr(context, "region", None)
    region_data = getattr(context, "region_data", None)
    if region is None or region_data is None:
        return None
    if not hasattr(region, "width") or not hasattr(region_data, "perspective_matrix"):
        return {"view_signature": None, "grid": {}}
    window = getattr(context, "window", None)
    area = getattr(context, "area", None)
    key = (
        0 if window is None else window.as_pointer(),
        0 if area is None else area.as_pointer(),
        region.as_pointer() if hasattr(region, "as_pointer") else id(region),
    )
    view_signature = (
        region.width,
        region.height,
        tuple(round(value, 7) for row in region_data.perspective_matrix for value in row),
    )
    cache = _viewport_caches.get(key)
    if cache is not None and cache["view_signature"] == view_signature:
        return cache

    grid = defaultdict(list)
    for obj in getattr(context, "visible_objects", ()):
        if obj.type != "MESH" or (excluded_flag and obj.get(excluded_flag, False)):
            continue
        for vertex in obj.data.vertices:
            world_co = obj.matrix_world @ vertex.co
            screen_co = view3d_utils.location_3d_to_region_2d(region, region_data, world_co)
            if screen_co is None:
                continue
            candidate = {
                "type": "VERTEX",
                "label": "Vertex",
                "priority": 0,
                "object": obj,
                "vertex_index": vertex.index,
                "world_co": world_co.copy(),
                "screen_co": screen_co.copy(),
            }
            cell = (floor(screen_co.x / _CELL_SIZE), floor(screen_co.y / _CELL_SIZE))
            grid[cell].append(candidate)
    cache = {"view_signature": view_signature, "grid": grid}
    _viewport_caches[key] = cache
    return cache


def _is_visible(context, candidate):
    coord = candidate["screen_co"]
    origin = view3d_utils.region_2d_to_origin_3d(context.region, context.region_data, coord)
    direction = view3d_utils.region_2d_to_vector_3d(context.region, context.region_data, coord).normalized()
    candidate_depth = (candidate["world_co"] - origin).dot(direction)
    if candidate_depth <= 0.0:
        return False
    hit, location, _normal, _face_index, _obj, _matrix = context.scene.ray_cast(
        context.evaluated_depsgraph_get(),
        origin,
        direction,
        distance=candidate_depth + max(1e-4, candidate_depth * 1e-4),
    )
    if not hit:
        return True
    hit_depth = (location - origin).dot(direction)
    tolerance = max(1e-4, candidate_depth * 1e-4)
    return candidate_depth <= hit_depth + tolerance
