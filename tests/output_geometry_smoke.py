"""Focused smoke tests for linear-dimension world-space output geometry."""

import sys
import unittest
from pathlib import Path

import bpy
from mathutils import Vector


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

import dimensions
from dimensions.anchors import set_world_anchor
from dimensions.area_binding import bind_area_face_indices
from dimensions.collections import create_dimension_object
from dimensions.output_geometry import (
    TEXT_OUTPUT_SUPPORTED,
    WorldSizingPolicy,
    angle_dimension_label_strokes,
    angle_dimension_output_spec,
    area_dimension_label_strokes,
    area_dimension_output_spec,
    _linear_dimension_label_text,
    linear_dimension_label_layout,
    linear_dimension_label_strokes,
    linear_dimension_output_spec,
)


class DimensionsOutputGeometrySmokeTests(unittest.TestCase):
    def setUp(self):
        self.created = []
        self.context = type("Context", (), {"scene": bpy.context.scene})()
        self.original_text_placement = bpy.context.scene.dimensions_settings.text_placement

    def tearDown(self):
        bpy.context.scene.dimensions_settings.text_placement = self.original_text_placement
        for obj in self.created:
            if obj.name in bpy.data.objects:
                bpy.data.objects.remove(obj, do_unlink=True)

    def _linear_dimension(self, arrow_style="ARROW"):
        dimension = create_dimension_object(self.context, "DIM Output Geometry")
        self.created.append(dimension)
        props = dimension.dimension_props
        set_world_anchor(props.start, Vector((0.0, 0.0, 0.0)))
        set_world_anchor(props.end, Vector((4.0, 0.0, 0.0)))
        props.offset_plane_normal = (0.0, 0.0, 1.0)
        props.offset_distance = 1.0
        props.color = (0.2, 0.4, 0.8, 0.75)
        props.arrow_end_style = arrow_style
        return dimension

    def _angle_dimension(self):
        dimension = create_dimension_object(self.context, "DIM Output Angle")
        self.created.append(dimension)
        props = dimension.dimension_props
        props.annotation_kind = "ANGLE"
        set_world_anchor(props.start, Vector((1.0, 0.0, 0.0)))
        set_world_anchor(props.center, Vector((0.0, 0.0, 0.0)))
        set_world_anchor(props.end, Vector((0.0, 1.0, 0.0)))
        props.angle_radius = 0.5
        props.color = (0.8, 0.3, 0.2, 1.0)
        return dimension

    def _captured_area_dimension(self):
        dimension = create_dimension_object(self.context, "DIM Output Area")
        self.created.append(dimension)
        props = dimension.dimension_props
        props.annotation_kind = "AREA"
        props.measurement_state = "CAPTURED"
        props.area_value = 4.0
        props.area_face_count = 1
        set_world_anchor(props.start, Vector((0.0, 0.0, 0.0)))
        set_world_anchor(props.end, Vector((0.0, 2.0, 0.0)))
        props.color = (0.2, 0.8, 0.3, 1.0)
        return dimension

    def test_linear_dimension_emits_dimension_extensions_and_open_arrows(self):
        spec = linear_dimension_output_spec(
            self._linear_dimension(),
            "linear-open",
            WorldSizingPolicy(line_width=0.05, arrow_size=0.4),
        )

        self.assertEqual(spec.source_key, "linear-open")
        self.assertEqual(len(spec.strokes), 7)
        self.assertEqual(tuple(spec.strokes[0].points[0]), (0.0, 1.0, 0.0))
        self.assertEqual(tuple(spec.strokes[0].points[1]), (4.0, 1.0, 0.0))
        self.assertEqual(tuple(spec.strokes[1].points[0]), (0.0, 0.0, 0.0))
        self.assertEqual(tuple(spec.strokes[1].points[1]), (0.0, 1.0, 0.0))
        self.assertEqual(tuple(spec.strokes[2].points[0]), (4.0, 0.0, 0.0))
        self.assertEqual(tuple(spec.strokes[2].points[1]), (4.0, 1.0, 0.0))
        self.assertTrue(all(stroke.line_width == 0.05 for stroke in spec.strokes))
        for stroke in spec.strokes:
            for actual, expected in zip(stroke.color, (0.2, 0.4, 0.8, 0.75)):
                self.assertAlmostEqual(actual, expected, places=5)

    def test_architectural_ticks_are_one_world_space_stroke_per_end(self):
        arrow_size = 0.6
        spec = linear_dimension_output_spec(
            self._linear_dimension("ARCHITECTURAL_TICK"),
            "linear-ticks",
            WorldSizingPolicy(line_width=0.02, arrow_size=arrow_size),
        )

        self.assertEqual(len(spec.strokes), 5)
        self.assertAlmostEqual(
            (spec.strokes[3].points[1] - spec.strokes[3].points[0]).length,
            arrow_size,
            places=5,
        )
        self.assertAlmostEqual(
            (spec.strokes[4].points[1] - spec.strokes[4].points[0]).length,
            arrow_size,
            places=5,
        )
        self.assertEqual(
            (spec.strokes[3].points[0] + spec.strokes[3].points[1]) * 0.5,
            spec.strokes[0].points[0],
        )
        self.assertEqual(
            (spec.strokes[4].points[0] + spec.strokes[4].points[1]) * 0.5,
            spec.strokes[0].points[1],
        )

    def test_invalid_sources_return_no_output_and_text_is_supported(self):
        dimension = self._linear_dimension()
        dimension.dimension_props.annotation_kind = "AREA"
        self.assertIsNone(
            linear_dimension_output_spec(
                dimension,
                "not-linear",
                WorldSizingPolicy(line_width=0.02, arrow_size=0.4),
            )
        )
        self.assertTrue(TEXT_OUTPUT_SUPPORTED)

    def test_linear_label_generates_world_space_strokes(self):
        dimension = self._linear_dimension()
        strokes = linear_dimension_label_strokes(
            bpy.context,
            dimension,
            text_height=0.2,
            line_width=0.01,
        )
        self.assertGreater(len(strokes), 0)
        self.assertTrue(all(stroke.line_width == 0.01 for stroke in strokes))

    def test_label_layout_matches_inline_above_and_outside_presentation(self):
        dimension = self._linear_dimension()
        settings = bpy.context.scene.dimensions_settings

        settings.text_placement = "INLINE"
        inline = linear_dimension_label_layout(
            bpy.context, dimension, 0.2, 0.01, 0.2
        )
        self.assertEqual(len(inline.dimension_line_strokes), 2)

        settings.text_placement = "ABOVE"
        above = linear_dimension_label_layout(
            bpy.context, dimension, 0.2, 0.01, 0.2
        )
        self.assertEqual(above.dimension_line_strokes, ())
        self.assertGreater(
            min(point[1] for stroke in above.strokes for point in stroke.points),
            1.0,
        )

        settings.text_placement = "OUTSIDE"
        outside = linear_dimension_label_layout(
            bpy.context, dimension, 0.2, 0.01, 0.2
        )
        self.assertEqual(outside.dimension_line_strokes, ())
        self.assertGreater(
            min(point[0] for stroke in outside.strokes for point in stroke.points),
            4.0,
        )

        settings.text_placement = "OUTSIDE_START"
        outside_start = linear_dimension_label_layout(
            bpy.context, dimension, 0.2, 0.01, 0.2
        )
        self.assertEqual(outside_start.dimension_line_strokes, ())
        self.assertLess(
            max(point[0] for stroke in outside_start.strokes for point in stroke.points),
            0.0,
        )

    def test_custom_text_position_preserves_live_line_order(self):
        dimension = self._linear_dimension()
        props = dimension.dimension_props
        props.custom_text = "NOTE"
        props.custom_text_position = "ABOVE"
        above = _linear_dimension_label_text(bpy.context, props, 4.0)
        self.assertTrue(above.startswith("NOTE\n"))
        props.custom_text_position = "BELOW"
        below = _linear_dimension_label_text(bpy.context, props, 4.0)
        self.assertTrue(below.endswith("\nNOTE"))

    def test_annotation_presentation_offset_moves_generated_linework(self):
        dimension = self._linear_dimension()
        dimension.dimension_props.presentation_offset = (0.0, 2.0, 3.0)
        spec = linear_dimension_output_spec(
            dimension,
            "offset",
            WorldSizingPolicy(line_width=0.02, arrow_size=0.4),
        )

        self.assertEqual(tuple(spec.strokes[0].points[0]), (0.0, 3.0, 3.0))
        self.assertEqual(tuple(spec.strokes[0].points[1]), (4.0, 3.0, 3.0))

    def test_angle_output_emits_rays_arc_and_label_at_offset_position(self):
        dimension = self._angle_dimension()
        dimension.dimension_props.presentation_offset = (0.0, 0.0, 2.0)
        spec = angle_dimension_output_spec(
            dimension, "angle", WorldSizingPolicy(line_width=0.02, arrow_size=0.2)
        )
        self.assertIsNotNone(spec)
        self.assertEqual(len(spec.strokes), 3)
        self.assertEqual(tuple(spec.strokes[0].points[0]), (0.0, 0.0, 2.0))
        self.assertEqual(tuple(spec.strokes[0].points[1]), (1.0, 0.0, 2.0))
        self.assertGreater(len(spec.strokes[2].points), 2)
        labels = angle_dimension_label_strokes(
            bpy.context, dimension, 0.15, 0.02
        )
        self.assertGreater(len(labels), 0)

    def test_angle_output_supports_minor_supplement_and_reflex_modes(self):
        dimension = self._angle_dimension()
        sizing = WorldSizingPolicy(line_width=0.02, arrow_size=0.2)
        arc_midpoints = {}
        for mode in ("MINOR", "SUPPLEMENT", "REFLEX"):
            dimension.dimension_props.angle_mode = mode
            spec = angle_dimension_output_spec(dimension, mode.lower(), sizing)
            self.assertIsNotNone(spec)
            arc = spec.strokes[2].points
            arc_midpoints[mode] = arc[len(arc) // 2]
        self.assertGreater(arc_midpoints["MINOR"].x, 0.0)
        self.assertGreater(arc_midpoints["MINOR"].y, 0.0)
        self.assertLess(arc_midpoints["SUPPLEMENT"].y, 0.0)
        self.assertLess(arc_midpoints["REFLEX"].x, 0.0)

    def test_captured_area_output_emits_leader_marker_and_label(self):
        dimension = self._captured_area_dimension()
        spec = area_dimension_output_spec(
            dimension, "area", WorldSizingPolicy(line_width=0.02, arrow_size=0.2)
        )
        self.assertIsNotNone(spec)
        self.assertEqual(len(spec.strokes), 3)
        self.assertEqual(tuple(spec.strokes[0].points[0]), (0.0, 0.0, 0.0))
        self.assertEqual(tuple(spec.strokes[0].points[1]), (0.0, 2.0, 0.0))
        labels = area_dimension_label_strokes(
            bpy.context, dimension, 0.15, 0.02
        )
        self.assertGreater(len(labels), 0)

    def test_live_area_output_evaluates_bound_faces_in_world_space(self):
        mesh = bpy.data.meshes.new("DimensionsLiveAreaOutputMesh")
        mesh.from_pydata(
            [(0.0, 0.0, 0.0), (2.0, 0.0, 0.0), (2.0, 1.0, 0.0), (0.0, 1.0, 0.0)],
            [],
            [(0, 1, 2, 3)],
        )
        source = bpy.data.objects.new("DimensionsLiveAreaOutputSource", mesh)
        bpy.context.scene.collection.objects.link(source)
        source.location = (1.0, 2.0, 0.0)
        bpy.context.view_layer.update()
        dimension = create_dimension_object(self.context, "DIM Output Live Area")
        self.created.append(dimension)
        try:
            props = dimension.dimension_props
            props.annotation_kind = "AREA"
            result = bind_area_face_indices(props, source, [0])
            self.assertIsNotNone(result)
            props.area_placement_locked = True
            props.area_label_direction = (1.0, 0.0, 0.0)
            props.offset_distance = 2.0
            spec = area_dimension_output_spec(
                dimension, "live-area", WorldSizingPolicy(0.02, 0.2)
            )
            self.assertIsNotNone(spec)
            self.assertEqual(tuple(spec.strokes[0].points[0]), (2.0, 2.5, 0.0))
            self.assertEqual(tuple(spec.strokes[0].points[1]), (4.0, 2.5, 0.0))
            self.assertGreater(len(area_dimension_label_strokes(self.context, dimension, 0.15, 0.02)), 0)
        finally:
            if source.name in bpy.data.objects:
                bpy.data.objects.remove(source, do_unlink=True)
            if mesh.name in bpy.data.meshes:
                bpy.data.meshes.remove(mesh)

    def test_area_output_applies_presentation_offset_only_to_the_label_end(self):
        dimension = self._captured_area_dimension()
        dimension.dimension_props.presentation_offset = (1.0, 0.0, 3.0)
        spec = area_dimension_output_spec(
            dimension, "area-offset", WorldSizingPolicy(line_width=0.02, arrow_size=0.2)
        )

        self.assertEqual(tuple(spec.strokes[0].points[0]), (0.0, 0.0, 0.0))
        self.assertEqual(tuple(spec.strokes[0].points[1]), (1.0, 2.0, 3.0))

    def test_area_needs_repair_is_not_renderable(self):
        dimension = self._captured_area_dimension()
        dimension.dimension_props.measurement_state = "NEEDS_REPAIR"
        self.assertIsNone(
            area_dimension_output_spec(
                dimension, "invalid-area", WorldSizingPolicy(0.02, 0.2)
            )
        )


def main():
    dimensions.register()
    try:
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(DimensionsOutputGeometrySmokeTests)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    finally:
        dimensions.unregister()
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
