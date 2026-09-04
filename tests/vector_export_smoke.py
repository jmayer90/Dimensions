"""Focused OUT-02 physical-scale SVG and PDF export checks."""

import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
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
from dimensions.grease_pencil_output import OutputStroke
from dimensions.operators.export_vector import build_scene_vector_document, vector_output_strokes
from dimensions.vector_export import (
    VectorExportError,
    build_vector_document,
    paper_dimensions_mm,
    pdf_bytes,
    svg_text,
)


class DimensionsVectorExportTests(unittest.TestCase):
    def setUp(self):
        self.scene = bpy.context.scene
        self.created = []
        self.original_camera = self.scene.camera
        self.original_scale_length = self.scene.unit_settings.scale_length
        camera_data = bpy.data.cameras.new(f"OUT-02 Camera {self._testMethodName}")
        camera_data.type = "ORTHO"
        camera_data.ortho_scale = 1.0
        self.camera = bpy.data.objects.new(f"OUT-02 Camera {self._testMethodName}", camera_data)
        self.scene.collection.objects.link(self.camera)
        self.camera.location = (0.0, 0.0, 10.0)
        self.scene.camera = self.camera
        self.scene.render.resolution_x = 1000
        self.scene.render.resolution_y = 1000
        self.scene.render.resolution_percentage = 100
        self.scene.unit_settings.scale_length = 1.0
        settings = self.scene.dimensions_settings
        settings.output_scope = "VISIBLE"
        settings.vector_paper_size = "A4"
        settings.vector_orientation = "PORTRAIT"
        settings.vector_scale_denominator = 10.0
        settings.vector_line_width_mm = 0.25
        settings.vector_text_height_mm = 3.5
        settings.vector_arrow_size_mm = 2.5
        settings.sheet_border_enabled = False
        settings.sheet_title_block_enabled = False
        settings.sheet_margin_mm = 10.0
        settings.sheet_title_block_width_mm = 80.0
        settings.sheet_title_block_height_mm = 30.0
        settings.sheet_drawing_title = ""
        settings.sheet_drawing_number = ""
        settings.sheet_revision = ""
        settings.sheet_author = ""
        settings.sheet_date = ""

    def tearDown(self):
        for obj in reversed(self.created):
            if bpy.data.objects.get(obj.name) is not None:
                bpy.data.objects.remove(obj, do_unlink=True)
        camera_data = self.camera.data
        if bpy.data.objects.get(self.camera.name) is not None:
            bpy.data.objects.remove(self.camera, do_unlink=True)
        if camera_data.users == 0:
            bpy.data.cameras.remove(camera_data)
        self.scene.camera = self.original_camera
        self.scene.unit_settings.scale_length = self.original_scale_length

    def _dimension(self, name, start=(-0.05, 0.0, 0.0), end=(0.05, 0.0, 0.0)):
        dimension = create_dimension_object(bpy.context, name)
        set_world_anchor(dimension.dimension_props.start, Vector(start))
        set_world_anchor(dimension.dimension_props.end, Vector(end))
        dimension.dimension_props.offset_distance = 0.0
        self.created.append(dimension)
        return dimension

    def _document_for_stroke(self, stroke, **overrides):
        options = {
            "paper_size": "A4",
            "orientation": "PORTRAIT",
            "scale_denominator": 10.0,
            "annotation_count": 1,
        }
        options.update(overrides)
        self.camera.data.ortho_scale = 0.2
        return build_vector_document(self.scene, self.camera, (stroke,), **options)

    def test_one_hundred_millimetres_at_one_to_ten_spans_ten_millimetres(self):
        document = self._document_for_stroke(OutputStroke(
            points=(Vector((-0.05, 0.0, 0.0)), Vector((0.05, 0.0, 0.0))),
            color=(0.2, 0.4, 0.6, 1.0),
            line_width=0.0025,
        ))
        root = ET.fromstring(svg_text(document))
        polyline = root.find(".//{http://www.w3.org/2000/svg}polyline")
        points = [tuple(map(float, value.split(","))) for value in polyline.attrib["points"].split()]
        self.assertAlmostEqual(abs(points[1][0] - points[0][0]), 10.0, places=5)
        self.assertEqual(root.attrib["width"], "210mm")
        self.assertEqual(root.attrib["height"], "297mm")
        self.assertEqual(polyline.attrib["stroke"], "#336699")
        self.assertAlmostEqual(float(polyline.attrib["stroke-width"]), 0.25, places=6)

    def test_paper_size_and_orientation_are_physical(self):
        self.assertEqual(paper_dimensions_mm("A4", "PORTRAIT"), (210.0, 297.0))
        self.assertEqual(paper_dimensions_mm("A4", "LANDSCAPE"), (297.0, 210.0))
        self.assertEqual(paper_dimensions_mm("A3", "PORTRAIT"), (297.0, 420.0))
        self.assertEqual(paper_dimensions_mm("LETTER", "LANDSCAPE"), (279.4, 215.9))

    def test_pdf_is_single_page_with_the_selected_media_box(self):
        document = self._document_for_stroke(OutputStroke(
            points=(Vector((-0.05, 0.0, 0.0)), Vector((0.05, 0.0, 0.0))),
            color=(1.0, 0.0, 0.0, 1.0),
            line_width=0.0025,
        ), paper_size="A3", orientation="LANDSCAPE")
        data = pdf_bytes(document)
        self.assertTrue(data.startswith(b"%PDF-1.4"))
        self.assertTrue(data.rstrip().endswith(b"%%EOF"))
        self.assertIn(b"/Count 1", data)
        self.assertIn(b"/MediaBox [0 0 1190.551181 841.889764]", data)

    def test_operator_exports_valid_svg_and_pdf_with_stroke_labels(self):
        dimension = self._dimension("DIM OUT-02 Operator")
        dimension.dimension_props.color = (0.1, 0.7, 0.3, 1.0)
        dimension.dimension_props.custom_text = "TEST"
        self.camera.data.ortho_scale = 1.0
        with tempfile.TemporaryDirectory(prefix="dimensions-vector-export-") as directory:
            svg_path = Path(directory) / "drawing.svg"
            pdf_path = Path(directory) / "drawing.pdf"
            self.assertEqual(
                bpy.ops.dimensions.export_svg(filepath=str(svg_path)),
                {"FINISHED"},
            )
            self.assertEqual(
                bpy.ops.dimensions.export_pdf(filepath=str(pdf_path)),
                {"FINISHED"},
            )
            root = ET.parse(svg_path).getroot()
            polylines = root.findall(".//{http://www.w3.org/2000/svg}polyline")
            self.assertGreater(len(polylines), 10)
            self.assertEqual(root.findall(".//{http://www.w3.org/2000/svg}text"), [])
            self.assertTrue(pdf_path.read_bytes().startswith(b"%PDF-1.4"))

    def test_sheet_controls_are_independent_and_svg_pdf_serialize_the_same_strokes(self):
        self._dimension("DIM OUT-05 Sheet Parity")
        settings = self.scene.dimensions_settings
        self.camera.data.ortho_scale = 1.0

        settings.sheet_border_enabled = True
        border_document = build_scene_vector_document(bpy.context)
        self.assertEqual(
            [stroke.role for stroke in border_document.strokes].count("BORDER"), 1,
        )
        self.assertFalse(any(
            stroke.role.startswith("TITLE") or stroke.role.startswith("TEXT_")
            for stroke in border_document.strokes
        ))

        settings.sheet_border_enabled = False
        settings.sheet_title_block_enabled = True
        settings.sheet_drawing_title = "BRACKET"
        settings.sheet_drawing_number = "D-100"
        settings.sheet_revision = "A"
        settings.sheet_author = "Ada Lovelace"
        settings.sheet_date = "2026-08-29"
        settings.vector_scale_denominator = 100000.0
        document = build_scene_vector_document(bpy.context)
        roles = {stroke.role for stroke in document.strokes}
        self.assertNotIn("BORDER", roles)
        self.assertIn("TITLE_BLOCK", roles)
        for role in (
            "TEXT_TITLE", "TEXT_DRAWING_NUMBER", "TEXT_REVISION",
            "TEXT_AUTHOR", "TEXT_DATE", "TEXT_SCALE",
        ):
            self.assertIn(role, roles)

        root = ET.fromstring(svg_text(document))
        polylines = root.findall(".//{http://www.w3.org/2000/svg}polyline")
        pdf = pdf_bytes(document)
        self.assertEqual(len(polylines), len(document.strokes))
        self.assertEqual(pdf.count(b"\nS\n"), len(document.strokes))
        self.assertIn(b"/Count 1", pdf)

    def test_sheet_geometry_is_physical_and_does_not_change_annotation_projection(self):
        self._dimension("DIM OUT-05 Physical Invariance")
        settings = self.scene.dimensions_settings
        self.camera.data.ortho_scale = 0.1
        baseline = build_scene_vector_document(bpy.context)
        baseline_annotations = tuple(
            stroke for stroke in baseline.strokes if stroke.role == "ANNOTATION"
        )

        settings.sheet_border_enabled = True
        settings.sheet_title_block_enabled = True
        settings.sheet_drawing_title = "PART"
        settings.sheet_drawing_number = "D-1"
        settings.sheet_revision = "A"
        settings.sheet_author = "ADA"
        settings.sheet_date = "2026-08-29"
        with_sheet = build_scene_vector_document(bpy.context)
        self.assertEqual(
            tuple(stroke for stroke in with_sheet.strokes if stroke.role == "ANNOTATION"),
            baseline_annotations,
        )

        invariant_roles = {"BORDER", "TITLE_BLOCK", "TITLE_GRID"}
        layouts = []
        for camera_scale, unit_scale, denominator in (
            (0.1, 1.0, 10.0),
            (0.2, 0.001, 10.0),
            (0.05, 1.0, 100.0),
        ):
            self.camera.data.ortho_scale = camera_scale
            self.scene.unit_settings.scale_length = unit_scale
            settings.vector_scale_denominator = denominator
            document = build_scene_vector_document(bpy.context)
            layouts.append(tuple(
                stroke for stroke in document.strokes if stroke.role in invariant_roles
            ))
        self.assertEqual(layouts[0], layouts[1])
        self.assertEqual(layouts[0], layouts[2])

    def test_invalid_sheet_layout_is_rejected_before_writing(self):
        self._dimension("DIM OUT-05 Invalid Sheet")
        settings = self.scene.dimensions_settings
        settings.sheet_title_block_enabled = True
        settings.sheet_title_block_width_mm = 300.0
        with self.assertRaisesRegex(VectorExportError, "does not fit"):
            build_scene_vector_document(bpy.context)
        with tempfile.TemporaryDirectory(prefix="dimensions-invalid-sheet-") as directory:
            filepath = Path(directory) / "invalid.svg"
            self.assertEqual(
                bpy.ops.dimensions.export_svg(filepath=str(filepath)),
                {"CANCELLED"},
            )
            self.assertFalse(filepath.exists())

    def test_fallback_and_needs_repair_annotations_are_skipped(self):
        live = self._dimension("DIM OUT-02 Live", start=(-0.2, 0.0, 0.0), end=(-0.1, 0.0, 0.0))
        fallback = self._dimension("DIM OUT-02 Fallback", start=(0.0, 0.0, 0.0), end=(0.1, 0.0, 0.0))
        repair = self._dimension("DIM OUT-02 Repair", start=(0.2, 0.0, 0.0), end=(0.3, 0.0, 0.0))
        live.dimension_props.measurement_state = "LIVE"
        fallback.dimension_props.measurement_state = "FALLBACK"
        repair.dimension_props.measurement_state = "NEEDS_REPAIR"
        settings = self.scene.dimensions_settings
        settings.sheet_border_enabled = True
        settings.sheet_title_block_enabled = True
        strokes, exported, skipped = vector_output_strokes(bpy.context)
        self.assertTrue(strokes)
        self.assertEqual(exported, 1)
        self.assertEqual(skipped, 2)
        document = build_scene_vector_document(bpy.context)
        self.assertEqual(document.annotation_count, 1)
        self.assertEqual(document.skipped_count, 2)

    def test_exporting_one_hundred_annotations_stays_interactive(self):
        self.camera.data.ortho_scale = 1.0
        settings = self.scene.dimensions_settings
        settings.sheet_border_enabled = True
        settings.sheet_title_block_enabled = True
        settings.sheet_drawing_title = "100 ANNOTATIONS"
        settings.sheet_drawing_number = "BENCH-100"
        settings.sheet_revision = "A"
        settings.sheet_author = "TEST"
        settings.sheet_date = "2026-08-29"
        for index in range(100):
            y = -0.45 + index * 0.009
            self._dimension(
                f"DIM OUT-02 Benchmark {index:03d}",
                start=(-0.05, y, 0.0),
                end=(0.05, y, 0.0),
            )
        with tempfile.TemporaryDirectory(prefix="dimensions-vector-benchmark-") as directory:
            filepath = Path(directory) / "hundred.svg"
            started = perf_counter()
            self.assertEqual(
                bpy.ops.dimensions.export_svg(filepath=str(filepath)),
                {"FINISHED"},
            )
            elapsed = perf_counter() - started
            root = ET.parse(filepath).getroot()
            self.assertEqual(root.tag, "{http://www.w3.org/2000/svg}svg")
            self.assertLess(elapsed, 5.0)
            print(f"OUT-05 exported 100 annotations with a drawing sheet in {elapsed:.3f} s")

    def test_sheet_populate_date_sets_today_iso_date(self):
        import datetime
        self.scene.dimensions_settings.sheet_date = "1970-01-01"
        self.assertEqual(bpy.ops.dimensions.sheet_populate_date(), {"FINISHED"})
        self.assertEqual(
            self.scene.dimensions_settings.sheet_date,
            datetime.date.today().isoformat(),
        )

    def test_sheet_sync_scale_updates_denominator_from_ortho_camera(self):
        self.camera.data.ortho_scale = 2.0
        settings = self.scene.dimensions_settings
        settings.vector_paper_size = "A4"
        settings.vector_orientation = "PORTRAIT"
        settings.sheet_border_enabled = False
        self.assertEqual(bpy.ops.dimensions.sheet_sync_scale(), {"FINISHED"})
        self.assertAlmostEqual(settings.vector_scale_denominator, 9.52, places=2)


def main():
    dimensions.register()
    try:
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(DimensionsVectorExportTests)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        return 0 if result.wasSuccessful() else 1
    finally:
        dimensions.unregister()


if __name__ == "__main__":
    sys.exit(main())
