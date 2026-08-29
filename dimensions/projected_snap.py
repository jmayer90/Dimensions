"""Cached, depth-aware Object Mode projected-vertex acquisition."""

from collections import defaultdict
from math import floor, hypot
import os
from time import perf_counter

import numpy as np
from bpy_extras import view3d_utils
from mathutils import Vector


_CELL_SIZE = 48.0
_MAX_DEPTH_CHECKS = 32
_INDEX_MARGIN = 128.0
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


def _object_has_excluded_flag(obj, excluded_flag):
    if not excluded_flag:
        return False
    flags = (excluded_flag,) if isinstance(excluded_flag, str) else excluded_flag
    return any(obj.get(flag, False) for flag in flags)


def nearest_visible_projected_vertex(context, mouse_x, mouse_y, pixel_threshold, excluded_flag=None):
    started = perf_counter() if _profiling_enabled() else None
    cache = _get_cache(context, excluded_flag)
    if cache is None:
        return None
    mouse = Vector((mouse_x, mouse_y))
    radius = float(pixel_threshold)
    grid = cache["grid"]
    indexed_bounds = grid.get("indexed_bounds")
    if indexed_bounds is not None and not (
        mouse.x - radius >= indexed_bounds[0]
        and mouse.x + radius <= indexed_bounds[1]
        and mouse.y - radius >= indexed_bounds[2]
        and mouse.y + radius <= indexed_bounds[3]
    ):
        grid = _full_spatial_grid(grid)
    min_x = floor((mouse.x - radius) / _CELL_SIZE)
    max_x = floor((mouse.x + radius) / _CELL_SIZE)
    min_y = floor((mouse.y - radius) / _CELL_SIZE)
    max_y = floor((mouse.y + radius) / _CELL_SIZE)
    candidate_indices = []
    for cell_x in range(min_x, max_x + 1):
        for cell_y in range(min_y, max_y + 1):
            for source_index in _cell_source_indices(grid, cell_x, cell_y):
                screen_co = grid["screen_coordinates"][source_index]
                distance = hypot(float(screen_co[0]) - mouse.x, float(screen_co[1]) - mouse.y)
                if distance < radius:
                    candidate_indices.append((distance, int(source_index)))
    candidate_indices.sort(key=lambda item: item[0])
    for _distance, source_index in candidate_indices[:_MAX_DEPTH_CHECKS]:
        candidate = _materialize_candidate(cache["sources"], grid, source_index)
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
        return {
            "view_signature": None,
            "grid": {
                "cell_ranges": {},
                "source_indices": np.empty(0, dtype=np.int64),
                "screen_coordinates": np.empty((0, 2), dtype=np.float32),
            },
        }
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
    previous_grid = (
        cache["grid"]
        if cache is not None and cache["source_signature"] == source_signature
        else None
    )
    grid = _project_sources(region, region_data, sources, previous_grid=previous_grid)
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
        if obj.type != "MESH" or _object_has_excluded_flag(obj, excluded_flag):
            continue
        signature.append((obj.as_pointer(), obj.data.as_pointer(), tuple(obj.matrix_world)))
    return tuple(signature)


def _build_sources(context, excluded_flag):
    objects = tuple(
        obj
        for obj in getattr(context, "visible_objects", ())
        if obj.type == "MESH" and not _object_has_excluded_flag(obj, excluded_flag)
    )
    object_starts = np.empty(len(objects) + 1, dtype=np.int64)
    object_starts[0] = 0
    for object_index, obj in enumerate(objects):
        object_starts[object_index + 1] = object_starts[object_index] + len(obj.data.vertices)

    world_coordinates = np.empty((int(object_starts[-1]), 3), dtype=np.float32)
    for object_index, obj in enumerate(objects):
        start = int(object_starts[object_index])
        end = int(object_starts[object_index + 1])
        if start == end:
            continue
        coordinates = world_coordinates[start:end]
        obj.data.vertices.foreach_get("co", coordinates.reshape(-1))
        matrix = np.asarray(tuple(tuple(row) for row in obj.matrix_world), dtype=np.float32)
        if not np.array_equal(matrix, np.eye(4, dtype=np.float32)):
            coordinates[:] = coordinates @ matrix[:3, :3].T
            coordinates += matrix[:3, 3]
    return {
        "objects": objects,
        "object_starts": object_starts,
        "world_coordinates": world_coordinates,
    }


