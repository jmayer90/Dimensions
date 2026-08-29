"""Repeatable 200-line repeated-spacing draw and snap benchmark.

Run with ``blender --background --factory-startup --python
tests/guide_spacing_benchmark.py``. The draw measurement covers the production CPU
path that resolves and batches a spaced set before GPU upload. The snap measurement
uses the public guide query and performs all 200 line intersections and projections.
"""

import os
import sys
import time
from pathlib import Path
from unittest.mock import patch

import bpy
from mathutils import Vector


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import dimensions
from dimensions.anchors import set_world_anchor
from dimensions.collections import create_guide_object
from dimensions.derived_guides import bind_guide_source, spaced_guide_lines
from dimensions.drawing import _spaced_guide_draw_segments
from dimensions.snapping import find_nearest_guide_point

from support import make_context


GENERATED_LINE_COUNT = 200
DRAW_BUDGET_MS = 1000.0 / 30.0
SNAP_BUDGET_MS = 8.0


def clear_scene():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for collection in list(bpy.data.collections):
        bpy.data.collections.remove(collection)


def make_spacing_scene(context):
    source = create_guide_object(context, "GUIDE Spacing Benchmark Source")
    set_world_anchor(source.guide_props.start, Vector((0.0, 0.0, 0.0)))
    set_world_anchor(source.guide_props.end, Vector((1.0, 0.0, 0.0)))

    spaced = create_guide_object(context, "GUIDE Spacing Benchmark Set")
    props = spaced.guide_props
    props.derived = True
    props.derivation_mode = "SPACING"
    props.spacing_mode = "COUNT"
    props.spacing_interval = 0.4
    props.spacing_count = GENERATED_LINE_COUNT
    props.derived_direction = (0.0, 1.0, 0.0)
    bind_guide_source(props.source_a, source)
    set_world_anchor(props.construction_pivot, Vector((0.0, 0.0, 0.0)))
    return spaced


def average_milliseconds(callback, iterations):
    callback()
    started = time.perf_counter()
    for _index in range(iterations):
        callback()
    return (time.perf_counter() - started) * 1000.0 / iterations


def main():
    dimensions.register()
    try:
        clear_scene()
        context = make_context(scene=bpy.context.scene)
        context.view_layer = bpy.context.view_layer
        spaced = make_spacing_scene(context)
        lines = spaced_guide_lines(spaced)
        if len(lines) != GENERATED_LINE_COUNT:
            raise AssertionError(f"expected {GENERATED_LINE_COUNT} lines, got {len(lines)}")
        draw_lines, segments = _spaced_guide_draw_segments(spaced)
        if len(draw_lines) != GENERATED_LINE_COUNT or len(segments) != GENERATED_LINE_COUNT * 2:
            raise AssertionError("draw preparation did not preserve every generated line")

        iterations = int(os.environ.get("DIMENSIONS_GUIDE_BENCHMARK_ITERATIONS", "500"))
        draw_ms = average_milliseconds(
            lambda: _spaced_guide_draw_segments(spaced), iterations,
        )

        def query():
            return find_nearest_guide_point(
                context, 0.0, 0.0, enabled_targets=frozenset(("guide",)),
            )

        with (
            patch("dimensions.snapping.has_view3d_window_region", return_value=True),
            patch(
                "dimensions.snapping.get_mouse_ray",
                return_value=(Vector((0.0, 0.0, 5.0)), Vector((0.0, 0.0, -1.0))),
            ),
            patch(
                "dimensions.snapping.view3d_utils.location_3d_to_region_2d",
                side_effect=lambda _region, _data, point: Vector((point.x, point.y)),
            ),
        ):
            snap_ms = average_milliseconds(query, iterations)
            if query() is None:
                raise AssertionError("200-line spacing set produced no snap candidate")

        print("Dimensions repeated-spacing benchmark")
        print(f"Blender {bpy.app.version_string}, {iterations} iterations")
        print(
            f"{GENERATED_LINE_COUNT} generated lines  "
            f"draw preparation={draw_ms:.3f} ms  guide snap query={snap_ms:.3f} ms"
        )
        if draw_ms >= DRAW_BUDGET_MS:
            raise AssertionError(
                f"draw preparation {draw_ms:.3f} ms exceeds {DRAW_BUDGET_MS:.3f} ms budget"
            )
        if snap_ms >= SNAP_BUDGET_MS:
            raise AssertionError(
                f"guide snap query {snap_ms:.3f} ms exceeds {SNAP_BUDGET_MS:.3f} ms budget"
            )
    finally:
        clear_scene()
        dimensions.unregister()


if __name__ == "__main__":
    main()
