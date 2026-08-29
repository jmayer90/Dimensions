"""Focused DIM-02 circle fitting, binding, lifecycle-state, and output checks."""

import sys
import unittest
from math import cos, pi, sin
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

import dimensions
from dimensions.circle_binding import (
    bind_circle_vertices, circle_geometry, circle_value, fit_circle_world, store_circle_fit,
)
from dimensions.collections import create_dimension_object
from dimensions.constants import CURRENT_SCHEMA_VERSION
from dimensions.migrations import migrate_scene
from dimensions.output_geometry import WorldSizingPolicy, circle_dimension_output_spec
from dimensions.annotation_manager import annotation_display_value, annotation_state, sync_annotation_manager
from dimensions.manipulation import apply_circle_label_position
from dimensions.repair import repair_issues
from dimensions.operators.export_vector import vector_output_strokes


class CircleDimensionTests(unittest.TestCase):
    def setUp(self):
        self.created = []

    def tearDown(self):
        for obj in reversed(self.created):
            if bpy.data.objects.get(obj.name) is not None:
                data = obj.data
                bpy.data.objects.remove(obj, do_unlink=True)
                if data is not None and data.users == 0 and isinstance(data, bpy.types.Mesh):
                    bpy.data.meshes.remove(data)

    def _points(self, count, radius=2.5, sweep=2.0 * pi):
        rotation = Matrix.Rotation(0.67, 4, Vector((1.0, 1.0, 0.3)))
        center = Vector((3.0, -2.0, 4.0))
        return [center + rotation @ Vector((radius * cos(sweep * i / count), radius * sin(sweep * i / count), 0.0)) for i in range(count)]

    def _bound(self, points, closed=True):
        mesh = bpy.data.meshes.new("DIM-02 Circle Source")
        mesh.from_pydata(points, (), ())
        source = bpy.data.objects.new("DIM-02 Circle Source", mesh)
        bpy.context.scene.collection.objects.link(source)
        self.created.append(source)
        annotation = create_dimension_object(bpy.context, "DIM Circle")
        self.created.append(annotation)
        props = annotation.dimension_props
        props.annotation_kind = "CIRCLE"
        fit = bind_circle_vertices(props, source, range(len(points)), closed)
        store_circle_fit(props, fit)
        props.circle_label_distance = fit["radius"] * 1.35
        return annotation, source

    def test_fit_known_circles_at_multiple_segment_counts_and_arbitrary_plane(self):
        for count in (8, 16, 32, 64):
            fit = fit_circle_world(self._points(count), "FITTED", True)
            self.assertIsNotNone(fit)
            self.assertAlmostEqual(fit["radius"], 2.5, places=5)
            self.assertLess(fit["fit_error"], 1e-6)
            self.assertAlmostEqual(fit["sweep"], 2.0 * pi, places=6)

    def test_polygon_modes_report_across_flats_fit_and_corners(self):
        points = self._points(8, radius=2.5)
        fitted = fit_circle_world(points, "FITTED", True)["radius"]
        inscribed = fit_circle_world(points, "INSCRIBED", True)["radius"]
        circumscribed = fit_circle_world(points, "CIRCUMSCRIBED", True)["radius"]
        self.assertAlmostEqual(circumscribed, 2.5, places=5)
        self.assertAlmostEqual(fitted, 2.5, places=5)
        self.assertAlmostEqual(inscribed, 2.5 * cos(pi / 8.0), places=5)
        self.assertLess(inscribed, fitted)

    def test_non_circular_selection_enters_visible_fallback_warning(self):
        points = [Vector((2.0 * cos(i * pi / 8), sin(i * pi / 8), 0.0)) for i in range(16)]
        annotation, _source = self._bound(points)
        fit = circle_geometry(annotation.dimension_props)
        self.assertTrue(fit["fit_warning"])
        self.assertEqual(fit["state"], "FALLBACK")

    def test_open_arc_length_and_full_circle_length(self):
        full = fit_circle_world(self._points(32, radius=2.0), "FITTED", True)
        self.assertAlmostEqual(full["radius"] * full["sweep"], 4.0 * pi, places=5)
        short_points = [Vector((2.0 * cos(i * pi / 24), 2.0 * sin(i * pi / 24), 0.0)) for i in range(5)]
        short = fit_circle_world(short_points, "FITTED", False)
        self.assertAlmostEqual(short["sweep"], pi / 6.0, places=5)
        self.assertAlmostEqual(short["radius"] * short["sweep"], pi / 3.0, places=5)

    def test_persistent_binding_updates_live_and_retains_point_ids(self):
        annotation, source = self._bound(self._points(16, radius=1.0))
        ids = [anchor.vertex_id for anchor in annotation.dimension_props.circle_vertices]
        self.assertTrue(all(value > 0 for value in ids))
        for vertex in source.data.vertices:
            vertex.co *= 2.0
        source.data.update()
        fit = circle_geometry(annotation.dimension_props)
        self.assertAlmostEqual(fit["radius"], 2.0, places=5)
        annotation.dimension_props.circle_vertices[0].target_object = None
        annotation.dimension_props.circle_vertices[0].resolution_status = "UNRESOLVABLE"
        self.assertEqual(circle_geometry(annotation.dimension_props)["state"], "NEEDS_REPAIR")

    def test_radius_diameter_arc_labels_and_output_share_one_binding(self):
        annotation, _source = self._bound(self._points(24, radius=1.5))
        props = annotation.dimension_props
        for kind, multiplier in (("RADIUS", 1.0), ("DIAMETER", 2.0), ("ARC_LENGTH", 2.0 * pi)):
            props.circle_kind = kind
            fit = circle_geometry(props)
            self.assertAlmostEqual(circle_value(props, fit), 1.5 * multiplier, places=5)
            spec = circle_dimension_output_spec(bpy.context, annotation, f"circle-{kind}", WorldSizingPolicy(0.01, 0.1), 0.14)
            self.assertIsNotNone(spec)
            self.assertGreater(len(spec.strokes), 2)

    def test_label_handle_moves_in_fit_plane_and_capture_preserves_arc_start(self):
        annotation, _source = self._bound(self._points(16, radius=1.5), closed=False)
        props = annotation.dimension_props
        fit = circle_geometry(props)
        target = fit["center"] + fit["axis_v"] * 3.0 + fit["normal"] * 2.0
        self.assertTrue(apply_circle_label_position(annotation, fit, target))
        self.assertAlmostEqual(props.circle_label_distance, 3.0, places=5)
        self.assertAlmostEqual(props.circle_leader_angle, pi / 2.0, places=5)
        stored_start = fit["start_direction"].copy()
        store_circle_fit(props, fit)
        props.measurement_state = "CAPTURED"
        captured = circle_geometry(props)
        self.assertGreater(captured["start_direction"].dot(stored_start), 0.99999)

    def test_poor_fit_cannot_be_captured_as_authoritative(self):
        points = [Vector((2.0 * cos(i * pi / 8), sin(i * pi / 8), 0.0)) for i in range(16)]
        annotation, _source = self._bound(points)
        for selected in bpy.context.selected_objects:
            selected.select_set(False)
        annotation.select_set(True)
        bpy.context.view_layer.objects.active = annotation
        self.assertEqual(bpy.ops.dimensions.capture_circle_dimension(), {"CANCELLED"})
        self.assertNotEqual(annotation.dimension_props.measurement_state, "CAPTURED")

    def test_schema_v9_to_v10_is_additive_and_idempotent(self):
        annotation, _source = self._bound(self._points(8))
        settings = bpy.context.scene.dimensions_settings
        settings.schema_version = 9
        self.assertTrue(migrate_scene(bpy.context.scene))
        self.assertEqual(settings.schema_version, CURRENT_SCHEMA_VERSION)
        self.assertEqual(len(annotation.dimension_props.circle_vertices), 8)
        self.assertFalse(migrate_scene(bpy.context.scene))

    def test_object_mode_creation_manager_repair_and_output_integration(self):
        points = self._points(16, radius=1.0)
        mesh = bpy.data.meshes.new("DIM-02 Operator Source")
        mesh.from_pydata(points, (), ())
        source = bpy.data.objects.new("DIM-02 Operator Source", mesh)
        bpy.context.scene.collection.objects.link(source)
        self.created.append(source)
        for selected in bpy.context.selected_objects:
            selected.select_set(False)
        source.select_set(True)
        bpy.context.view_layer.objects.active = source
        before = set(bpy.data.objects)
        self.assertEqual(bpy.ops.dimensions.create_circle_dimension(circle_kind="DIAMETER"), {"FINISHED"})
        annotation = next(obj for obj in set(bpy.data.objects) - before if getattr(getattr(obj, "dimension_props", None), "enabled", False))
        self.created.append(annotation)
        sync_annotation_manager(bpy.context.scene)
        self.assertEqual(annotation_state(annotation), "LIVE")
        self.assertTrue(annotation_display_value(bpy.context.scene, annotation).startswith("⌀"))
        annotation.dimension_props.circle_vertices[0].target_object = None
        annotation.dimension_props.circle_vertices[0].resolution_status = "UNRESOLVABLE"
        issues = repair_issues(annotation)
        self.assertTrue(any(issue["anchor_name"] == "CIRCLE_0" for issue in issues))
        annotation.dimension_props.circle_vertices[0].target_object = source
        annotation.dimension_props.circle_vertices[0].resolution_status = "BY_ID"
        settings = bpy.context.scene.dimensions_settings
        settings.output_scope = "SELECTED"
        settings.output_sizing_mode = "WORLD"
        self.assertEqual(bpy.ops.dimensions.generate_output(), {"FINISHED"})
        generated = [item for item in bpy.context.scene.objects if item.get("dimensions_generated_output", False)]
        self.assertEqual(len(generated), 1)
        for item in generated:
            bpy.data.objects.remove(item, do_unlink=True)
        strokes, exported, skipped = vector_output_strokes(bpy.context)
        self.assertGreater(len(strokes), 2)
        self.assertEqual((exported, skipped), (1, 0))

    def test_edit_mode_edge_arc_selection_creates_open_arc_length(self):
        points = [(cos(index * pi / 12.0), sin(index * pi / 12.0), 0.0) for index in range(5)]
        mesh = bpy.data.meshes.new("DIM-02 Edit Arc")
        mesh.from_pydata(points, [(index, index + 1) for index in range(4)], ())
        source = bpy.data.objects.new("DIM-02 Edit Arc", mesh)
        bpy.context.scene.collection.objects.link(source)
        self.created.append(source)
        for selected in bpy.context.selected_objects:
            selected.select_set(False)
        source.select_set(True)
        bpy.context.view_layer.objects.active = source
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        before = set(bpy.data.objects)
        self.assertEqual(bpy.ops.dimensions.create_circle_dimension(circle_kind="ARC_LENGTH"), {"FINISHED"})
        bpy.ops.object.mode_set(mode="OBJECT")
        annotation = next(obj for obj in set(bpy.data.objects) - before if getattr(getattr(obj, "dimension_props", None), "enabled", False))
        self.created.append(annotation)
        self.assertFalse(annotation.dimension_props.circle_closed)
        self.assertAlmostEqual(circle_geometry(annotation.dimension_props)["sweep"], pi / 3.0, places=5)


def main():
    dimensions.register()
    try:
        result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(CircleDimensionTests))
        return 0 if result.wasSuccessful() else 1
    finally:
        dimensions.unregister()


if __name__ == "__main__":
    sys.exit(main())
