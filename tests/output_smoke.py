"""Focused Blender smoke tests for the isolated OUT-01 output backend."""

import sys
import tempfile
import unittest
from pathlib import Path

import bpy


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from dimensions.grease_pencil_output import (
    GENERATED_OUTPUT_TAG,
    OUTPUT_SOURCE_KEY,
    TEXT_TO_STROKE_SUPPORTED,
    GreasePencilOutputSpec,
    OutputStroke,
    _remove_generated_object,
    generated_output_objects,
    find_output_collection,
    generate_grease_pencil_output,
    get_or_create_output_collection,
)


class DimensionsOutputSmokeTests(unittest.TestCase):
    def setUp(self):
        self.scene = bpy.context.scene
        self.created = []

    def tearDown(self):
        for obj in self.created:
            if obj.name in bpy.data.objects:
                _remove_generated_object(obj)

    def _spec(self, source_key="smoke"):
        return GreasePencilOutputSpec(
            source_key=source_key,
            strokes=(
                OutputStroke(
                    points=((0.0, 0.0, 0.0), (2.0, 0.0, 0.0)),
                    color=(1.0, 0.2, 0.1, 1.0),
                    line_width=0.02,
                ),
                OutputStroke(
                    points=((0.0, 0.5, 0.0), (2.0, 0.5, 0.0)),
                    color=(0.1, 0.4, 1.0, 0.75),
                    line_width=0.04,
                ),
            ),
        )

    def test_creates_tagged_gpv3_strokes_in_scene_owned_collection(self):
        output = generate_grease_pencil_output(self.scene, self._spec())
        self.created.append(output)

        collection = get_or_create_output_collection(self.scene)
        self.assertIn(output.name, collection.objects)
        self.assertEqual(output.type, "GREASEPENCIL")
        self.assertTrue(output[GENERATED_OUTPUT_TAG])
        self.assertEqual(output[OUTPUT_SOURCE_KEY], "smoke")
        self.assertEqual(len(output.data.layers), 1)
        frame = output.data.layers[0].frames[0]
        self.assertEqual(frame.frame_number, self.scene.frame_current)
        drawing = frame.drawing
        self.assertEqual(len(drawing.strokes), 2)
        self.assertEqual(len(drawing.strokes[0].points), 2)
        self.assertEqual(tuple(drawing.strokes[0].points[1].position), (2.0, 0.0, 0.0))
        self.assertAlmostEqual(drawing.strokes[0].points[0].radius, 0.01, places=6)
        self.assertAlmostEqual(drawing.strokes[1].points[0].opacity, 0.75, places=6)
        self.assertEqual(len(output.data.materials), 2)

    def test_same_source_key_replaces_without_duplicates(self):
        first = generate_grease_pencil_output(self.scene, self._spec())
        second = generate_grease_pencil_output(self.scene, self._spec())
        self.created.append(second)

        outputs = generated_output_objects(self.scene, "smoke")
        self.assertEqual(outputs, (second,))
        self.assertEqual(len(generated_output_objects(self.scene)), 1)

    def test_output_pipeline_supports_text_strokes(self):
        self.assertTrue(TEXT_TO_STROKE_SUPPORTED)

    def test_querying_output_does_not_create_a_collection(self):
        other_scene = bpy.data.scenes.new("Dimensions Empty Output Query")
        try:
            self.assertIsNone(find_output_collection(other_scene))
            self.assertEqual(generated_output_objects(other_scene), ())
            self.assertIsNone(find_output_collection(other_scene))
        finally:
            bpy.data.scenes.remove(other_scene)

    def test_invalid_spec_rolls_back_without_creating_blender_data(self):
        def ids(collection):
            return {item.as_pointer() for item in collection}

        before = tuple(
            ids(collection)
            for collection in (bpy.data.objects, bpy.data.grease_pencils, bpy.data.materials, bpy.data.collections)
        )
        invalid_specs = (
            {"source_key": "invalid-empty", "strokes": ()},
            {
                "source_key": "invalid-points",
                "strokes": ({"points": ((0.0, 0.0, 0.0),), "line_width": 0.01},),
            },
            {
                "source_key": "invalid-width",
                "strokes": ({"points": ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0)), "line_width": 0.0},),
            },
        )
        for spec in invalid_specs:
            with self.assertRaises((TypeError, ValueError)):
                generate_grease_pencil_output(self.scene, spec)

        after = tuple(
            ids(collection)
            for collection in (bpy.data.objects, bpy.data.grease_pencils, bpy.data.materials, bpy.data.collections)
        )
        self.assertEqual(after, before)

    def test_output_collection_is_isolated_between_scenes(self):
        other_scene = bpy.data.scenes.new("Dimensions Output Isolation")
        output = None
        collection = None
        try:
            output = generate_grease_pencil_output(other_scene, self._spec("other-scene"))
            collection = get_or_create_output_collection(other_scene)
            self.assertIn(output.name, collection.objects)
            self.assertNotIn(output, tuple(self.scene.collection.all_objects))
            self.assertEqual(generated_output_objects(other_scene, "other-scene"), (output,))
            self.assertEqual(generated_output_objects(self.scene, "other-scene"), ())
        finally:
            if output is not None and output.name in bpy.data.objects:
                _remove_generated_object(output)
            bpy.data.scenes.remove(other_scene)
            if collection is not None and collection.users == 0:
                bpy.data.collections.remove(collection)

    def test_user_collection_name_collision_is_not_adopted(self):
        existing_named = bpy.data.collections.get("Dimensions Output")
        existing_name = existing_named.name if existing_named is not None else None
        if existing_named is not None:
            existing_named.name = "Dimensions Output Existing Test"
        other_scene = bpy.data.scenes.new("Dimensions Output Name Collision")
        user_collection = bpy.data.collections.new("Dimensions Output")
        other_scene.collection.children.link(user_collection)
        output_collection = None
        try:
            output_collection = get_or_create_output_collection(other_scene)
            self.assertNotEqual(output_collection, user_collection)
            self.assertIsNone(user_collection.get("dimensions_collection_role"))
            self.assertEqual(
                output_collection.get("dimensions_collection_role"),
                "DIMENSIONS_OUTPUT",
            )
        finally:
            bpy.data.scenes.remove(other_scene)
            for collection in (output_collection, user_collection):
                if collection is not None and collection.users == 0:
                    bpy.data.collections.remove(collection)
            if existing_named is not None and existing_named.name in bpy.data.collections:
                existing_named.name = existing_name

    def test_shared_tagged_collection_is_not_reused_by_another_scene(self):
        original_collection = get_or_create_output_collection(self.scene)
        other_scene = bpy.data.scenes.new("Dimensions Shared Output Guard")
        other_scene.collection.children.link(original_collection)
        other_collection = None
        try:
            other_collection = get_or_create_output_collection(other_scene)
            self.assertNotEqual(other_collection, original_collection)
            owners = [
                scene
                for scene in bpy.data.scenes
                if other_collection in scene.collection.children_recursive
            ]
            self.assertEqual(owners, [other_scene])
        finally:
            bpy.data.scenes.remove(other_scene)
            if other_collection is not None and other_collection.users == 0:
                bpy.data.collections.remove(other_collection)

    def test_generated_strokes_render_in_eevee_and_cycles_when_available(self):
        output = generate_grease_pencil_output(
            self.scene,
            GreasePencilOutputSpec(
                source_key="render-smoke",
                strokes=(
                    OutputStroke(
                        points=((-1.0, 0.0, 0.0), (1.0, 0.0, 0.0)),
                        color=(1.0, 1.0, 1.0, 1.0),
                        line_width=0.08,
                    ),
                ),
            ),
        )
        self.created.append(output)

        camera_data = bpy.data.cameras.new("Dimensions Output Render Camera")
        camera = bpy.data.objects.new("Dimensions Output Render Camera", camera_data)
        self.scene.collection.objects.link(camera)
        world = bpy.data.worlds.new("Dimensions Output Render World")
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
            camera.location = (0.0, 0.0, 5.0)
            camera_data.type = "ORTHO"
            camera_data.ortho_scale = 3.0
            camera_data.clip_start = 0.1
            camera_data.clip_end = 100.0
            render.resolution_x = 128
            render.resolution_y = 128
            render.resolution_percentage = 100
            render.film_transparent = False

            with tempfile.TemporaryDirectory(prefix="dimensions-output-render-") as directory:
                for engine in ("BLENDER_EEVEE", "CYCLES"):
                    try:
                        render.engine = engine
                    except (TypeError, ValueError) as error:
                        unsupported.append(f"{engine}: {error}")
                        print(f"OUT-01 render engine unsupported: {engine}: {error}")
                        continue

                    render.filepath = str(Path(directory) / f"{engine}.png")
                    if engine == "CYCLES":
                        self.scene.cycles.samples = 1
                    try:
                        bpy.ops.render.render(write_still=True)
                    except (RuntimeError, OSError) as error:
                        if engine == "CYCLES":
                            unsupported.append(f"{engine}: {error}")
                            print(f"OUT-01 render engine unsupported: {engine}: {error}")
                            continue
                        raise

                    rendered = bpy.data.images.load(render.filepath, check_existing=False)
                    try:
                        pixels = [0.0] * (rendered.size[0] * rendered.size[1] * 4)
                        rendered.pixels.foreach_get(pixels)
                        visible = any(
                            max(pixels[index:index + 3]) > 0.05
                            for index in range(0, len(pixels), 4)
                        )
                        self.assertTrue(visible, f"{engine} rendered an empty image")
                    finally:
                        bpy.data.images.remove(rendered)

            if unsupported:
                print("OUT-01 render engines unavailable: " + "; ".join(unsupported))
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


def main():
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(DimensionsOutputSmokeTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