def _project_sources(region, region_data, sources, previous_grid=None):
    world_coordinates = sources["world_coordinates"]
    projection = np.asarray(tuple(tuple(row) for row in region_data.perspective_matrix), dtype=np.float32)
    projection_signature = (
        region.width,
        region.height,
        projection[[0, 1, 3], :].tobytes(),
    )
    if previous_grid is not None and previous_grid.get("projection_signature") == projection_signature:
        return previous_grid

    if not np.any(projection[3, :3]):
        clip_w = projection[3, 3]
        all_visible = clip_w > 0.0
        if all_visible:
            axis_aligned_xy = np.array(((1.0, 0.0, 0.0), (0.0, 1.0, 0.0)), dtype=np.float32)
            if np.array_equal(projection[:2, :3], axis_aligned_xy):
                screen_coordinates = world_coordinates[:, :2].copy()
            else:
                screen_coordinates = world_coordinates @ projection[:2, :3].T
            screen_coordinates += projection[:2, 3]
            screen_coordinates /= clip_w
            visible_indices = None
        else:
            screen_coordinates = np.full((len(world_coordinates), 2), np.nan, dtype=np.float32)
            visible_indices = np.empty(0, dtype=np.int64)
    else:
        clip_coordinates = world_coordinates @ projection[[0, 1, 3], :3].T
        clip_coordinates += projection[[0, 1, 3], 3]
        visible_mask = clip_coordinates[:, 2] > 0.0
        all_visible = visible_mask.all()
        screen_coordinates = clip_coordinates[:, :2]
        if all_visible:
            np.divide(clip_coordinates[:, 0], clip_coordinates[:, 2], out=screen_coordinates[:, 0])
            np.divide(clip_coordinates[:, 1], clip_coordinates[:, 2], out=screen_coordinates[:, 1])
            visible_indices = None
        else:
            visible_indices = np.flatnonzero(visible_mask)
            np.divide(
                clip_coordinates[:, 0],
                clip_coordinates[:, 2],
                out=screen_coordinates[:, 0],
                where=visible_mask,
            )
            np.divide(
                clip_coordinates[:, 1],
                clip_coordinates[:, 2],
                out=screen_coordinates[:, 1],
                where=visible_mask,
            )
            screen_coordinates[~visible_mask] = np.nan
    if all_visible or len(visible_indices):
        if all_visible:
            screen_coordinates[:, 0] += 1.0
            screen_coordinates[:, 1] += 1.0
            screen_coordinates[:, 0] *= region.width * 0.5
            screen_coordinates[:, 1] *= region.height * 0.5
            projected_coordinates = screen_coordinates
        else:
            screen_coordinates[visible_indices, 0] += 1.0
            screen_coordinates[visible_indices, 1] += 1.0
            screen_coordinates[visible_indices, 0] *= region.width * 0.5
            screen_coordinates[visible_indices, 1] *= region.height * 0.5
            projected_coordinates = screen_coordinates[visible_indices]
        indexed_bounds = (
            -_INDEX_MARGIN,
            region.width + _INDEX_MARGIN,
            -_INDEX_MARGIN,
            region.height + _INDEX_MARGIN,
        )
        indexed_mask = (
            (projected_coordinates[:, 0] >= indexed_bounds[0])
            & (projected_coordinates[:, 0] <= indexed_bounds[1])
            & (projected_coordinates[:, 1] >= indexed_bounds[2])
            & (projected_coordinates[:, 1] <= indexed_bounds[3])
        )
        indexed_positions = np.flatnonzero(indexed_mask)
        projected_coordinates = projected_coordinates[indexed_positions]
        indexed_source_indices = (
            indexed_positions if all_visible else visible_indices[indexed_positions]
        )
        if not len(indexed_source_indices):
            return {
                "cell_ranges": {},
                "source_indices": range(len(world_coordinates)) if all_visible else visible_indices,
                "cell_source_indices": np.empty(0, dtype=np.int64),
                "screen_coordinates": screen_coordinates,
                "cell_keys": np.empty(0, dtype=np.uint64),
                "cell_encoding": None,
                "visible_indices": visible_indices,
                "indexed_source_indices": indexed_source_indices,
                "indexed_bounds": indexed_bounds,
                "projection_signature": projection_signature,
            }
        cells = np.floor(projected_coordinates / _CELL_SIZE).astype(np.int32)
        cell_x = cells[:, 0]
        cell_y = cells[:, 1]
        minimum_x = int(cell_x.min())
        minimum_y = int(cell_y.min())
        cell_width = int(cell_x.max()) - minimum_x + 1
        cell_height = int(cell_y.max()) - minimum_y + 1
        dense_cell_count = cell_width * cell_height
        if dense_cell_count <= np.iinfo(np.int32).max:
            cell_keys = (
                (cell_y - minimum_y) * cell_width + (cell_x - minimum_x)
            ).astype(np.int32, copy=False)
            cell_encoding = (minimum_x, minimum_y, cell_width)
        else:
            cell_keys = _packed_cell_keys(cell_x, cell_y)
            cell_encoding = None
        previous_indexed_sources = None if previous_grid is None else previous_grid.get("indexed_source_indices")
        same_visible_sources = (
            previous_indexed_sources is not None
            and np.array_equal(indexed_source_indices, previous_indexed_sources)
        )
        if (
            same_visible_sources
            and previous_grid is not None
            and cell_encoding == previous_grid.get("cell_encoding")
            and np.array_equal(cell_keys, previous_grid.get("cell_keys"))
        ):
            sorted_source_indices = previous_grid.get(
                "cell_source_indices", previous_grid["source_indices"]
            )
            cell_ranges = previous_grid["cell_ranges"]
        else:
            order = np.argsort(cell_keys, kind="mergesort")
            sorted_keys = cell_keys[order]
            sorted_source_indices = indexed_source_indices[order]
            starts = np.r_[0, np.flatnonzero(sorted_keys[1:] != sorted_keys[:-1]) + 1]
            ends = np.r_[starts[1:], len(sorted_keys)]
            if cell_encoding is not None:
                unique_dense_keys = sorted_keys[starts]
                unique_x = unique_dense_keys % cell_width + minimum_x
                unique_y = unique_dense_keys // cell_width + minimum_y
                unique_cell_keys = _packed_cell_keys(unique_x, unique_y)
            else:
                unique_cell_keys = sorted_keys[starts]
            cell_ranges = {
                int(key): (int(start), int(end))
                for key, start, end in zip(unique_cell_keys, starts, ends)
            }
    else:
        sorted_source_indices = np.empty(0, dtype=np.int64)
        cell_ranges = {}
        cell_keys = np.empty(0, dtype=np.uint64)
        cell_encoding = None
        visible_indices = np.empty(0, dtype=np.int64)
        indexed_source_indices = visible_indices
        indexed_bounds = (
            -_INDEX_MARGIN,
            region.width + _INDEX_MARGIN,
            -_INDEX_MARGIN,
            region.height + _INDEX_MARGIN,
        )
    return {
        "cell_ranges": cell_ranges,
        "source_indices": range(len(world_coordinates)) if all_visible else visible_indices,
        "cell_source_indices": sorted_source_indices,
        "screen_coordinates": screen_coordinates,
        "cell_keys": cell_keys,
        "cell_encoding": cell_encoding,
        "visible_indices": visible_indices,
        "indexed_source_indices": indexed_source_indices,
        "indexed_bounds": indexed_bounds,
        "projection_signature": projection_signature,
    }


