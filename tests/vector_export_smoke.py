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
from dimensions.operators.export_vector import vector_output_strokes
from dimensions.vector_export import (
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

    def test_fallback_and_needs_repair_annotations_are_skipped(self):
        live = self._dimension("DIM OUT-02 Live", start=(-0.2, 0.0, 0.0), end=(-0.1, 0.0, 0.0))
        fallback = self._dimension("DIM OUT-02 Fallback", start=(0.0, 0.0, 0.0), end=(0.1, 0.0, 0.0))
        repair = self._dimension("DIM OUT-02 Repair", start=(0.2, 0.0, 0.0), end=(0.3, 0.0, 0.0))
        live.dimension_props.measurement_state = "LIVE"
        fallback.dimension_props.measurement_state = "FALLBACK"
        repair.dimension_props.measurement_state = "NEEDS_REPAIR"
        strokes, exported, skipped = vector_output_strokes(bpy.context)
        self.assertTrue(strokes)
        self.assertEqual(exported, 1)
        self.assertEqual(skipped, 2)

    def test_exporting_one_hundred_annotations_stays_interactive(self):
        self.camera.data.ortho_scale = 1.0
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
            print(f"OUT-02 exported 100 linear annotations to SVG in {elapsed:.3f} s")


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
