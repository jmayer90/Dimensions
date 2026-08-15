"""Cached, depth-aware Object Mode projected-vertex acquisition."""

from collections import defaultdict
from math import floor
import os
from time import perf_counter

from bpy_extras import view3d_utils
from mathutils import Vector


_CELL_SIZE = 48.0
_MAX_DEPTH_CHECKS = 32
_viewport_caches = {}
_timings = defaultdict(lambda: {"count": 0, "seconds": 0.0})


def _profiling_enabled():
    return os.environ.get("DIMENSIONS_SNAP_PROFILE", "").lower() in {"1", "true", "yes"}


def _record_timing(operation, started):
    """Record opt-in timing without adding cost to normal interactive snapping."""
    if not _profiling_enabled():
        return
    elapsed = perf_counter() - started
    record = _timings[operation]
    record["count"] += 1
    record["seconds"] += elapsed
    print(f"Dimensions snap {operation}: {elapsed * 1000.0:.3f} ms")


def get_projected_snap_timings(reset=False):
    """Return opt-in projected snap timings for benchmark scripts and support reports."""
    result = {
        operation: {
            "count": record["count"],
            "seconds": record["seconds"],
            "average_ms": 0.0 if not record["count"] else record["seconds"] * 1000.0 / record["count"],
        }
        for operation, record in _timings.items()
    }
    if reset:
        _timings.clear()
    return result


def clear_projected_snap_cache():
    _viewport_caches.clear()


def invalidate_projected_snap_cache_from_depsgraph(depsgraph):
    if depsgraph is None or any(True for _update in depsgraph.updates):
        clear_projected_snap_cache()


def nearest_visible_projected_vertex(context, mouse_x, mouse_y, pixel_threshold, excluded_flag=None):
    started = perf_counter() if _profiling_enabled() else None
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
        visible_started = perf_counter() if _profiling_enabled() else None
        if _is_visible(context, candidate):
            if visible_started is not None:
                _record_timing("occlusion", visible_started)
            if started is not None:
                _record_timing("query", started)
            return dict(candidate)
        if visible_started is not None:
            _record_timing("occlusion", visible_started)
    if started is not None:
        _record_timing("query", started)
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

    source_signature = _source_signature(context, excluded_flag)
    if cache is None or cache["source_signature"] != source_signature:
        started = perf_counter() if _profiling_enabled() else None
        sources = _build_sources(context, excluded_flag)
        if started is not None:
            _record_timing("build", started)
    else:
        # A pure view movement only reprojects already-built world-space sources.
        # It never rescans mesh data or recreates the source cache.
        sources = cache["sources"]
    started = perf_counter() if _profiling_enabled() else None
    grid = _project_sources(region, region_data, sources)
    if started is not None:
        _record_timing("reproject", started)
    cache = {
        "view_signature": view_signature,
        "source_signature": source_signature,
        "sources": sources,
        "grid": grid,
    }
    _viewport_caches[key] = cache
    return cache


def _source_signature(context, excluded_flag):
    """Identify geometry inputs without tying cache validity to the current camera view."""
    signature = []
    for obj in getattr(context, "visible_objects", ()):
        if obj.type != "MESH" or (excluded_flag and obj.get(excluded_flag, False)):
            continue
        signature.append((obj.as_pointer(), obj.data.as_pointer(), tuple(obj.matrix_world)))
    return tuple(signature)


def _build_sources(context, excluded_flag):
    sources = []
    for obj in getattr(context, "visible_objects", ()):
        if obj.type != "MESH" or (excluded_flag and obj.get(excluded_flag, False)):
            continue
        sources.extend(
            {
                "type": "VERTEX",
                "label": "Vertex",
                "priority": 0,
                "object": obj,
                "vertex_index": vertex.index,
                "world_co": (obj.matrix_world @ vertex.co).copy(),
            }
            for vertex in obj.data.vertices
        )
    return sources


def _project_sources(region, region_data, sources):
    grid = defaultdict(list)
    for source in sources:
        screen_co = view3d_utils.location_3d_to_region_2d(region, region_data, source["world_co"])
        if screen_co is None:
            continue
        candidate = dict(source)
        candidate["screen_co"] = screen_co.copy()
        cell = (floor(screen_co.x / _CELL_SIZE), floor(screen_co.y / _CELL_SIZE))
        grid[cell].append(candidate)
    return grid


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
