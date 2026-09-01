"""Focused Blender smoke tests for the OUT-01 generation workflow."""

import os
import sys
import tempfile
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
        self.original_depth_pass = bpy.context.view_layer.use_pass_z
        self.original_grease_pencil_pass = bpy.context.view_layer.use_pass_grease_pencil

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
        bpy.context.view_layer.use_pass_z = self.original_depth_pass
        bpy.context.view_layer.use_pass_grease_pencil = self.original_grease_pencil_pass

    def _dimension(self, name, start=(0.0, 0.0, 0.0), end=(2.0, 0.0, 0.0)):
        dimension = create_dimension_object(bpy.context, name)
        set_world_anchor(dimension.dimension_props.start, Vector(start))
        set_world_anchor(dimension.dimension_props.end, Vector(end))
        dimension.location = _annotation_world_depth_point(dimension)
        self.created.append(dimension)
        return dimension

    def _angle(self, name):
        annotation = self._dimension(name)
        props = annotation.dimension_props
        props.annotation_kind = "ANGLE"
        set_world_anchor(props.start, Vector((1.0, 0.0, 0.0)))
        set_world_anchor(props.center, Vector((0.0, 0.0, 0.0)))
        set_world_anchor(props.end, Vector((0.0, 1.0, 0.0)))
        props.angle_radius = 0.5
        annotation.location = (0.0, 0.0, 0.0)
        return annotation

    def _captured_area(self, name):
        annotation = self._dimension(name)
        props = annotation.dimension_props
        props.annotation_kind = "AREA"
        props.measurement_state = "CAPTURED"
        props.area_value = 4.0
        props.area_face_count = 1
        set_world_anchor(props.start, Vector((0.0, 0.0, 0.0)))
        set_world_anchor(props.end, Vector((0.0, 2.0, 0.0)))
        annotation.location = (0.0, 1.0, 0.0)
        return annotation

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

    def test_invalid_source_removes_matching_generated_artifact(self):
        self._remove_existing_output()
        settings = self.scene.dimensions_settings
        settings.output_scope = "VISIBLE"
        settings.output_sizing_mode = "WORLD"
        dimension = self._dimension("DIM Output Invalid Cleanup")
        self.assertEqual(bpy.ops.dimensions.generate_output(), {"FINISHED"})
        key = annotation_output_key(self.scene, dimension)
        self.assertEqual(len(generated_output_objects(self.scene, key)), 1)

        dimension.dimension_props.start.anchor_type = "VERTEX"
        dimension.dimension_props.start.target_object = None
        self.assertEqual(bpy.ops.dimensions.generate_output(), {"FINISHED"})
        self.assertEqual(generated_output_objects(self.scene, key), ())

    def test_deleted_annotation_removes_its_generated_artifact(self):
        self._remove_existing_output()
        settings = self.scene.dimensions_settings
        settings.output_scope = "VISIBLE"
        settings.output_sizing_mode = "WORLD"
        dimension = self._dimension("DIM Output Deleted Cleanup")
        self.assertEqual(bpy.ops.dimensions.generate_output(), {"FINISHED"})
        key = annotation_output_key(self.scene, dimension)
        self.assertEqual(len(generated_output_objects(self.scene, key)), 1)

        self.created.remove(dimension)
        bpy.data.objects.remove(dimension, do_unlink=True)
        self.assertEqual(bpy.ops.dimensions.generate_output(), {"FINISHED"})
        self.assertEqual(generated_output_objects(self.scene, key), ())

    def test_visible_scope_removes_hidden_artifact_but_selected_scope_preserves_unselected(self):
        self._remove_existing_output()
        settings = self.scene.dimensions_settings
        settings.output_sizing_mode = "WORLD"
        visible = self._dimension("DIM Output Hidden Cleanup")
        settings.output_scope = "VISIBLE"
        self.assertEqual(bpy.ops.dimensions.generate_output(), {"FINISHED"})
        key = annotation_output_key(self.scene, visible)
        self.assertEqual(len(generated_output_objects(self.scene, key)), 1)

        visible.hide_set(True)
        self.assertEqual(bpy.ops.dimensions.generate_output(), {"FINISHED"})
        self.assertEqual(generated_output_objects(self.scene, key), ())
        visible.hide_set(False)

        visible.select_set(True)
        self.assertEqual(bpy.ops.dimensions.generate_output(), {"FINISHED"})
        visible.select_set(False)
        other = self._dimension("DIM Output Selected Reconcile")
        other.select_set(True)
        settings.output_scope = "SELECTED"
        self.assertEqual(bpy.ops.dimensions.generate_output(), {"FINISHED"})
        self.assertEqual(len(generated_output_objects(self.scene, key)), 1)

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

    def test_area_camera_depth_uses_the_offset_label_not_the_source_center(self):
        area = self._captured_area("DIM Output Area Depth")
        area.dimension_props.presentation_offset = (0.0, 0.0, 4.0)

        self.assertEqual(tuple(_annotation_world_depth_point(area)), (0.0, 1.0, 2.0))

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

    def test_operator_generates_mixed_linear_angle_and_captured_area_output(self):
        self._remove_existing_output()
        settings = self.scene.dimensions_settings
        settings.output_sizing_mode = "WORLD"
        settings.output_scope = "VISIBLE"
        linear = self._dimension("DIM Output Mixed Linear")
        angle = self._angle("DIM Output Mixed Angle")
        area = self._captured_area("DIM Output Mixed Area")
        self.assertEqual(bpy.ops.dimensions.generate_output(), {"FINISHED"})
        outputs = generated_output_objects(self.scene)
        self.created.extend(outputs)
        self.assertEqual(len(outputs), 3)
        keys = {output.get("dimensions_output_source_key") for output in outputs}
        self.assertEqual(
            keys,
            {
                annotation_output_key(self.scene, linear),
                annotation_output_key(self.scene, angle),
                annotation_output_key(self.scene, area),
            },
        )
        self.assertTrue(all(len(output.data.layers[0].frames[0].drawing.strokes) > 2 for output in outputs))
        self.assertTrue(bpy.context.view_layer.use_pass_z)
        self.assertTrue(bpy.context.view_layer.use_pass_grease_pencil)
        self.assertTrue(all(not output.use_grease_pencil_lights for output in outputs))
        self.assertTrue(all(output.data.stroke_depth_order == "3D" for output in outputs))

    def test_regenerating_angle_and_area_replaces_only_matching_artifact(self):
        self._remove_existing_output()
        self.addCleanup(self._remove_existing_output)
        settings = self.scene.dimensions_settings
        settings.output_sizing_mode = "WORLD"
        settings.output_scope = "SELECTED"
        angle = self._angle("DIM Output Regenerate Angle")
        area = self._captured_area("DIM Output Regenerate Area")
        angle.select_set(True)
        area.select_set(True)
        bpy.context.view_layer.objects.active = angle
        self.assertEqual(bpy.ops.dimensions.generate_output(), {"FINISHED"})
        angle_key = annotation_output_key(self.scene, angle)
        area_key = annotation_output_key(self.scene, area)
        original_angle = generated_output_objects(self.scene, angle_key)[0]
        original_area = generated_output_objects(self.scene, area_key)[0]

        angle.select_set(True)
        area.select_set(False)
        bpy.context.view_layer.objects.active = angle
        self.assertEqual(bpy.ops.dimensions.generate_output(), {"FINISHED"})
        replaced_angle = generated_output_objects(self.scene, angle_key)[0]
        self.assertIsNot(replaced_angle, original_angle)
        self.assertIs(generated_output_objects(self.scene, area_key)[0], original_area)

        angle.select_set(False)
        area.select_set(True)
        bpy.context.view_layer.objects.active = area
        self.assertEqual(bpy.ops.dimensions.generate_output(), {"FINISHED"})
        replaced_area = generated_output_objects(self.scene, area_key)[0]
        self.assertIsNot(replaced_area, original_area)
        self.assertIs(generated_output_objects(self.scene, angle_key)[0], replaced_angle)

    @unittest.skipIf(
        os.environ.get("DIMENSIONS_SKIP_RENDER_TESTS") == "1",
        "GPU render engines are unavailable on this runner",
    )
    def test_mixed_annotations_render_in_eevee_and_cycles(self):
        self._remove_existing_output()
        settings = self.scene.dimensions_settings
        settings.output_sizing_mode = "WORLD"
        settings.output_scope = "VISIBLE"
        self._dimension("DIM Output Render Linear", start=(-2.0, -1.0, 0.0), end=(2.0, -1.0, 0.0))
        self._angle("DIM Output Render Angle")
        self._captured_area("DIM Output Render Area")
        self.assertEqual(bpy.ops.dimensions.generate_output(), {"FINISHED"})
        outputs = generated_output_objects(self.scene)
        self.created.extend(outputs)

        camera_data = bpy.data.cameras.new("Dimensions Mixed Output Camera")
        camera = bpy.data.objects.new("Dimensions Mixed Output Camera", camera_data)
        self.scene.collection.objects.link(camera)
        world = bpy.data.worlds.new("Dimensions Mixed Output World")
        world.use_nodes = True
        world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.0, 0.0, 0.0, 1.0)
        world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.0
        render = self.scene.render
        original = (
            render.engine,
            self.scene.camera,
            self.scene.world,
            render.resolution_x,
            render.resolution_y,
            render.resolution_percentage,
            render.filepath,
            render.film_transparent,
        )
        unsupported = []
        try:
            self.scene.camera = camera
            self.scene.world = world
            camera.location = (0.0, 0.0, 8.0)
            camera_data.type = "ORTHO"
            camera_data.ortho_scale = 6.0
            camera_data.clip_start = 0.1
            camera_data.clip_end = 100.0
            render.resolution_x = 128
            render.resolution_y = 128
            render.resolution_percentage = 100
            render.film_transparent = False
            with tempfile.TemporaryDirectory(prefix="dimensions-mixed-output-render-") as directory:
                for engine in ("BLENDER_EEVEE", "CYCLES"):
                    try:
                        render.engine = engine
                    except (TypeError, ValueError) as error:
                        unsupported.append(f"{engine}: {error}")
                        continue
                    render.filepath = str(Path(directory) / f"{engine}.png")
                    if engine == "CYCLES":
                        self.scene.cycles.samples = 1
                    try:
                        bpy.ops.render.render(write_still=True)
                    except (RuntimeError, OSError) as error:
                        if engine == "CYCLES":
                            unsupported.append(f"{engine}: {error}")
                            continue
                        raise
                    image = bpy.data.images.load(render.filepath, check_existing=False)
                    try:
                        pixels = [0.0] * (image.size[0] * image.size[1] * 4)
                        image.pixels.foreach_get(pixels)
                        self.assertTrue(
                            any(max(pixels[index:index + 3]) > 0.05 for index in range(0, len(pixels), 4)),
                            f"{engine} rendered an empty mixed annotation image",
                        )
                    finally:
                        bpy.data.images.remove(image)
            self.assertNotIn("BLENDER_EEVEE", {item.split(":", 1)[0] for item in unsupported})
        finally:
            if camera.name in bpy.data.objects:
                bpy.data.objects.remove(camera, do_unlink=True)
            if camera_data.name in bpy.data.cameras:
                bpy.data.cameras.remove(camera_data)
            if world.name in bpy.data.worlds:
                bpy.data.worlds.remove(world)
            render.engine = original[0]
            self.scene.camera = original[1]
            self.scene.world = original[2]
            render.resolution_x = original[3]
            render.resolution_y = original[4]
            render.resolution_percentage = original[5]
            render.filepath = original[6]
            render.film_transparent = original[7]

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
