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
from dimensions.collections import create_dimension_object
from dimensions.output_geometry import (
    TEXT_OUTPUT_SUPPORTED,
    WorldSizingPolicy,
    linear_dimension_output_spec,
)


class DimensionsOutputGeometrySmokeTests(unittest.TestCase):
    def setUp(self):
        self.created = []
        self.context = type("Context", (), {"scene": bpy.context.scene})()

    def tearDown(self):
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

    def test_invalid_sources_return_no_output_and_text_is_deferred(self):
        dimension = self._linear_dimension()
        dimension.dimension_props.annotation_kind = "AREA"
        self.assertIsNone(
            linear_dimension_output_spec(
                dimension,
                "not-linear",
                WorldSizingPolicy(line_width=0.02, arrow_size=0.4),
            )
        )
        self.assertFalse(TEXT_OUTPUT_SUPPORTED)

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
