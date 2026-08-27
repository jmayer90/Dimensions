"""Focused Blender smoke tests for the OUT-01 generation workflow."""

import sys
import unittest
from pathlib import Path
from time import perf_counter

import bpy
from mathutils import Vector


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

import dimensions
from dimensions.anchors import set_world_anchor
from dimensions.collections import create_dimension_object
from dimensions.grease_pencil_output import _remove_generated_object, generated_output_objects
from dimensions.operators.generate_output import (
    _camera_world_units_per_pixel,
    _annotation_world_depth_point,
    annotation_output_key,
    annotation_output_keys,
    output_sizing_for_annotation,
    output_text_height_for_annotation,
)


class DimensionsOutputOperatorSmokeTests(unittest.TestCase):
    def setUp(self):
        self.scene = bpy.context.scene
        self.created = []
        self.original_camera = self.scene.camera
        self.original_scope = self.scene.dimensions_settings.output_scope
        self.original_sizing = self.scene.dimensions_settings.output_sizing_mode

    def tearDown(self):
        for obj in self.created:
            if obj.name in bpy.data.objects:
                if obj.type == "GREASEPENCIL":
                    _remove_generated_object(obj)
                else:
                    object_type = obj.type
                    data = obj.data
                    bpy.data.objects.remove(obj, do_unlink=True)
                    if object_type == "CAMERA" and data is not None and data.users == 0:
                        bpy.data.cameras.remove(data)
        settings = self.scene.dimensions_settings
        settings.output_scope = self.original_scope
        settings.output_sizing_mode = self.original_sizing
        self.scene.camera = self.original_camera

    def _dimension(self, name, start=(0.0, 0.0, 0.0), end=(2.0, 0.0, 0.0)):
        dimension = create_dimension_object(bpy.context, name)
        set_world_anchor(dimension.dimension_props.start, Vector(start))
        set_world_anchor(dimension.dimension_props.end, Vector(end))
        dimension.location = _annotation_world_depth_point(dimension)
        self.created.append(dimension)
        return dimension

    def _remove_existing_output(self):
        for output in generated_output_objects(self.scene):
            _remove_generated_object(output)

    def test_scene_output_settings_expose_camera_world_and_scope(self):
        settings = self.scene.dimensions_settings
        self.assertEqual(settings.output_sizing_mode, "CAMERA")
        self.assertEqual(settings.output_scope, "VISIBLE")
        self.assertGreater(settings.output_line_width, 0.0)
        self.assertGreater(settings.output_text_height, 0.0)
        self.assertGreater(settings.output_arrow_size, 0.0)
        self.assertGreater(settings.output_world_line_width, 0.0)
        self.assertGreater(settings.output_world_text_height, 0.0)
        self.assertGreater(settings.output_world_arrow_size, 0.0)

    def test_world_sizing_uses_explicit_scene_units(self):
        settings = self.scene.dimensions_settings
        settings.output_sizing_mode = "WORLD"
        settings.output_world_line_width = 0.025
        settings.output_world_arrow_size = 0.20
        settings.output_world_text_height = 0.3
        dimension = self._dimension("DIM Output World Sizing")

        sizing = output_sizing_for_annotation(self.scene, dimension, settings)
        self.assertAlmostEqual(sizing.line_width, 0.025)
        self.assertAlmostEqual(sizing.arrow_size, 0.20)
        self.assertAlmostEqual(output_text_height_for_annotation(self.scene, dimension, settings), 0.3)

    def test_duplicated_annotations_receive_distinct_output_keys(self):
        first = self._dimension("DIM Output Key Source")
        first_key = annotation_output_key(self.scene, first)
        duplicate = first.copy()
        self.scene.collection.objects.link(duplicate)
        self.created.append(duplicate)

        self.assertEqual(annotation_output_key(self.scene, first), first_key)
        self.assertNotEqual(annotation_output_key(self.scene, duplicate), first_key)
        self.assertIsNone(first.get("dimensions_annotation_output_key"))
        self.assertIsNone(duplicate.get("dimensions_annotation_output_key"))

    def test_generating_only_a_duplicate_cannot_replace_the_original_output(self):
        self._remove_existing_output()
        settings = self.scene.dimensions_settings
        settings.output_sizing_mode = "WORLD"
        settings.output_scope = "SELECTED"
        original = self._dimension("DIM Output Original")
        original_key = annotation_output_key(self.scene, original)
        duplicate = original.copy()
        self.scene.collection.objects.link(duplicate)
        self.created.append(duplicate)
        original.select_set(False)
        duplicate.select_set(True)
        bpy.context.view_layer.objects.active = duplicate

        keys = annotation_output_keys(self.scene, (original, duplicate))
        self.assertEqual(keys[original.name], original_key)
        self.assertNotEqual(keys[duplicate.name], original_key)
        self.assertEqual(bpy.ops.dimensions.generate_output(), {"FINISHED"})
        outputs = generated_output_objects(self.scene)
        self.created.extend(outputs)
        self.assertEqual(len(outputs), 1)
        self.assertEqual(outputs[0].get("dimensions_output_source_key"), keys[duplicate.name])

    def test_renamed_duplicate_preserves_preexisting_source_output(self):
        self._remove_existing_output()
        settings = self.scene.dimensions_settings
        settings.output_sizing_mode = "WORLD"
        settings.output_scope = "SELECTED"
        original = self._dimension("DIM Output Original")
        original.select_set(True)
        bpy.context.view_layer.objects.active = original
        self.assertEqual(bpy.ops.dimensions.generate_output(), {"FINISHED"})
        original_key = annotation_output_key(self.scene, original)
        previous_output = generated_output_objects(self.scene, original_key)[0]

        duplicate = original.copy()
        duplicate.name = "AAA Output Duplicate"
        self.scene.collection.objects.link(duplicate)
        self.created.append(duplicate)
        original.select_set(True)
        duplicate.select_set(False)
        bpy.context.view_layer.objects.active = original

        self.assertEqual(bpy.ops.dimensions.generate_output(), {"FINISHED"})
        outputs = generated_output_objects(self.scene, original_key)
        self.created.extend(output for output in outputs if output not in self.created)
        self.assertEqual(len(outputs), 1)
        self.assertNotEqual(outputs[0], previous_output)
        self.assertEqual(annotation_output_key(self.scene, original), original_key)
        self.assertNotEqual(annotation_output_key(self.scene, duplicate), original_key)

    def test_camera_sizing_scales_with_annotation_depth(self):
        settings = self.scene.dimensions_settings
        settings.output_sizing_mode = "CAMERA"
        settings.output_line_width = 2.0
        settings.output_text_height = 14.0
        settings.output_arrow_size = 10.0
        camera_data = bpy.data.cameras.new("Dimensions Output Camera Test")
        camera = bpy.data.objects.new("Dimensions Output Camera Test", camera_data)
        self.scene.collection.objects.link(camera)
        self.created.append(camera)
        camera.location = (0.0, 0.0, 10.0)
        camera_data.lens = 50.0
        self.scene.camera = camera
        self.scene.render.resolution_y = 100
        self.scene.render.resolution_percentage = 100
        near = self._dimension("DIM Output Near", start=(-1.0, 0.0, 0.0), end=(1.0, 0.0, 0.0))
        far = self._dimension("DIM Output Far", start=(-1.0, 0.0, -10.0), end=(1.0, 0.0, -10.0))
        bpy.context.view_layer.update()

        self.assertAlmostEqual(_annotation_world_depth_point(near).z, 0.0)
        self.assertAlmostEqual(_annotation_world_depth_point(far).z, -10.0)

        near_policy = output_sizing_for_annotation(self.scene, near, settings)
        far_policy = output_sizing_for_annotation(self.scene, far, settings)
        self.assertIsNotNone(near_policy)
        self.assertIsNotNone(far_policy)
        self.assertGreater(far_policy.line_width, near_policy.line_width)
        self.assertGreater(
            output_text_height_for_annotation(self.scene, far, settings),
            output_text_height_for_annotation(self.scene, near, settings),
        )
        self.assertAlmostEqual(
            near_policy.line_width,
            settings.output_line_width * _camera_world_units_per_pixel(
                self.scene,
                camera,
                Vector((0.0, 0.0, 0.0)),
            ),
            places=6,
        )

    def test_operator_generates_only_visible_annotations_in_scope(self):
        self._remove_existing_output()
        settings = self.scene.dimensions_settings
        settings.output_sizing_mode = "WORLD"
        settings.output_scope = "VISIBLE"
        visible = self._dimension("DIM Output Visible")
        hidden = self._dimension("DIM Output Hidden", start=(0.0, 1.0, 0.0), end=(2.0, 1.0, 0.0))
        hidden.dimension_props.visible = False
        bpy.context.view_layer.objects.active = visible
        visible.select_set(True)

        self.assertEqual(bpy.ops.dimensions.generate_output(), {"FINISHED"})
        outputs = generated_output_objects(self.scene)
        self.assertEqual(len(outputs), 1)
        self.assertEqual(outputs[0].get("dimensions_output_source_key"), annotation_output_key(self.scene, visible))
        drawing = outputs[0].data.layers[0].frames[0].drawing
        self.assertGreater(len(drawing.strokes), 7)
        self.assertNotIn(annotation_output_key(self.scene, hidden), {output.get("dimensions_output_source_key") for output in outputs})
        self.created.extend(outputs)

    def test_operator_selected_scope_limits_output(self):
        self._remove_existing_output()
        settings = self.scene.dimensions_settings
        settings.output_sizing_mode = "WORLD"
        settings.output_scope = "SELECTED"
        selected = self._dimension("DIM Output Selected")
        unselected = self._dimension("DIM Output Unselected", start=(0.0, 1.0, 0.0), end=(2.0, 1.0, 0.0))
        selected.select_set(True)
        unselected.select_set(False)
        bpy.context.view_layer.objects.active = selected

        self.assertEqual(bpy.ops.dimensions.generate_output(), {"FINISHED"})
        outputs = generated_output_objects(self.scene)
        self.assertEqual(len(outputs), 1)
        self.assertEqual(outputs[0].get("dimensions_output_source_key"), annotation_output_key(self.scene, selected))
        self.created.extend(outputs)

    def test_generating_one_hundred_linear_annotations_stays_interactive(self):
        self._remove_existing_output()
        settings = self.scene.dimensions_settings
        settings.output_sizing_mode = "WORLD"
        settings.output_scope = "VISIBLE"
        for index in range(100):
            y = index * 0.05
            self._dimension(
                f"DIM Output Benchmark {index:03d}",
                start=(0.0, y, 0.0),
                end=(2.0, y, 0.0),
            )

        started = perf_counter()
        self.assertEqual(bpy.ops.dimensions.generate_output(), {"FINISHED"})
        elapsed = perf_counter() - started
        outputs = generated_output_objects(self.scene)
        self.created.extend(outputs)
        print(f"OUT-01 generated 100 linear annotations in {elapsed:.3f} s")
        self.assertEqual(len(outputs), 100)
        self.assertLess(elapsed, 5.0)

def main():
    dimensions.register()
    try:
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(DimensionsOutputOperatorSmokeTests)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        return 0 if result.wasSuccessful() else 1
    finally:
        dimensions.unregister()


if __name__ == "__main__":
    sys.exit(main())
