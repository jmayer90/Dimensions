"""Focused physical-page checks for the bounded single-sheet layout core."""

import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from dimensions.sheet_layout import (
    PageMargins,
    SheetLayoutError,
    SheetMetadata,
    build_sheet_layout,
)
from dimensions.vector_export import paper_dimensions_mm


METADATA = SheetMetadata(
    title="BRACKET",
    drawing_number="D-100",
    revision="A",
    author="Ada Lovelace",
    date="2026-08-29",
    scale="1:10",
)


class SheetLayoutSmokeTests(unittest.TestCase):
    def test_border_and_fixed_title_block_use_configured_margins(self):
        layout = build_sheet_layout(
            210.0, 297.0,
            margins_mm=(12.0, 8.0, 6.0, 10.0),
            metadata=METADATA,
        )
        self.assertEqual(layout.margins, PageMargins(12.0, 8.0, 6.0, 10.0))
        self.assertEqual(layout.border_bounds, (12.0, 8.0, 204.0, 287.0))
        self.assertEqual(layout.title_block_bounds, (119.0, 251.0, 204.0, 287.0))
        self.assertEqual(layout.strokes[0].role, "BORDER")
        self.assertEqual(layout.strokes[1].role, "TITLE_BLOCK")

    def test_all_metadata_is_deterministic_vector_stroke_text(self):
        first = build_sheet_layout(297.0, 210.0, metadata=METADATA)
        second = build_sheet_layout(297.0, 210.0, metadata=METADATA)
        self.assertEqual(first, second)
        roles = {stroke.role for stroke in first.strokes}
        for field in ("TITLE", "DRAWING_NUMBER", "REVISION", "AUTHOR", "DATE", "SCALE"):
            self.assertIn(f"TEXT_{field}", roles)
        self.assertTrue(all(len(point) == 2 for stroke in first.strokes for point in stroke.points))
        with self.assertRaises(FrozenInstanceError):
            first.width_mm = 1.0

    def test_physical_title_block_text_and_line_weight_ignore_page_and_model_scale(self):
        layouts = []
        for paper, orientation in (
            ("A4", "PORTRAIT"),
            ("A4", "LANDSCAPE"),
            ("A3", "PORTRAIT"),
            ("LETTER", "LANDSCAPE"),
        ):
            width, height = paper_dimensions_mm(paper, orientation)
            # A model-to-paper factor is deliberately absent from this API.
            for _model_scale in (0.001, 1.0, 1000.0):
                layouts.append(build_sheet_layout(
                    width, height, metadata=METADATA,
                    title_block_width_mm=105.0,
                    title_block_height_mm=36.0,
                    line_width_mm=0.25,
                    text_height_mm=2.5,
                ))
        for layout in layouts:
            left, top, right, bottom = layout.title_block_bounds
            self.assertAlmostEqual(right - left, 105.0)
            self.assertAlmostEqual(bottom - top, 36.0)
            self.assertTrue(all(stroke.line_width_mm == 0.25 for stroke in layout.strokes))
        for index in range(0, len(layouts), 3):
            self.assertEqual(layouts[index].strokes, layouts[index + 1].strokes)
            self.assertEqual(layouts[index].strokes, layouts[index + 2].strokes)

    def test_invalid_margins_and_blocks_are_rejected(self):
        invalid_calls = (
            lambda: build_sheet_layout(210, 297, margins_mm=-1, metadata=METADATA),
            lambda: build_sheet_layout(210, 297, margins_mm=(10, 10, 200, 10), metadata=METADATA),
            lambda: build_sheet_layout(210, 297, margins_mm=(1, 2, 3), metadata=METADATA),
            lambda: build_sheet_layout(210, 297, title_block_width_mm=59, metadata=METADATA),
            lambda: build_sheet_layout(210, 297, title_block_height_mm=23, metadata=METADATA),
            lambda: build_sheet_layout(100, 100, margins_mm=30, title_block_width_mm=85, metadata=METADATA),
        )
        for call in invalid_calls:
            with self.subTest(call=call), self.assertRaises(SheetLayoutError):
                call()

    def test_disabled_furniture_is_not_emitted_or_irrelevantly_validated(self):
        border_only = build_sheet_layout(
            210, 297,
            border_enabled=True,
            title_block_enabled=False,
            title_block_width_mm=-1,
            text_height_mm=-1,
            metadata=object(),
        )
        self.assertEqual(tuple(stroke.role for stroke in border_only.strokes), ("BORDER",))
        self.assertIsNone(border_only.title_block_bounds)

        title_only = build_sheet_layout(
            210, 297,
            border_enabled=False,
            title_block_enabled=True,
            metadata=METADATA,
        )
        self.assertNotIn("BORDER", {stroke.role for stroke in title_only.strokes})
        self.assertIn("TITLE_BLOCK", {stroke.role for stroke in title_only.strokes})

        empty = build_sheet_layout(
            210, 297,
            border_enabled=False,
            title_block_enabled=False,
            line_width_mm=-1,
            color=object(),
            title_block_width_mm=-1,
            metadata=object(),
        )
        self.assertEqual(empty.strokes, ())
        self.assertIsNone(empty.title_block_bounds)

    def test_metadata_that_cannot_fit_is_rejected_instead_of_clipped(self):
        metadata = SheetMetadata(
            title="AN EXTREMELY LONG DRAWING TITLE THAT CANNOT FIT",
            drawing_number="D-100",
            revision="A",
            author="ADA",
            date="2026-08-29",
            scale="1/10",
        )
        with self.assertRaisesRegex(SheetLayoutError, "Title does not fit"):
            build_sheet_layout(210, 297, metadata=metadata)

    def test_default_block_accepts_empty_punctuation_and_full_supported_scale(self):
        metadata = SheetMetadata(
            title="",
            drawing_number="A-201/REV.B",
            revision="-",
            author="Ada Lovelace",
            date="",
            scale="1:100000",
        )
        layout = build_sheet_layout(
            210, 297,
            title_block_width_mm=80,
            title_block_height_mm=30,
            metadata=metadata,
        )
        roles = {stroke.role for stroke in layout.strokes}
        for field in ("TITLE", "DRAWING_NUMBER", "REVISION", "AUTHOR", "DATE", "SCALE"):
            self.assertIn(f"TEXT_{field}", roles)


def main():
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(SheetLayoutSmokeTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
