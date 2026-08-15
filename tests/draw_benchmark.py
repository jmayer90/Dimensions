"""Repeatable annotation-overlay draw benchmark.

Run with ``blender --background --factory-startup --python tests/draw_benchmark.py``.

Blender cannot present GPU batches in background mode, so this measures the per-frame
CPU work the overlay does before it uploads anything: locating annotations, resolving
anchors, projecting to screen space, and laying out labels. That is the cost FND-03 is
about — it is what used to scale with scene size — and it bounds the frame rate the
overlay can sustain.

Scenes are generated deterministically so runs are comparable across machines.
"""

import os
import sys
import time
from pathlib import Path

import bpy
from mathutils import Vector


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import dimensions
from dimensions import drawing
from dimensions.anchors import set_world_anchor
from dimensions.collections import create_dimension_object, get_scene_collection
from dimensions.properties import is_dimension_object

from support import make_context


def make_reference_scene(distractor_count, dimension_count, context):
    """Build a deterministic scene of plain meshes plus linear dimensions."""
    mesh = bpy.data.meshes.new("Benchmark Cube")
    mesh.from_pydata(
        [
            (0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0),
            (0.0, 0.0, 1.0), (1.0, 0.0, 1.0), (1.0, 1.0, 1.0), (0.0, 1.0, 1.0),
        ],
        [],
        [(0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4), (2, 3, 7, 6), (0, 3, 7, 4), (1, 2, 6, 5)],
    )
    for index in range(distractor_count):
        obj = bpy.data.objects.new(f"Benchmark Cube {index}", mesh)
        obj.location = ((index % 100) * 2.0, (index // 100) * 2.0, 0.0)
        bpy.context.scene.collection.objects.link(obj)

    for index in range(dimension_count):
        dimension = create_dimension_object(context, f"DIM Benchmark {index}")
        row = index // 25
        column = index % 25
        set_world_anchor(dimension.dimension_props.start, Vector((column * 2.0, row * 2.0, 0.0)))
        set_world_anchor(dimension.dimension_props.end, Vector((column * 2.0 + 1.5, row * 2.0, 0.0)))


def clear_scene():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for mesh in list(bpy.data.meshes):
        bpy.data.meshes.remove(mesh)
    for collection in list(bpy.data.collections):
        bpy.data.collections.remove(collection)
    drawing.invalidate_dimension_geometry_cache()


def time_frames(context, frame_count, invalidate_each_frame):
    """Return milliseconds per frame for the overlay's per-frame CPU work."""
    collection = get_scene_collection(bpy.context.scene, "DIMENSIONS")
    annotations = [obj for obj in collection.all_objects if is_dimension_object(obj)]

    # Warm up so the first frame's import and allocation cost is not counted.
    for obj in annotations:
        drawing.get_cached_dimension_geometry(context, obj)

    start = time.perf_counter()
    for _frame in range(frame_count):
        if invalidate_each_frame:
            drawing.invalidate_dimension_geometry_cache()
        for obj in annotations:
            drawing.get_cached_dimension_geometry(context, obj)
    elapsed = time.perf_counter() - start
    return (elapsed / frame_count) * 1000.0


def run_case(label, distractor_count, dimension_count, frame_count=200):
    clear_scene()
    context = make_context(scene=bpy.context.scene)
    context.view_layer = bpy.context.view_layer
    make_reference_scene(distractor_count, dimension_count, context)

    rebuilt = time_frames(context, frame_count, invalidate_each_frame=True)
    cached = time_frames(context, frame_count, invalidate_each_frame=False)
    scene_objects = len(bpy.context.scene.objects)
    print(
        f"{label:<34} objects={scene_objects:<7} dimensions={dimension_count:<5} "
        f"rebuild={rebuilt:7.3f} ms/frame  cached={cached:7.3f} ms/frame  "
        f"({_fps(rebuilt)} fps rebuilding, {_fps(cached)} fps cached)"
    )
    return rebuilt, cached


def _fps(milliseconds):
    if milliseconds <= 0.0:
        return ">9999"
    return f"{1000.0 / milliseconds:.0f}"


def main():
    dimensions.register()
    try:
        frame_count = int(os.environ.get("DIMENSIONS_DRAW_BENCHMARK_FRAMES", "200"))
        print("Dimensions overlay draw benchmark")
        print(f"Blender {bpy.app.version_string}, {frame_count} frames per case\n")
        run_case("10 cubes, 10 dimensions", 10, 10, frame_count)
        run_case("10,000 cubes, 10 dimensions", 10_000, 10, frame_count)
        run_case("500 dimensions (budget scene)", 10, 500, frame_count)
    finally:
        dimensions.unregister()


if __name__ == "__main__":
    main()
