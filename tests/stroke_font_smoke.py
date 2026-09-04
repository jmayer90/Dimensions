"""Pure smoke tests for the world-space Dimensions stroke font."""

import unittest
import importlib.util
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_MODULE_SPEC = importlib.util.spec_from_file_location(
    "dimensions_stroke_font",
    REPOSITORY_ROOT / "dimensions" / "stroke_font.py",
)
_MODULE = importlib.util.module_from_spec(_MODULE_SPEC)
_MODULE_SPEC.loader.exec_module(_MODULE)
text_strokes = _MODULE.text_strokes
text_block_dimensions = _MODULE.text_block_dimensions


def _bounds(strokes):
    points = [point for stroke in strokes for point in stroke]
    return tuple(min(point[index] for point in points) for index in range(3)), tuple(
        max(point[index] for point in points) for index in range(3)
    )


class StrokeFontSmokeTests(unittest.TestCase):
    def test_block_dimensions_include_line_spacing(self):
        single_width, single_height = text_block_dimensions("123", 2.0)
        multiline_width, multiline_height = text_block_dimensions("123\n4", 2.0)
        self.assertEqual(multiline_width, single_width)
        self.assertGreater(multiline_height, single_height * 2.0)

    def test_numeric_metric_and_imperial_labels_have_strokes(self):
        for label in ("12.50 mm", '3 1/2"', "-0.125 in"):
            self.assertTrue(text_strokes(label, (0, 0, 0), (1, 0, 0), (0, 1, 0), 1.0))

    def test_alignment_moves_the_same_label_relative_to_its_origin(self):
        left = _bounds(text_strokes("12", (0, 0, 0), (1, 0, 0), (0, 1, 0), 1.0, "LEFT"))
        centered = _bounds(text_strokes("12", (0, 0, 0), (1, 0, 0), (0, 1, 0), 1.0, "CENTER"))
        right = _bounds(text_strokes("12", (0, 0, 0), (1, 0, 0), (0, 1, 0), 1.0, "RIGHT"))
        self.assertGreater(left[0][0], centered[0][0])
        self.assertGreater(centered[0][0], right[0][0])

    def test_multiline_text_advances_down_the_y_axis(self):
        strokes = text_strokes("A\nB", (0, 0, 0), (1, 0, 0), (0, 1, 0), 2.0)
        lower, upper = _bounds(strokes)
        self.assertLess(lower[1], -2.0)
        self.assertAlmostEqual(upper[1], 2.0)

    def test_axes_orient_points_in_world_space(self):
        strokes = text_strokes("I", (1, 2, 3), (0, 1, 0), (0, 0, 1), 2.0, "LEFT")
        lower, upper = _bounds(strokes)
        self.assertAlmostEqual(lower[0], 1.0)
        self.assertAlmostEqual(upper[0], 1.0)
        self.assertGreater(upper[1], lower[1])
        self.assertGreater(upper[2], lower[2])

    def test_unknown_characters_use_a_visible_fallback(self):
        self.assertEqual(
            text_strokes("mm", (0, 0, 0), (1, 0, 0), (0, 1, 0), 1.0),
            text_strokes("MM", (0, 0, 0), (1, 0, 0), (0, 1, 0), 1.0),
        )
        self.assertEqual(
            text_strokes("@", (0, 0, 0), (1, 0, 0), (0, 1, 0), 1.0),
            text_strokes("?", (0, 0, 0), (1, 0, 0), (0, 1, 0), 1.0),
        )

    def test_circular_dimension_symbols_have_native_glyphs(self):
        fallback = text_strokes("?", (0, 0, 0), (1, 0, 0), (0, 1, 0), 1.0)
        for symbol in ("⌀", "⌒"):
            strokes = text_strokes(symbol, (0, 0, 0), (1, 0, 0), (0, 1, 0), 1.0)
            self.assertTrue(strokes)
            self.assertNotEqual(strokes, fallback)

    def test_drafting_punctuation_symbols_have_native_glyphs(self):
        fallback = text_strokes("?", (0, 0, 0), (1, 0, 0), (0, 1, 0), 1.0)
        for symbol in (":", ",", "[", "]", "_", "=", "%", "&", "#"):
            strokes = text_strokes(symbol, (0, 0, 0), (1, 0, 0), (0, 1, 0), 1.0)
            self.assertTrue(strokes, f"Glyph {symbol} produced no strokes")
            self.assertNotEqual(strokes, fallback, f"Glyph {symbol} matched fallback")

    def test_height_and_axes_must_be_positive_and_usable(self):
        with self.assertRaises(ValueError):
            text_strokes("1", (0, 0, 0), (1, 0, 0), (0, 1, 0), 0.0)
        with self.assertRaises(ValueError):
            text_strokes("1", (0, 0, 0), (0, 0, 0), (0, 1, 0), 1.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
