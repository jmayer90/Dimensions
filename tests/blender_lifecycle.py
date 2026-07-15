"""Foreground-independent persistence checks that require file reload."""

import sys
import traceback
from pathlib import Path

import bpy
from mathutils import Vector


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

import dimensions
from dimensions.anchors import set_world_anchor
from dimensions.collections import (
    MEASUREMENT_SNAP_PROXY_FLAG,
    create_measurement_object,
    ensure_measurement_snap_proxy,
    remove_measurement_snap_proxies,
)
from dimensions.scene_sync import sync_scene_objects


MEASUREMENT_NAME = "Dimensions Lifecycle Measurement"


def main():
    dimensions.register()
    filepath = Path(bpy.app.tempdir) / "dimensions-lifecycle.blend"
    try:
        measurement = create_measurement_object(bpy.context, MEASUREMENT_NAME)
        set_world_anchor(measurement.guide_props.start, Vector((1.0, 2.0, 3.0)))
        set_world_anchor(measurement.guide_props.end, Vector((5.0, 2.0, 3.0)))
        proxy = ensure_measurement_snap_proxy(measurement, bpy.context.scene)
        assert proxy is not None and len(proxy.data.vertices) == 2

        invalid_proxy = bpy.data.objects.new("Invalid Dimensions Proxy", None)
        bpy.context.scene.collection.objects.link(invalid_proxy)
        invalid_proxy.parent = measurement
        invalid_proxy[MEASUREMENT_SNAP_PROXY_FLAG] = True
        ensure_measurement_snap_proxy(measurement, bpy.context.scene)
        assert len([
            child for child in measurement.children
            if child.get(MEASUREMENT_SNAP_PROXY_FLAG, False)
        ]) == 1

        measurement.guide_props.visible = False
        proxy = ensure_measurement_snap_proxy(measurement, bpy.context.scene)
        assert proxy.hide_get() or proxy.hide_viewport
        measurement.guide_props.visible = True

        remove_measurement_snap_proxies(measurement)
        sync_scene_objects(bpy.context.scene)
        assert any(child.get(MEASUREMENT_SNAP_PROXY_FLAG, False) for child in measurement.children)

        if bpy.ops.ed.undo.poll():
            bpy.ops.ed.undo_push(message="Dimensions lifecycle before clear")
            bpy.ops.dimensions.clear_measurements()
            assert bpy.data.objects.get(MEASUREMENT_NAME) is None
            bpy.ops.ed.undo()
            measurement = bpy.data.objects.get(MEASUREMENT_NAME)
            assert measurement is not None
            sync_scene_objects(bpy.context.scene)
            assert any(child.get(MEASUREMENT_SNAP_PROXY_FLAG, False) for child in measurement.children)
        else:
            print("Undo lifecycle check skipped: unavailable in background context")

        bpy.ops.wm.save_as_mainfile(filepath=str(filepath), check_existing=False)
        bpy.ops.wm.open_mainfile(filepath=str(filepath), load_ui=False)

        measurement = bpy.data.objects.get(MEASUREMENT_NAME)
        assert measurement is not None
        sync_scene_objects(bpy.context.scene)
        proxy = next(
            child for child in measurement.children
            if child.get(MEASUREMENT_SNAP_PROXY_FLAG, False)
        )
        points = [proxy.matrix_world @ vertex.co for vertex in proxy.data.vertices]
        assert points == [Vector((1.0, 2.0, 3.0)), Vector((5.0, 2.0, 3.0))]
        print("Dimensions lifecycle checks passed")
    finally:
        dimensions.unregister()
        if filepath.exists():
            filepath.unlink()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