def _full_spatial_grid(grid):
    cached = grid.get("full_grid")
    if cached is not None:
        return cached
    screen_coordinates = grid["screen_coordinates"]
    finite_mask = np.isfinite(screen_coordinates).all(axis=1)
    source_indices = np.flatnonzero(finite_mask)
    if not len(source_indices):
        cached = {
            "cell_ranges": {},
            "source_indices": source_indices,
            "cell_source_indices": source_indices,
            "screen_coordinates": screen_coordinates,
        }
        grid["full_grid"] = cached
        return cached
    projected = screen_coordinates[source_indices]
    cells = np.floor(projected / _CELL_SIZE).astype(np.int32)
    cell_keys = _packed_cell_keys(cells[:, 0], cells[:, 1])
    order = np.argsort(cell_keys, kind="mergesort")
    sorted_keys = cell_keys[order]
    sorted_source_indices = source_indices[order]
    starts = np.r_[0, np.flatnonzero(sorted_keys[1:] != sorted_keys[:-1]) + 1]
    ends = np.r_[starts[1:], len(sorted_keys)]
    cell_ranges = {
        int(sorted_keys[start]): (int(start), int(end))
        for start, end in zip(starts, ends)
    }
    cached = {
        "cell_ranges": cell_ranges,
        "source_indices": sorted_source_indices,
        "cell_source_indices": sorted_source_indices,
        "screen_coordinates": screen_coordinates,
    }
    grid["full_grid"] = cached
    return cached


def _packed_cell_keys(cell_x, cell_y):
    x = np.asarray(cell_x, dtype=np.int32).view(np.uint32)
    y = np.asarray(cell_y, dtype=np.int32).view(np.uint32).astype(np.uint64)
    return (y << np.uint64(32)) | x


def _cell_source_indices(grid, cell_x, cell_y):
    key = ((int(cell_y) & 0xFFFFFFFF) << 32) | (int(cell_x) & 0xFFFFFFFF)
    start, end = grid["cell_ranges"].get(key, (0, 0))
    source_indices = grid.get("cell_source_indices", grid["source_indices"])
    return source_indices[start:end]


def _materialize_candidate(sources, grid, source_index):
    object_index = int(np.searchsorted(sources["object_starts"], source_index, side="right") - 1)
    vertex_index = source_index - int(sources["object_starts"][object_index])
    return {
        "type": "VERTEX",
        "label": "Vertex",
        "priority": 0,
        "object": sources["objects"][object_index],
        "vertex_index": vertex_index,
        "world_co": Vector(sources["world_coordinates"][source_index]),
        "screen_co": Vector(grid["screen_coordinates"][source_index]),
    }


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
