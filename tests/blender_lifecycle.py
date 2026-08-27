"""Named lifecycle checks for persistent Dimensions data."""

import sys
import tempfile
import unittest
from pathlib import Path

import bpy
from mathutils import Vector


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

import dimensions
from dimensions.anchors import set_world_anchor
from dimensions.constants import CURRENT_SCHEMA_VERSION
from dimensions.migrations import migrate_scene, scene_has_dimensions_data
from dimensions.collections import (
    MEASUREMENT_SNAP_PROXY_FLAG,
    create_dimension_object,
    create_measurement_object,
    ensure_measurement_snap_proxy,
    remove_measurement_snap_proxies,
)
from dimensions.operators.generate_output import annotation_output_key
from dimensions.projected_snap import get_projected_snap_timings
from dimensions.scene_sync import sync_scene_objects
from dimensions.viewport_state import get_state, set_state


class DimensionsLifecycleTests(unittest.TestCase):
    def setUp(self):
        dimensions.register()
        self.measurement = create_measurement_object(
            bpy.context,
            f"Dimensions Lifecycle Measurement {self._testMethodName}",
        )
        self.measurement_name = self.measurement.name
        set_world_anchor(self.measurement.guide_props.start, Vector((1.0, 2.0, 3.0)))
        set_world_anchor(self.measurement.guide_props.end, Vector((5.0, 2.0, 3.0)))

    def tearDown(self):
        measurement = bpy.data.objects.get(self.measurement_name)
        if measurement is not None:
            bpy.data.objects.remove(measurement, do_unlink=True)

    @classmethod
    def tearDownClass(cls):
        dimensions.unregister()

    def test_measurement_proxy_contains_both_endpoints(self):
        proxy = ensure_measurement_snap_proxy(self.measurement, bpy.context.scene)
        self.assertIsNotNone(proxy)
        self.assertEqual(len(proxy.data.vertices), 2)
        points = [proxy.matrix_world @ vertex.co for vertex in proxy.data.vertices]
        self.assertEqual(points, [Vector((1.0, 2.0, 3.0)), Vector((5.0, 2.0, 3.0))])

    def test_proxy_cleanup_removes_duplicate_children(self):
        invalid_proxy = bpy.data.objects.new("Invalid Dimensions Proxy", None)
        bpy.context.scene.collection.objects.link(invalid_proxy)
        invalid_proxy.parent = self.measurement
        invalid_proxy[MEASUREMENT_SNAP_PROXY_FLAG] = True
        ensure_measurement_snap_proxy(self.measurement, bpy.context.scene)
        proxies = [
            child for child in self.measurement.children
            if child.get(MEASUREMENT_SNAP_PROXY_FLAG, False)
        ]
        self.assertEqual(len(proxies), 1)

    def test_proxy_visibility_follows_measurement_visibility(self):
        self.measurement.guide_props.visible = False
        proxy = ensure_measurement_snap_proxy(self.measurement, bpy.context.scene)
        self.assertTrue(proxy.hide_get() or proxy.hide_viewport)

    def test_sync_repairs_missing_measurement_proxy(self):
        remove_measurement_snap_proxies(self.measurement)
        sync_scene_objects(bpy.context.scene)
        self.assertTrue(any(
            child.get(MEASUREMENT_SNAP_PROXY_FLAG, False)
            for child in self.measurement.children
        ))

    def test_undo_redo_lifecycle_clears_transient_viewport_state(self):
        set_state("DIMENSION", {"test": "undo"})
        from dimensions.scene_sync import _undo_redo_handler

        _undo_redo_handler(bpy.context.scene)
        self.assertIsNone(get_state("DIMENSION"))
        self.assertEqual(get_projected_snap_timings(), {})

    def test_save_reload_preserves_measurement_and_proxy(self):
        ensure_measurement_snap_proxy(self.measurement, bpy.context.scene)
        with tempfile.TemporaryDirectory() as directory:
            filepath = Path(directory) / "dimensions-lifecycle.blend"
            bpy.ops.wm.save_as_mainfile(filepath=str(filepath), check_existing=False)
            bpy.ops.wm.open_mainfile(filepath=str(filepath), load_ui=False)
            measurement = bpy.data.objects.get(self.measurement_name)
            self.assertIsNotNone(measurement)
            sync_scene_objects(bpy.context.scene)
            self.assertTrue(any(
                child.get(MEASUREMENT_SNAP_PROXY_FLAG, False)
                for child in measurement.children
            ))

    def test_save_reload_preserves_scene_owned_output_identity(self):
        dimension = create_dimension_object(
            bpy.context,
            "Dimensions Lifecycle Output Identity",
        )
        dimension_name = dimension.name
        set_world_anchor(dimension.dimension_props.start, Vector((0.0, 0.0, 0.0)))
        set_world_anchor(dimension.dimension_props.end, Vector((2.0, 0.0, 0.0)))
        source_key = annotation_output_key(bpy.context.scene, dimension)
        self.assertIsNone(dimension.get("dimensions_annotation_output_key"))

        with tempfile.TemporaryDirectory() as directory:
            filepath = Path(directory) / "dimensions-output-identity.blend"
            bpy.ops.wm.save_as_mainfile(filepath=str(filepath), check_existing=False)
            bpy.ops.wm.open_mainfile(filepath=str(filepath), load_ui=False)
            reloaded = bpy.data.objects.get(dimension_name)
            self.assertIsNotNone(reloaded)
            self.assertEqual(
                annotation_output_key(bpy.context.scene, reloaded),
                source_key,
            )
            bpy.data.objects.remove(reloaded, do_unlink=True)


