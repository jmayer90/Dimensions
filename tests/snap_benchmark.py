"""Repeatable dense-scene projected-snap benchmark.

Run with ``DIMENSIONS_SNAP_PROFILE=1 blender --background --factory-startup --python
tests/snap_benchmark.py``.

The scene generator is deterministic, so runs are comparable across machines. The
benchmark measures the three costs the snap cache is built around: the initial source
build, a reprojection after a pure view change (which must not rebuild sources), and a
steady-state query.
"""

import os
import sys
import time
from pathlib import Path

import bpy
from mathutils import Matrix


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from dimensions.constants import DEFAULT_SNAP_PIXEL_THRESHOLD
from dimensions.projected_snap import (
    clear_projected_snap_cache,
    get_projected_snap_timings,
    nearest_visible_projected_vertex,
)

from support import make_context


def make_reference_scene(vertex_count=100_000, objects=1):
    """Create deterministic points distributed over a regular grid."""
    collection = bpy.data.collections.new("Dimensions Snap Benchmark")
    bpy.context.scene.collection.children.link(collection)
    per_object = max(1, vertex_count // objects)
    for object_index in range(objects):
        mesh = bpy.data.meshes.new(f"Snap Benchmark {object_index}")
        vertices = [
            ((index % 1000) * 0.01, (index // 1000) * 0.01, object_index * 0.01)
            for index in range(per_object)
        ]
        mesh.from_pydata(vertices, [], [])
        obj = bpy.data.objects.new(f"Snap Benchmark {object_index}", mesh)
        collection.objects.link(obj)
    return collection


def clear_scene():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for mesh in list(bpy.data.meshes):
        bpy.data.meshes.remove(mesh)
    for collection in list(bpy.data.collections):
        bpy.data.collections.remove(collection)
    clear_projected_snap_cache()


def run_case(label, vertex_count, objects, query_count=50):
    clear_scene()
    make_reference_scene(vertex_count, objects)
    bpy.context.view_layer.update()

    context = make_context(scene=bpy.context.scene)
    context.view_layer = bpy.context.view_layer
    context.visible_objects = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    context.evaluated_depsgraph_get = bpy.context.evaluated_depsgraph_get

    get_projected_snap_timings(reset=True)

    build_started = time.perf_counter()
    nearest_visible_projected_vertex(context, 100.0, 100.0, DEFAULT_SNAP_PIXEL_THRESHOLD)
    build_ms = (time.perf_counter() - build_started) * 1000.0

    # A pure view change must reproject without rescanning any mesh data.
    context.region_data.perspective_matrix = Matrix.Translation((0.0, 0.0, 1.0))
    reproject_started = time.perf_counter()
    nearest_visible_projected_vertex(context, 100.0, 100.0, DEFAULT_SNAP_PIXEL_THRESHOLD)
    reproject_ms = (time.perf_counter() - reproject_started) * 1000.0

    query_started = time.perf_counter()
    for index in range(query_count):
        nearest_visible_projected_vertex(
            context,
            100.0 + (index % 10),
            100.0 + (index % 7),
            DEFAULT_SNAP_PIXEL_THRESHOLD,
        )
    query_ms = ((time.perf_counter() - query_started) / query_count) * 1000.0

    print(
        f"{label:<38} vertices={vertex_count:<9} objects={objects:<4} "
        f"build={build_ms:9.3f} ms  reproject={reproject_ms:8.3f} ms  query={query_ms:7.3f} ms"
    )
    return build_ms, reproject_ms, query_ms


def main():
    print("Dimensions projected-snap benchmark")
    print(f"Blender {bpy.app.version_string}\n")
    if os.environ.get("DIMENSIONS_SNAP_PROFILE", "").lower() not in {"1", "true", "yes"}:
        print("note: set DIMENSIONS_SNAP_PROFILE=1 for the add-on's own per-stage timings\n")
    run_case("sparse (10k vertices)", 10_000, 1)
    run_case("dense single object (100k vertices)", 100_000, 1)
    run_case("dense many objects (100k vertices)", 100_000, 50)
    run_case("very dense (1M vertices)", 1_000_000, 10)


if __name__ == "__main__":
    main()