class DimensionsReleasedFileTests(unittest.TestCase):
    """Migration against a real file saved by an earlier release.

    ``tests/fixtures/schema-v0.blend`` was written before schema stamping existed: its
    vertex anchors carry no durable point IDs and its scene carries no stamp. The
    0.3.2 fixture represents schema v1 before output settings were introduced.
    Every schema change adds a fixture here so migrations keep being tested against
    files that actually shipped, not only against synthetic data.
    """

    FIXTURE = REPOSITORY_ROOT / "tests" / "fixtures" / "schema-v0.blend"
    OUTPUT_FIXTURE = REPOSITORY_ROOT / "tests" / "fixtures" / "schema-v1-0.3.2.blend"

    def setUp(self):
        dimensions.register()

    def test_the_fixture_is_present(self):
        self.assertTrue(self.FIXTURE.is_file(), f"missing fixture: {self.FIXTURE}")
        self.assertTrue(self.OUTPUT_FIXTURE.is_file(), f"missing fixture: {self.OUTPUT_FIXTURE}")

    def test_an_unstamped_released_file_migrates_to_the_current_schema(self):
        bpy.ops.wm.open_mainfile(filepath=str(self.FIXTURE), load_ui=False)
        scene = bpy.context.scene
        self.assertTrue(scene_has_dimensions_data(scene))

        # load_post runs on open; opening an unstamped file must land it at current.
        self.assertEqual(scene.dimensions_settings.schema_version, CURRENT_SCHEMA_VERSION)

        dimension = bpy.data.objects.get("DIM Legacy")
        self.assertIsNotNone(dimension)
        self.assertGreater(dimension.dimension_props.start.vertex_id, 0)
        self.assertGreater(dimension.dimension_props.end.vertex_id, 0)

    def test_migrating_a_released_file_twice_changes_nothing(self):
        bpy.ops.wm.open_mainfile(filepath=str(self.FIXTURE), load_ui=False)
        scene = bpy.context.scene
        dimension = bpy.data.objects.get("DIM Legacy")
        identifiers = (
            dimension.dimension_props.start.vertex_id,
            dimension.dimension_props.end.vertex_id,
        )

        self.assertFalse(migrate_scene(scene))
        self.assertEqual(scene.dimensions_settings.schema_version, CURRENT_SCHEMA_VERSION)
        self.assertEqual(
            (
                dimension.dimension_props.start.vertex_id,
                dimension.dimension_props.end.vertex_id,
            ),
            identifiers,
        )

    def test_the_0_3_2_fixture_migrates_output_settings(self):
        bpy.ops.wm.open_mainfile(filepath=str(self.OUTPUT_FIXTURE), load_ui=False)
        scene = bpy.context.scene
        self.assertTrue(scene_has_dimensions_data(scene))
        self.assertEqual(scene.dimensions_settings.schema_version, CURRENT_SCHEMA_VERSION)
        self.assertEqual(scene.dimensions_settings.output_sizing_mode, "CAMERA")
        self.assertEqual(scene.dimensions_settings.output_scope, "VISIBLE")
        self.assertAlmostEqual(scene.dimensions_settings.output_line_width, 2.0)
        self.assertAlmostEqual(scene.dimensions_settings.output_text_height, 14.0)
        self.assertEqual(len(scene.dimensions_settings.output_source_bindings), 0)


def main():
    loader = unittest.defaultTestLoader
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.TestSuite(
            loader.loadTestsFromTestCase(case)
            for case in (DimensionsLifecycleTests, DimensionsReleasedFileTests)
        )
    )
    if not result.wasSuccessful():
        raise SystemExit(1)
    print("Dimensions lifecycle checks passed")


if __name__ == "__main__":
    main()
