"""Named lifecycle checks for persistent Dimensions data."""

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy
from mathutils import Vector


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

import dimensions
from dimensions import migrations as migrations_module
from dimensions.anchors import dimension_source_anchors, resolve_anchor, set_anchor, set_object_anchor, set_world_anchor
from dimensions.angle_binding import set_angle_edge
from dimensions.area_binding import bind_area_face_indices
from dimensions.constants import CURRENT_SCHEMA_VERSION
from dimensions.dimension_geometry import get_dimension_world_geometry
from dimensions.construction import (
    GUIDE_PLANE_FLAG,
    construction_segment_world,
    guide_line_world,
    guide_plane_frame,
    guide_point_world,
    plane_frame,
    set_guide_line_transform,
)
from dimensions.migrations import migrate_scene, scene_has_dimensions_data
from dimensions.properties import (
    STYLE_PROPERTY_NAMES,
    is_dimension_object,
    is_guide_object,
    resolve_dimension_style,
)
from dimensions.collections import (
    GUIDE_POINT_SNAP_PROXY_FLAG,
    MEASUREMENT_SNAP_PROXY_FLAG,
    create_dimension_object,
    create_guide_object,
    create_guide_point_object,
    create_guide_plane_object,
    create_measurement_object,
    ensure_measurement_snap_proxy,
    ensure_guide_point_snap_proxy,
    get_scene_collection,
    iter_scene_role_objects,
    remove_measurement_snap_proxies,
)
from dimensions.grease_pencil_output import generate_grease_pencil_output, generated_output_objects
from dimensions.migrations import object_schema_version
from dimensions.operators.generate_output import annotation_output_key
from dimensions.projected_snap import get_projected_snap_timings
from dimensions.scene_sync import _run_scheduled_sync, scene_sync_suspended, sync_scene_objects
from dimensions.snap_targets import TARGET_IDS, enabled_snap_targets
from dimensions.viewport_state import get_state, set_state


# Saved files store an enum's item number, not its identifier, so a reordered or
# renumbered item silently changes what older files mean. Each tuple lists the
# identifiers in item-number order. annotation_kind numbers 3-6 belonged to the
# removed set, circle, coordinate, and elevation kinds that schema 16 converts, and
# must never be reused.
_END_STYLES = ("OPEN", "FILLED", "ARCHITECTURAL_TICK", "DOT", "NONE")
_UNIT_STYLES = (
    "AUTO", "METRIC_AUTO", "MILLIMETERS", "CENTIMETERS", "METERS",
    "FEET_INCHES", "INCH_DECIMAL", "INCH_FRACTION", "BLENDER",
)
_SECONDARY_UNIT_STYLES = ("NONE", *_UNIT_STYLES[1:])
_ARROW_STYLES = ("ARROW", "ARCHITECTURAL_TICK")
_TOLERANCE_MODES = ("NONE", "SYMMETRIC", "DEVIATION")
_DUAL_UNIT_ARRANGEMENTS = ("BRACKETS", "PARENTHESES", "STACKED")
_LABEL_ORIENTATIONS = ("ALIGNED", "HORIZONTAL")
_LABEL_LINE_MODES = ("ABOVE", "BROKEN")
_STYLE_ENUMS = {
    "arrow_end_style": _ARROW_STYLES,
    "start_end_style": _END_STYLES,
    "end_end_style": _END_STYLES,
    "tolerance_mode": _TOLERANCE_MODES,
    "unit_style": _UNIT_STYLES,
    "secondary_unit_style": _SECONDARY_UNIT_STYLES,
    "dual_unit_arrangement": _DUAL_UNIT_ARRANGEMENTS,
    "label_orientation": _LABEL_ORIENTATIONS,
    "label_line_mode": _LABEL_LINE_MODES,
}
PERSISTED_ENUM_ITEMS = {
    "CADDIM_PG_Anchor.anchor_type": ("VERTEX", "OBJECT_POINT", "WORLD"),
    "CADDIM_PG_Anchor.resolution_status": ("BY_ID", "BY_FALLBACK", "UNRESOLVABLE"),
    **{f"CADDIM_PG_AnnotationStyle.{name}": items for name, items in _STYLE_ENUMS.items()},
    **{f"CADDIM_PG_Dimension.{name}": items for name, items in _STYLE_ENUMS.items()},
    "CADDIM_PG_Dimension.annotation_kind": ("LINEAR", "AREA", "ANGLE"),
    "CADDIM_PG_Dimension.angle_source_mode": ("THREE_POINT", "EDGES"),
    "CADDIM_PG_Dimension.measurement_state": ("LIVE", "FALLBACK", "CAPTURED", "NEEDS_REPAIR"),
    "CADDIM_PG_Dimension.angle_mode": ("MINOR", "SUPPLEMENT", "REFLEX"),
    "CADDIM_PG_Dimension.dimension_type": ("ALIGNED", "X", "Y", "Z"),
    "CADDIM_PG_Dimension.measurement_mode": ("TRUE", "DELTA_X", "DELTA_Y", "DELTA_Z"),
    "CADDIM_PG_Dimension.custom_text_position": ("ABOVE", "BELOW"),
    "CADDIM_PG_Guide.kind": ("GUIDE", "MEASUREMENT", "POINT", "PLANE"),
    # 0.6 saved FILTERED as 0 and SELECTED as 1; 0.7 lists Selected first.
    "CADDIM_PG_SceneSettings.annotation_manager_bulk_scope": ("FILTERED", "SELECTED"),
    "CADDIM_PG_SceneSettings.unit_style": _UNIT_STYLES,
    "CADDIM_PG_SceneSettings.metric_unit_style": ("AUTO", "METRIC_AUTO", "MILLIMETERS", "CENTIMETERS", "METERS", "BLENDER"),
    "CADDIM_PG_SceneSettings.imperial_unit_style": ("AUTO", "FEET_INCHES", "INCH_DECIMAL", "INCH_FRACTION", "BLENDER"),
    "CADDIM_PG_SceneSettings.imperial_denominator": ("2", "4", "8", "16", "32", "64"),
    "CADDIM_PG_SceneSettings.dimension_arrow_end_style": _ARROW_STYLES,
    "CADDIM_PG_SceneSettings.dimension_start_end_style": _END_STYLES,
    "CADDIM_PG_SceneSettings.dimension_end_end_style": _END_STYLES,
    "CADDIM_PG_SceneSettings.dimension_secondary_unit_style": _SECONDARY_UNIT_STYLES,
    "CADDIM_PG_SceneSettings.dimension_dual_unit_arrangement": _DUAL_UNIT_ARRANGEMENTS,
    "CADDIM_PG_SceneSettings.dimension_label_orientation": _LABEL_ORIENTATIONS,
    "CADDIM_PG_SceneSettings.dimension_label_line_mode": _LABEL_LINE_MODES,
    "CADDIM_PG_SceneSettings.output_sizing_mode": ("CAMERA", "WORLD"),
    "CADDIM_PG_SceneSettings.output_scope": ("SELECTED", "VISIBLE"),
    "CADDIM_PG_SceneSettings.vector_paper_size": ("A4", "A3", "LETTER"),
    "CADDIM_PG_SceneSettings.vector_orientation": ("PORTRAIT", "LANDSCAPE"),
    "CADDIM_PG_SceneSettings.text_placement": ("INLINE", "ABOVE", "OUTSIDE", "OUTSIDE_START"),
    "CADDIM_PG_SceneSettings.hud_corner": ("BOTTOM_LEFT", "BOTTOM_RIGHT", "TOP_LEFT", "TOP_RIGHT"),
}


class DimensionsLifecycleTests(unittest.TestCase):
    def setUp(self):
        dimensions.register()
        self.measurement = create_measurement_object(
            bpy.context,
            f"Dimensions Lifecycle Measurement {self._testMethodName}",
        )
        self.measurement_name = self.measurement.name
        set_world_anchor(self.measurement.guide_props.start, Vector((1.0, 2.0, 3.0)))
        set_world_anchor(self.measurement.guide_props.end, Vector((5.0, 2.0, 3.0)))

    def tearDown(self):
        measurement = bpy.data.objects.get(self.measurement_name)
        if measurement is not None:
            bpy.data.objects.remove(measurement, do_unlink=True)

    @classmethod
    def tearDownClass(cls):
        dimensions.unregister()

    def test_measurement_proxy_contains_both_endpoints(self):
        proxy = ensure_measurement_snap_proxy(self.measurement, bpy.context.scene)
        self.assertIsNotNone(proxy)
        self.assertEqual(len(proxy.data.vertices), 2)
        points = [proxy.matrix_world @ vertex.co for vertex in proxy.data.vertices]
        self.assertEqual(points, [Vector((1.0, 2.0, 3.0)), Vector((5.0, 2.0, 3.0))])

    def test_proxy_cleanup_removes_duplicate_children(self):
        invalid_proxy = bpy.data.objects.new("Invalid Dimensions Proxy", None)
        bpy.context.scene.collection.objects.link(invalid_proxy)
        invalid_proxy.parent = self.measurement
        invalid_proxy[MEASUREMENT_SNAP_PROXY_FLAG] = True
        ensure_measurement_snap_proxy(self.measurement, bpy.context.scene)
        proxies = [
            child for child in self.measurement.children
            if child.get(MEASUREMENT_SNAP_PROXY_FLAG, False)
        ]
        self.assertEqual(len(proxies), 1)

    def test_proxy_visibility_follows_measurement_visibility(self):
        self.measurement.guide_props.visible = False
        proxy = ensure_measurement_snap_proxy(self.measurement, bpy.context.scene)
        self.assertTrue(proxy.hide_get() or proxy.hide_viewport)

    def test_sync_repairs_missing_measurement_proxy(self):
        remove_measurement_snap_proxies(self.measurement)
        sync_scene_objects(bpy.context.scene)
        self.assertTrue(any(
            child.get(MEASUREMENT_SNAP_PROXY_FLAG, False)
            for child in self.measurement.children
        ))

    def test_undo_redo_lifecycle_clears_transient_viewport_state(self):
        set_state("DIMENSION", {"test": "undo"})
        from dimensions.scene_sync import _undo_redo_handler

        # Blender documents this callback argument as a dummy value, not a scene.
        _undo_redo_handler(None)
        self.assertIsNone(get_state("DIMENSION"))
        self.assertEqual(get_projected_snap_timings(), {})

    def test_save_reload_preserves_measurement_and_proxy(self):
        ensure_measurement_snap_proxy(self.measurement, bpy.context.scene)
        with tempfile.TemporaryDirectory() as directory:
            filepath = Path(directory) / "dimensions-lifecycle.blend"
            bpy.ops.wm.save_as_mainfile(filepath=str(filepath), check_existing=False)
            from dimensions.viewport_state import _states

            _states["DIMENSION"][(11, 22, 33)] = {"state": "STALE_PREVIEW"}
            bpy.ops.wm.open_mainfile(filepath=str(filepath), load_ui=False)
            self.assertNotIn((11, 22, 33), _states["DIMENSION"])
            measurement = bpy.data.objects.get(self.measurement_name)
            self.assertIsNotNone(measurement)
            sync_scene_objects(bpy.context.scene)
            self.assertTrue(any(
                child.get(MEASUREMENT_SNAP_PROXY_FLAG, False)
                for child in measurement.children
            ))

    def test_save_reload_preserves_scene_snap_target_override(self):
        settings = bpy.context.scene.dimensions_settings
        settings.use_snap_target_override = True
        for identifier in TARGET_IDS:
            setattr(settings, f"snap_{identifier}", identifier == "measurement_endpoint")
        self.assertEqual(enabled_snap_targets(bpy.context), {"measurement_endpoint"})

        with tempfile.TemporaryDirectory() as directory:
            filepath = Path(directory) / "dimensions-snap-targets.blend"
            bpy.ops.wm.save_as_mainfile(filepath=str(filepath), check_existing=False)
            bpy.ops.wm.open_mainfile(filepath=str(filepath), load_ui=False)
            settings = bpy.context.scene.dimensions_settings
            self.assertTrue(settings.use_snap_target_override)
            self.assertEqual(enabled_snap_targets(bpy.context), {"measurement_endpoint"})

    def test_save_reload_preserves_sheet_layout_settings(self):
        settings = bpy.context.scene.dimensions_settings
        settings.sheet_border_enabled = True
        settings.sheet_title_block_enabled = True
        settings.sheet_margin_mm = 12.5
        settings.sheet_title_block_width_mm = 92.0
        settings.sheet_title_block_height_mm = 34.0
        settings.sheet_drawing_title = "North Elevation"
        settings.sheet_drawing_number = "A-201"
        settings.sheet_revision = "B"
        settings.sheet_author = "Ada Lovelace"
        settings.sheet_date = "2026-08-29"

        with tempfile.TemporaryDirectory() as directory:
            filepath = Path(directory) / "dimensions-sheet-layout.blend"
            bpy.ops.wm.save_as_mainfile(filepath=str(filepath), check_existing=False)
            bpy.ops.wm.open_mainfile(filepath=str(filepath), load_ui=False)
            restored = bpy.context.scene.dimensions_settings
            self.assertEqual(restored.schema_version, CURRENT_SCHEMA_VERSION)
            self.assertTrue(restored.sheet_border_enabled)
            self.assertTrue(restored.sheet_title_block_enabled)
            self.assertAlmostEqual(restored.sheet_margin_mm, 12.5)
            self.assertAlmostEqual(restored.sheet_title_block_width_mm, 92.0)
            self.assertAlmostEqual(restored.sheet_title_block_height_mm, 34.0)
            self.assertEqual(restored.sheet_drawing_title, "North Elevation")
            self.assertEqual(restored.sheet_drawing_number, "A-201")
            self.assertEqual(restored.sheet_revision, "B")
            self.assertEqual(restored.sheet_author, "Ada Lovelace")
            self.assertEqual(restored.sheet_date, "2026-08-29")

    def test_save_reload_preserves_moved_guide_plane_grid(self):
        frame = plane_frame((1.0, 2.0, 3.0), (0.0, 1.0, 1.0), (1.0, 0.0, 0.0))
        plane = create_guide_plane_object(bpy.context, frame, 1.5, 0.5, "Dimensions Lifecycle Plane")
        plane_name = plane.name
        plane.location.x += 2.0
        bpy.context.view_layer.update()
        sync_scene_objects(bpy.context.scene)
        self.assertAlmostEqual(plane.location.x, 3.0)
        expected_matrix = plane.matrix_world.copy()
        with tempfile.TemporaryDirectory() as directory:
            filepath = Path(directory) / "dimensions-guide-plane.blend"
            bpy.ops.wm.save_as_mainfile(filepath=str(filepath), check_existing=False)
            bpy.ops.wm.open_mainfile(filepath=str(filepath), load_ui=False)
            restored = bpy.data.objects.get(plane_name)
            self.assertIsNotNone(restored)
            self.assertEqual(restored.type, "MESH")
            self.assertTrue(restored.get(GUIDE_PLANE_FLAG))
            self.assertEqual(restored.guide_props.kind, "PLANE")
            self.assertAlmostEqual(restored.guide_props.plane_extent, 1.5)
            self.assertAlmostEqual(restored.guide_props.plane_spacing, 0.5)
            self.assertEqual(len(restored.data.vertices), 49)
            for restored_row, expected_row in zip(restored.matrix_world, expected_matrix):
                for restored_value, expected_value in zip(restored_row, expected_row):
                    self.assertAlmostEqual(restored_value, expected_value, places=5)

    def test_save_reload_preserves_moved_guide_point_and_proxy(self):
        point = create_guide_point_object(
            bpy.context, "Dimensions Lifecycle Guide Point", location=Vector((2.0, 3.0, 4.0)),
        )
        ensure_guide_point_snap_proxy(point, bpy.context.scene)
        point.location = (5.0, 6.0, 7.0)
        sync_scene_objects(bpy.context.scene)
        self.assertEqual(Vector(point.location), Vector((5.0, 6.0, 7.0)))
        point_name = point.name
        with tempfile.TemporaryDirectory() as directory:
            filepath = Path(directory) / "dimensions-guide-point-lifecycle.blend"
            bpy.ops.wm.save_as_mainfile(filepath=str(filepath), check_existing=False)
            bpy.ops.wm.open_mainfile(filepath=str(filepath), load_ui=False)
            restored = bpy.data.objects.get(point_name)
            self.assertIsNotNone(restored)
            self.assertEqual(restored.guide_props.kind, "POINT")
            self.assertEqual(guide_point_world(restored), Vector((5.0, 6.0, 7.0)))
            sync_scene_objects(bpy.context.scene)
            proxy = next(child for child in restored.children if child.get(GUIDE_POINT_SNAP_PROXY_FLAG, False))
            self.assertLess((proxy.matrix_world @ proxy.data.vertices[0].co - Vector((5.0, 6.0, 7.0))).length, 1e-6)

    def test_moved_and_rotated_guide_line_keeps_its_transform(self):
        guide = create_guide_object(bpy.context, "Dimensions Lifecycle Guide Line")
        set_guide_line_transform(guide, Vector((0.0, 0.0, 0.0)), Vector((1.0, 0.0, 0.0)))
        guide.location = (0.0, 4.0, 0.0)
        guide.rotation_euler = (0.0, 0.0, 1.5707963267948966)
        bpy.context.view_layer.update()
        sync_scene_objects(bpy.context.scene)
        origin, direction = guide_line_world(guide)
        self.assertLess((origin - Vector((0.0, 4.0, 0.0))).length, 1e-6)
        self.assertLess((direction - Vector((0.0, 1.0, 0.0))).length, 1e-6)
        bpy.data.objects.remove(guide, do_unlink=True)

    def test_dimensions_snapped_to_guides_follow_them_through_save_and_reload(self):
        from dimensions.anchors import resolve_anchor, set_anchor_from_snap

        point = create_guide_point_object(
            bpy.context, "Dimensions Lifecycle Followed Point", location=Vector((1.0, 0.0, 0.0)),
        )
        line = create_guide_object(bpy.context, "Dimensions Lifecycle Followed Line")
        set_guide_line_transform(line, Vector((0.0, 2.0, 0.0)), Vector((1.0, 0.0, 0.0)))
        bpy.context.view_layer.update()
        dimension = create_dimension_object(bpy.context, "Dimensions Lifecycle Followed Dimension")
        props = dimension.dimension_props
        set_anchor_from_snap(props.start, {
            "type": "GUIDE_POINT", "object": None, "guide_object": point,
            "world_co": Vector((1.0, 0.0, 0.0)), "screen_co": Vector(),
        })
        set_anchor_from_snap(props.end, {
            "type": "GUIDE", "object": None, "guide_object": line,
            "world_co": Vector((3.0, 2.0, 0.0)), "screen_co": Vector(),
        })
        point.location = (1.0, 0.0, 5.0)
        line.location = (0.0, 2.0, 5.0)
        bpy.context.view_layer.update()
        sync_scene_objects(bpy.context.scene)
        self.assertLess((resolve_anchor(props.start) - Vector((1.0, 0.0, 5.0))).length, 1e-6)
        self.assertLess((resolve_anchor(props.end) - Vector((3.0, 2.0, 5.0))).length, 1e-6)
        self.assertEqual(props.measurement_state, "LIVE")

        names = (point.name, line.name, dimension.name)
        with tempfile.TemporaryDirectory() as directory:
            filepath = Path(directory) / "dimensions-followed-guides.blend"
            bpy.ops.wm.save_as_mainfile(filepath=str(filepath), check_existing=False)
            bpy.ops.wm.open_mainfile(filepath=str(filepath), load_ui=False)
            point, line, dimension = (bpy.data.objects[name] for name in names)
            point.location.z = 9.0
            bpy.context.view_layer.update()
            sync_scene_objects(bpy.context.scene)
            props = dimension.dimension_props
            self.assertLess((resolve_anchor(props.start) - Vector((1.0, 0.0, 9.0))).length, 1e-6)

            # Clearing guides keeps dependent dimensions where they are instead of breaking them.
            with bpy.context.temp_override(scene=bpy.context.scene):
                bpy.ops.dimensions.clear_guides()
            sync_scene_objects(bpy.context.scene)
            self.assertEqual((props.start.anchor_type, props.end.anchor_type), ("WORLD", "WORLD"))
            self.assertLess((resolve_anchor(props.start) - Vector((1.0, 0.0, 9.0))).length, 1e-6)
            self.assertLess((resolve_anchor(props.end) - Vector((3.0, 2.0, 5.0))).length, 1e-6)
            self.assertEqual(props.measurement_state, "LIVE")
            bpy.data.objects.remove(dimension, do_unlink=True)

    def test_save_reload_preserves_scene_owned_output_identity(self):
        dimension = create_dimension_object(
            bpy.context,
            "Dimensions Lifecycle Output Identity",
        )
        dimension_name = dimension.name
        set_world_anchor(dimension.dimension_props.start, Vector((0.0, 0.0, 0.0)))
        set_world_anchor(dimension.dimension_props.end, Vector((2.0, 0.0, 0.0)))
        source_key = annotation_output_key(bpy.context.scene, dimension)
        self.assertIsNone(dimension.get("dimensions_annotation_output_key"))

        with tempfile.TemporaryDirectory() as directory:
            filepath = Path(directory) / "dimensions-output-identity.blend"
            bpy.ops.wm.save_as_mainfile(filepath=str(filepath), check_existing=False)
            bpy.ops.wm.open_mainfile(filepath=str(filepath), load_ui=False)
            reloaded = bpy.data.objects.get(dimension_name)
            self.assertIsNotNone(reloaded)
            self.assertEqual(
                annotation_output_key(bpy.context.scene, reloaded),
                source_key,
            )
            bpy.data.objects.remove(reloaded, do_unlink=True)


class DimensionsLifecycleMatrixTests(unittest.TestCase):
    def setUp(self):
        dimensions.register()
        self.previous_scene_name = bpy.context.window.scene.name
        self.scene = bpy.data.scenes.new(f"Dimensions Matrix {self._testMethodName}")
        self.scene_name = self.scene.name
        bpy.context.window.scene = self.scene

    def tearDown(self):
        previous_scene = bpy.data.scenes.get(self.previous_scene_name)
        if previous_scene is not None:
            bpy.context.window.scene = previous_scene
        elif len(bpy.data.scenes):
            bpy.context.window.scene = bpy.data.scenes[0]
        scene = bpy.data.scenes.get(self.scene_name)
        if scene is not None:
            bpy.data.scenes.remove(scene)

    @classmethod
    def tearDownClass(cls):
        dimensions.unregister()

    def test_sheet_settings_are_isolated_between_scenes(self):
        primary = self.scene.dimensions_settings
        primary.sheet_border_enabled = True
        primary.sheet_drawing_title = "PRIMARY"

        secondary_scene = bpy.data.scenes.new("Dimensions Secondary Sheet")
        try:
            secondary = secondary_scene.dimensions_settings
            self.assertFalse(secondary.sheet_border_enabled)
            self.assertEqual(secondary.sheet_drawing_title, "")
            secondary.sheet_title_block_enabled = True
            secondary.sheet_drawing_title = "SECONDARY"
            self.assertTrue(primary.sheet_border_enabled)
            self.assertFalse(primary.sheet_title_block_enabled)
            self.assertEqual(primary.sheet_drawing_title, "PRIMARY")
            self.assertEqual(secondary.sheet_drawing_title, "SECONDARY")
        finally:
            bpy.data.scenes.remove(secondary_scene)

    def _source_mesh(self, name="Lifecycle Source"):
        mesh = bpy.data.meshes.new(f"{name} Mesh")
        mesh.from_pydata(
            [(0.0, 0.0, 0.0), (2.0, 0.0, 0.0), (0.0, 2.0, 0.0)],
            [(0, 1), (0, 2), (1, 2)],
            [(0, 1, 2)],
        )
        obj = bpy.data.objects.new(name, mesh)
        self.scene.collection.objects.link(obj)
        return obj

    def _persistent_objects(self):
        source = self._source_mesh()

        linear = create_dimension_object(bpy.context, "Lifecycle Linear")
        set_anchor(linear.dimension_props.start, source, 0)
        set_anchor(linear.dimension_props.end, source, 1)

        angle = create_dimension_object(bpy.context, "Lifecycle Angle")
        angle.dimension_props.annotation_kind = "ANGLE"
        angle.dimension_props.angle_source_mode = "EDGES"
        set_angle_edge(angle.dimension_props, "A", source, (0, 1))
        set_angle_edge(angle.dimension_props, "B", source, (0, 2))

        area = create_dimension_object(bpy.context, "Lifecycle Area")
        area.dimension_props.annotation_kind = "AREA"
        result = bind_area_face_indices(area.dimension_props, source, [0])
        self.assertIsNotNone(result)
        set_object_anchor(area.dimension_props.start, source, result["center"])
        set_object_anchor(
            area.dimension_props.end,
            source,
            result["center"] + Vector((1.0, 0.0, 0.0)),
        )

        guide = create_guide_object(bpy.context, "Lifecycle Guide")
        set_anchor(guide.guide_props.start, source, 0)
        set_anchor(guide.guide_props.end, source, 2)

        measurement = create_measurement_object(bpy.context, "Lifecycle Measurement")
        set_world_anchor(measurement.guide_props.start, Vector((0.0, 0.0, 0.0)))
        set_world_anchor(measurement.guide_props.end, Vector((3.0, 0.0, 0.0)))
        proxy = ensure_measurement_snap_proxy(measurement, self.scene)
        self.assertIsNotNone(proxy)
        sync_scene_objects(self.scene)
        return source, linear, angle, area, guide, measurement, proxy

    def test_duplicate_annotations_share_sources_and_measurements_get_independent_proxies(self):
        source, linear, angle, area, guide, measurement, original_proxy = self._persistent_objects()
        duplicates = []
        for original in (linear, angle, area, guide, measurement):
            duplicate = original.copy()
            original.users_collection[0].objects.link(duplicate)
            duplicates.append(duplicate)
        sync_scene_objects(self.scene)

        linear_copy, angle_copy, area_copy, guide_copy, measurement_copy = duplicates
        self.assertEqual(linear_copy.dimension_props.start.target_object, source)
        self.assertEqual(angle_copy.dimension_props.angle_a_start.target_object, source)
        self.assertEqual(area_copy.dimension_props.area_source_object, source)
        self.assertEqual(guide_copy.guide_props.start.target_object, source)
        copied_proxies = [
            child for child in measurement_copy.children
            if child.get(MEASUREMENT_SNAP_PROXY_FLAG, False)
        ]
        self.assertEqual(len(copied_proxies), 1)
        self.assertNotEqual(copied_proxies[0], original_proxy)

    def test_deleting_sources_and_annotations_produces_repair_or_cleanup(self):
        source, linear, angle, area, guide, measurement, proxy = self._persistent_objects()
        source_name = source.name
        bpy.data.objects.remove(source, do_unlink=True)
        sync_scene_objects(self.scene)

        self.assertNotIn(source_name, bpy.data.objects)
        self.assertEqual(linear.dimension_props.measurement_state, "NEEDS_REPAIR")
        self.assertEqual(angle.dimension_props.measurement_state, "NEEDS_REPAIR")
        self.assertEqual(area.dimension_props.measurement_state, "NEEDS_REPAIR")
        self.assertEqual(resolve_anchor(guide.guide_props.start), Vector((0.0, 0.0, 0.0)))

        proxy_name = proxy.name
        bpy.data.objects.remove(measurement, do_unlink=True)
        sync_scene_objects(self.scene)
        self.assertNotIn(proxy_name, bpy.data.objects)

    def test_actual_undo_redo_restores_data_and_clears_pointer_caches(self):
        from dimensions import drawing, projected_snap, volume
        from dimensions.viewport_state import _states

        bpy.ops.ed.undo_push(message="Lifecycle baseline")
        source, linear, _angle, _area, _guide, measurement, proxy = self._persistent_objects()
        names = (source.name, linear.name, measurement.name, proxy.name)
        vertex_attribute = source.data.attributes.get("dimensions_anchor_id")
        self.assertIsNotNone(vertex_attribute)
        bpy.ops.ed.undo_push(message="Lifecycle objects created")

        projected_snap._viewport_caches[(1, 2, 3)] = {"stale": True}
        volume._volume_cache[(1, 2)] = (1.0, "EXACT")
        drawing._dimension_geometry_cache[(1, 2, 3)] = {"stale": True}
        _states["DIMENSION"][(1, 2, 3)] = {"stale": True}
        bpy.data.objects.remove(source, do_unlink=True)
        bpy.data.objects.remove(measurement, do_unlink=True)
        bpy.ops.ed.undo_push(message="Lifecycle sources deleted")

        self.assertEqual(bpy.ops.ed.undo(), {"FINISHED"})
        self.scene = bpy.data.scenes.get(self.scene_name)
        self.assertIsNotNone(self.scene)
        restored_source = bpy.data.objects.get(names[0])
        restored_measurement = bpy.data.objects.get(names[2])
        self.assertIsNotNone(restored_source)
        self.assertIsNotNone(restored_measurement)
        self.assertIsNotNone(restored_source.data.attributes.get("dimensions_anchor_id"))
        sync_scene_objects(self.scene)
        self.assertTrue(any(
            child.get(MEASUREMENT_SNAP_PROXY_FLAG, False)
            for child in restored_measurement.children
        ))
        self.assertFalse(projected_snap._viewport_caches)
        self.assertFalse(volume._volume_cache)
        self.assertFalse(drawing._dimension_geometry_cache)
        self.assertFalse(any(_states.values()))

        self.assertEqual(bpy.ops.ed.redo(), {"FINISHED"})
        self.scene = bpy.data.scenes.get(self.scene_name)
        self.assertIsNotNone(self.scene)
        self.assertIsNone(bpy.data.objects.get(names[0]))
        self.assertIsNone(bpy.data.objects.get(names[2]))
        restored_linear = bpy.data.objects.get(names[1])
        sync_scene_objects(self.scene)
        self.assertEqual(restored_linear.dimension_props.measurement_state, "NEEDS_REPAIR")

        self.assertEqual(bpy.ops.ed.undo(), {"FINISHED"})
        self.assertEqual(bpy.ops.ed.undo(), {"FINISHED"})
        self.scene = bpy.data.scenes.get(self.scene_name)
        self.assertIsNone(bpy.data.objects.get(names[1]))

    def test_scene_copy_and_move_remain_scene_owned(self):
        source, linear, _angle, _area, guide, _measurement, _proxy = self._persistent_objects()
        other_scene = bpy.data.scenes.new("Dimensions Matrix Other Scene")
        self.addCleanup(bpy.data.scenes.remove, other_scene)
        other_context = type("SceneContext", (), {
            "scene": other_scene,
            "preferences": bpy.context.preferences,
        })()
        other_collection = create_dimension_object(other_context, "Other Scene Dimension").users_collection[0]
        copied = linear.copy()
        other_collection.objects.link(copied)

        other_guide_collection = create_guide_object(other_context, "Other Scene Guide").users_collection[0]
        for collection in list(guide.users_collection):
            collection.objects.unlink(guide)
        other_guide_collection.objects.link(guide)
        _run_scheduled_sync()

        first_dimensions = get_scene_collection(self.scene, "DIMENSIONS")
        second_dimensions = get_scene_collection(other_scene, "DIMENSIONS")
        self.assertNotEqual(first_dimensions, second_dimensions)
        self.assertIn(linear, first_dimensions.objects[:])
        self.assertNotIn(linear, second_dimensions.objects[:])
        self.assertIn(copied, second_dimensions.objects[:])
        self.assertNotIn(guide, self.scene.objects[:])
        self.assertIn(guide, other_scene.objects[:])
        self.assertEqual(copied.dimension_props.start.target_object, source)

    def test_append_and_link_preserve_data_and_keep_linked_objects_read_only(self):
        from dimensions import drawing
        from dimensions.properties import is_read_only_dimensions_object

        source, *_objects = self._persistent_objects()
        dimension_collection = get_scene_collection(self.scene, "DIMENSIONS")
        guide_collection = get_scene_collection(self.scene, "GUIDES")
        source_collection = bpy.data.collections.new("Lifecycle Sources")
        self.scene.collection.children.link(source_collection)
        for collection in list(source.users_collection):
            collection.objects.unlink(source)
        source_collection.objects.link(source)

        with tempfile.TemporaryDirectory() as directory:
            filepath = Path(directory) / "dimensions-lifecycle-library.blend"
            bpy.data.libraries.write(
                str(filepath),
                {dimension_collection, guide_collection, source_collection},
            )
            collection_names = (
                dimension_collection.name,
                guide_collection.name,
                source_collection.name,
            )

            appended_scene = bpy.data.scenes.new("Dimensions Appended Scene")
            linked_scene = bpy.data.scenes.new("Dimensions Linked Scene")
            self.addCleanup(bpy.data.scenes.remove, appended_scene)
            self.addCleanup(bpy.data.scenes.remove, linked_scene)

            with bpy.data.libraries.load(str(filepath), link=False) as (data_from, data_to):
                self.assertTrue(set(collection_names).issubset(data_from.collections))
                data_to.collections = list(collection_names)
            appended_collections = tuple(data_to.collections)
            for collection in appended_collections:
                appended_scene.collection.children.link(collection)
            appended_scene.dimensions_settings.schema_version = 0
            sync_scene_objects(appended_scene)
            self.assertEqual(
                appended_scene.dimensions_settings.schema_version,
                CURRENT_SCHEMA_VERSION,
            )
            appended_dimensions = [
                obj for obj in appended_scene.objects
                if getattr(getattr(obj, "dimension_props", None), "enabled", False)
            ]
            self.assertEqual(len(appended_dimensions), 3)
            self.assertTrue(all(obj.library is None for obj in appended_dimensions))

            with bpy.data.libraries.load(str(filepath), link=True) as (_data_from, data_to):
                data_to.collections = list(collection_names)
            linked_collections = tuple(data_to.collections)
            for collection in linked_collections:
                linked_scene.collection.children.link(collection)
            linked_dimensions = [
                obj for obj in linked_scene.objects
                if getattr(getattr(obj, "dimension_props", None), "enabled", False)
            ]
            self.assertEqual(len(linked_dimensions), 3)
            before = [(obj.name, tuple(obj.location), obj.dimension_props.measurement_state) for obj in linked_dimensions]
            linked_scene.dimensions_settings.schema_version = 0
            with patch.object(
                migrations_module, "migrate_anchor_identity",
                side_effect=AssertionError("linked anchor must remain read-only"),
            ):
                sync_scene_objects(linked_scene)
            self.assertEqual(linked_scene.dimensions_settings.schema_version, CURRENT_SCHEMA_VERSION)
            after = [(obj.name, tuple(obj.location), obj.dimension_props.measurement_state) for obj in linked_dimensions]
            self.assertEqual(after, before)
            self.assertTrue(all(is_read_only_dimensions_object(obj) for obj in linked_dimensions))

            linked_mesh = next(
                obj for obj in linked_scene.objects if obj.type == "MESH" and obj.library is not None
            )
            attributes_before = tuple(linked_mesh.data.attributes.keys())
            original_scene = bpy.context.window.scene
            bpy.context.window.scene = linked_scene
            try:
                local_annotation = create_dimension_object(bpy.context, "Local With Linked Source")
                local_anchor = local_annotation.dimension_props.start
                local_anchor.target_object = linked_mesh
                local_anchor.anchor_type = "VERTEX"
                local_anchor.vertex_index = 0
                local_anchor.vertex_id = 0
                linked_scene.dimensions_settings.schema_version = 0
                self.assertTrue(migrate_scene(linked_scene))
                self.assertEqual(local_anchor.vertex_id, 0)
                self.assertEqual(tuple(linked_mesh.data.attributes.keys()), attributes_before)
                self.assertIsNone(get_scene_collection(linked_scene, "DIMENSIONS").library)
                visible_dimensions = tuple(iter_scene_role_objects(linked_scene, "DIMENSIONS"))
                self.assertIn(local_annotation, visible_dimensions)
                self.assertTrue(all(obj in visible_dimensions for obj in linked_dimensions))
            finally:
                bpy.context.window.scene = original_scene

            linked_name = linked_dimensions[0].name
            active_scene = bpy.context.window.scene
            bpy.context.window.scene = linked_scene
            try:
                self.assertEqual(
                    bpy.ops.dimensions.manager_rename(
                        object_name=linked_name,
                        name="Must Not Rename Linked",
                    ),
                    {"CANCELLED"},
                )
                self.assertEqual(
                    bpy.ops.dimensions.manager_delete(object_name=linked_name),
                    {"CANCELLED"},
                )
            finally:
                bpy.context.window.scene = active_scene
            self.assertIsNotNone(linked_scene.objects.get(linked_name))

            linked_area = next(
                obj for obj in linked_dimensions
                if obj.dimension_props.annotation_kind == "AREA"
            )
            area_before = (
                linked_area.dimension_props.area_value,
                linked_area.dimension_props.area_face_count,
                linked_area.dimension_props.measurement_state,
            )
            with patch.object(
                drawing,
                "_project_world_to_screen",
                side_effect=lambda _context, world: Vector((world.x, world.y)),
            ):
                geometry = drawing._build_area_geometry(
                    SimpleNamespace(scene=linked_scene),
                    linked_area.dimension_props,
                )
            self.assertIsNotNone(geometry)
            self.assertEqual(
                (
                    linked_area.dimension_props.area_value,
                    linked_area.dimension_props.area_face_count,
                    linked_area.dimension_props.measurement_state,
                ),
                area_before,
            )

            override = linked_dimensions[0].override_hierarchy_create(
                linked_scene,
                linked_scene.view_layers[0],
                do_fully_editable=True,
            )
            self.assertIsNotNone(override)
            self.assertIsNotNone(override.override_library)
            self.assertTrue(is_read_only_dimensions_object(override))
            override_before = (tuple(override.location), override.dimension_props.measurement_state)
            sync_scene_objects(linked_scene)
            self.assertEqual(
                (tuple(override.location), override.dimension_props.measurement_state),
                override_before,
            )
            override_name = override.name
            active_scene = bpy.context.window.scene
            bpy.context.window.scene = linked_scene
            try:
                self.assertEqual(
                    bpy.ops.dimensions.manager_rename(
                        object_name=override_name,
                        name="Must Not Rename Override",
                    ),
                    {"CANCELLED"},
                )
                self.assertEqual(
                    bpy.ops.dimensions.manager_delete(object_name=override_name),
                    {"CANCELLED"},
                )
            finally:
                bpy.context.window.scene = active_scene
            self.assertIsNotNone(linked_scene.objects.get(override_name))


class DimensionsReleasedFileTests(unittest.TestCase):
    """Migration against a real file saved by an earlier release.

    ``tests/fixtures/schema-v0.blend`` was written before schema stamping existed: its
    vertex anchors carry no durable point IDs and its scene carries no stamp. The
    0.3.2 fixture represents schema v1 before output settings were introduced.
    Schema changes add fixtures here so migrations are tested against files that
    actually shipped, not only synthetic data. The schema-v2 0.4.0 fixture verifies
    the sequential snap-target and named-style migrations in the 0.4.2 release.
    """

    FIXTURE = REPOSITORY_ROOT / "tests" / "fixtures" / "schema-v0.blend"
    OUTPUT_FIXTURE = REPOSITORY_ROOT / "tests" / "fixtures" / "schema-v1-0.3.2.blend"
    SCHEMA_V2_FIXTURE = REPOSITORY_ROOT / "tests" / "fixtures" / "schema-v2-0.4.0.blend"
    SCHEMA_V14_FIXTURE = REPOSITORY_ROOT / "tests" / "fixtures" / "schema-v14-0.5.0.blend"
    SCHEMA_V15_FIXTURE = REPOSITORY_ROOT / "tests" / "fixtures" / "schema-v15-0.6.0.blend"
    SETTINGS_ONLY_FIXTURE = REPOSITORY_ROOT / "tests" / "fixtures" / "schema-v6-settings-only-0.4.2.blend"

    def setUp(self):
        dimensions.register()

    def test_the_fixture_is_present(self):
        self.assertTrue(self.FIXTURE.is_file(), f"missing fixture: {self.FIXTURE}")
        self.assertTrue(self.OUTPUT_FIXTURE.is_file(), f"missing fixture: {self.OUTPUT_FIXTURE}")
        self.assertTrue(self.SCHEMA_V2_FIXTURE.is_file(), f"missing fixture: {self.SCHEMA_V2_FIXTURE}")
        self.assertTrue(self.SCHEMA_V14_FIXTURE.is_file(), f"missing fixture: {self.SCHEMA_V14_FIXTURE}")
        self.assertTrue(self.SCHEMA_V15_FIXTURE.is_file(), f"missing fixture: {self.SCHEMA_V15_FIXTURE}")
        self.assertTrue(self.SETTINGS_ONLY_FIXTURE.is_file(), f"missing fixture: {self.SETTINGS_ONLY_FIXTURE}")

    def test_settings_only_released_file_migrates_before_first_annotation(self):
        load_handlers = bpy.app.handlers.load_post
        migration_handler = migrations_module._load_post_handler
        handler_was_registered = migration_handler in load_handlers
        if handler_was_registered:
            load_handlers.remove(migration_handler)
        try:
            bpy.ops.wm.open_mainfile(filepath=str(self.SETTINGS_ONLY_FIXTURE), load_ui=False)
        finally:
            if handler_was_registered and migration_handler not in load_handlers:
                load_handlers.append(migration_handler)

        scene = bpy.context.scene
        settings = scene.dimensions_settings
        self.assertFalse(any(obj.dimension_props.enabled for obj in scene.objects))
        self.assertTrue(scene_has_dimensions_data(scene))
        self.assertEqual(settings.schema_version, 6)
        self.assertEqual(settings.precision, 4)
        self.assertEqual(settings.output_scope, "SELECTED")
        self.assertEqual(settings.annotation_styles[0].name, "Legacy Settings Style")

        calls = []
        originals = migrations_module._MIGRATIONS
        wrappers = {
            version: (lambda current, migration: lambda value: (
                calls.append(current), migration(value)
            )[1])(version, originals[version])
            for version in range(6, CURRENT_SCHEMA_VERSION)
        }
        with patch.dict(originals, wrappers):
            created = create_dimension_object(bpy.context, "First Annotation After Migration")
            self.assertEqual(calls, list(range(6, CURRENT_SCHEMA_VERSION)))
            self.assertEqual(settings.schema_version, CURRENT_SCHEMA_VERSION)
            self.assertFalse(migrate_scene(scene))
        self.assertTrue(created.dimension_props.enabled)
        self.assertEqual(settings.precision, 4)
        self.assertEqual(settings.output_scope, "SELECTED")
        self.assertEqual(settings.annotation_styles[0].name, "Legacy Settings Style")

    def test_first_annotation_in_fresh_scene_keeps_inherited_style(self):
        original_scene = bpy.context.window.scene
        scene = bpy.data.scenes.new("Dimensions Fresh Scene")
        try:
            bpy.context.window.scene = scene
            self.assertEqual(scene.dimensions_settings.schema_version, 0)
            created = create_dimension_object(bpy.context, "Fresh Inherited Annotation")
            self.assertEqual(scene.dimensions_settings.schema_version, CURRENT_SCHEMA_VERSION)
            self.assertFalse(created.dimension_props.override_line_width)
            self.assertFalse(created.dimension_props.override_precision)
        finally:
            bpy.context.window.scene = original_scene
            bpy.data.scenes.remove(scene)

    def test_schema_v14_fixture_migrates_sheet_defaults_idempotently(self):
        load_handlers = bpy.app.handlers.load_post
        migration_handler = migrations_module._load_post_handler
        handler_was_registered = migration_handler in load_handlers
        if handler_was_registered:
            load_handlers.remove(migration_handler)
        try:
            bpy.ops.wm.open_mainfile(filepath=str(self.SCHEMA_V14_FIXTURE), load_ui=False)
        finally:
            if handler_was_registered and migration_handler not in load_handlers:
                load_handlers.append(migration_handler)

        scene = bpy.context.scene
        settings = scene.dimensions_settings
        self.assertTrue(scene_has_dimensions_data(scene))
        self.assertEqual(settings.schema_version, 14)

        self.assertTrue(migrate_scene(scene))
        self.assertEqual(settings.schema_version, CURRENT_SCHEMA_VERSION)
        self.assertFalse(settings.sheet_border_enabled)
        self.assertFalse(settings.sheet_title_block_enabled)
        self.assertAlmostEqual(settings.sheet_margin_mm, 10.0)
        self.assertAlmostEqual(settings.sheet_title_block_width_mm, 80.0)
        self.assertAlmostEqual(settings.sheet_title_block_height_mm, 30.0)
        self.assertEqual(settings.sheet_drawing_title, "")
        self.assertEqual(settings.sheet_drawing_number, "")
        self.assertEqual(settings.sheet_revision, "")
        self.assertEqual(settings.sheet_author, "")
        self.assertEqual(settings.sheet_date, "")

        property_names = (
            "sheet_border_enabled", "sheet_title_block_enabled", "sheet_margin_mm",
            "sheet_title_block_width_mm", "sheet_title_block_height_mm",
            "sheet_drawing_title", "sheet_drawing_number", "sheet_revision",
            "sheet_author", "sheet_date",
        )
        expected = {name: getattr(settings, name) for name in property_names}
        self.assertFalse(migrate_scene(scene))
        self.assertEqual(
            {name: getattr(settings, name) for name in property_names},
            expected,
        )

    def _open_without_migration(self, filepath):
        load_handlers = bpy.app.handlers.load_post
        migration_handler = migrations_module._load_post_handler
        handler_was_registered = migration_handler in load_handlers
        if handler_was_registered:
            load_handlers.remove(migration_handler)
        try:
            bpy.ops.wm.open_mainfile(filepath=str(filepath), load_ui=False)
        finally:
            if handler_was_registered and migration_handler not in load_handlers:
                load_handlers.append(migration_handler)
        return bpy.context.scene

    def _linear_geometry(self, obj):
        props = obj.dimension_props
        return get_dimension_world_geometry(
            props.dimension_type,
            resolve_anchor(props.start),
            resolve_anchor(props.end),
            Vector(props.offset_plane_normal),
            props.offset_distance,
            props.offset_angle,
            props.measurement_mode,
        )

    def test_schema_v15_fixture_converts_removed_0_6_features(self):
        scene = self._open_without_migration(self.SCHEMA_V15_FIXTURE)
        self.assertEqual(scene.dimensions_settings.schema_version, 15)
        self.assertTrue(migrate_scene(scene))
        self.assertEqual(scene.dimensions_settings.schema_version, CURRENT_SCHEMA_VERSION)
        objects = scene.objects

        for name in ("DIM Circle Removed", "DIM Coordinate Removed", "DIM Elevation Removed"):
            self.assertIsNone(objects.get(name), name)

        for set_name, offsets, values in (
            ("DIM Chain Set", (0.3, 0.3), (1.0, 2.0)),
            ("DIM Baseline Set", (0.3, 0.7), (1.0, 2.5)),
        ):
            self.assertIsNone(objects.get(set_name))
            members = [objects.get(f"{set_name} {index}") for index in (1, 2)]
            self.assertTrue(all(member is not None for member in members), set_name)
            for member, offset, value in zip(members, offsets, values):
                props = member.dimension_props
                self.assertEqual(props.annotation_kind, "LINEAR")
                self.assertEqual(props.measurement_mode, "DELTA_X")
                self.assertAlmostEqual(props.offset_distance, offset, places=5)
                self.assertAlmostEqual(self._linear_geometry(member)["value"], value, places=5)
                self.assertTrue(props.override_color)
                self.assertAlmostEqual(props.color[0], 1.0, places=5)
                self.assertAlmostEqual(props.color[1], 0.2, places=5)
        chain_lines = [self._linear_geometry(objects.get(f"DIM Chain Set {index}")) for index in (1, 2)]
        self.assertLess((chain_lines[0]["line_end_world"] - chain_lines[1]["line_start_world"]).length, 1e-5)

        for name, origin, direction in (
            ("GUIDE Fixed", (0.0, 5.0, 0.0), (1.0, 0.0, 0.0)),
            ("GUIDE Offset Derived", (0.0, 6.0, 0.0), (1.0, 0.0, 0.0)),
            ("GUIDE Angular Derived", (0.0, 5.0, 0.0), (0.70710678, 0.70710678, 0.0)),
            ("GUIDE Axis Z", (3.0, 3.0, 0.0), (0.0, 0.0, 1.0)),
            ("GUIDE Vertex Anchored", (-1.0, -1.0, 1.0), (0.0, 1.0, 0.0)),
        ):
            line = guide_line_world(objects.get(name))
            self.assertIsNotNone(line, name)
            self.assertLess((line[0] - Vector(origin)).length, 1e-5, name)
            self.assertLess((line[1] - Vector(direction)).length, 1e-5, name)
        self.assertIsNotNone(guide_line_world(objects.get("GUIDE Spacing Derived")))

        self.assertEqual(guide_point_world(objects.get("POINT Vertex Anchored")), Vector((1.0, 1.0, 1.0)))
        self.assertEqual(objects.get("DATUM Origin").guide_props.kind, "POINT")

        for name in ("PLANE Three Points", "PLANE Face", "PLANE Point Normal", "PLANE Offset"):
            plane = objects.get(name)
            self.assertIsNotNone(plane, name)
            self.assertEqual(plane.type, "MESH", name)
            self.assertTrue(plane.get(GUIDE_PLANE_FLAG), name)
            self.assertEqual(plane.guide_props.kind, "PLANE", name)
        origin, _axis_u, _axis_v, normal = guide_plane_frame(objects.get("PLANE Face"))
        self.assertLess((origin - Vector((1.0, 0.0, 0.0))).length, 1e-5)
        self.assertLess((normal - Vector((1.0, 0.0, 0.0))).length, 1e-5)

        segment = construction_segment_world(objects.get("MEASURE Segment"))
        self.assertEqual(segment, (Vector((0.0, -7.0, 0.0)), Vector((2.0, -7.0, 0.0))))
        self.assertIsNotNone(objects.get("DIM Linear Kept"))

        raw_settings = scene.bl_system_properties_get()["dimensions_settings"]
        self.assertNotIn("active_plane_mode", raw_settings.keys())
        chain_raw = objects.get("DIM Chain Set 1").bl_system_properties_get()["dimension_props"]
        self.assertNotIn("set_members", chain_raw.keys())

        names = sorted(obj.name for obj in scene.objects)
        self.assertFalse(migrate_scene(scene))
        self.assertEqual(sorted(obj.name for obj in scene.objects), names)
        sync_scene_objects(scene)
        self.assertEqual(objects.get("DIM Chain Set 1").dimension_props.measurement_state, "LIVE")

    def test_an_unstamped_released_file_migrates_to_the_current_schema(self):
        bpy.ops.wm.open_mainfile(filepath=str(self.FIXTURE), load_ui=False)
        scene = bpy.context.scene
        self.assertTrue(scene_has_dimensions_data(scene))

        # load_post runs on open; opening an unstamped file must land it at current.
        self.assertEqual(scene.dimensions_settings.schema_version, CURRENT_SCHEMA_VERSION)

        dimension = bpy.data.objects.get("DIM Legacy")
        self.assertIsNotNone(dimension)
        self.assertGreater(dimension.dimension_props.start.vertex_id, 0)
        self.assertGreater(dimension.dimension_props.end.vertex_id, 0)

    def test_migrating_a_released_file_twice_changes_nothing(self):
        bpy.ops.wm.open_mainfile(filepath=str(self.FIXTURE), load_ui=False)
        scene = bpy.context.scene
        dimension = bpy.data.objects.get("DIM Legacy")
        identifiers = (
            dimension.dimension_props.start.vertex_id,
            dimension.dimension_props.end.vertex_id,
        )

        self.assertFalse(migrate_scene(scene))
        self.assertEqual(scene.dimensions_settings.schema_version, CURRENT_SCHEMA_VERSION)
        self.assertEqual(
            (
                dimension.dimension_props.start.vertex_id,
                dimension.dimension_props.end.vertex_id,
            ),
            identifiers,
        )

    def test_the_0_3_2_fixture_migrates_output_settings(self):
        bpy.ops.wm.open_mainfile(filepath=str(self.OUTPUT_FIXTURE), load_ui=False)
        scene = bpy.context.scene
        self.assertTrue(scene_has_dimensions_data(scene))
        self.assertEqual(scene.dimensions_settings.schema_version, CURRENT_SCHEMA_VERSION)
        self.assertEqual(scene.dimensions_settings.output_sizing_mode, "CAMERA")
        self.assertEqual(scene.dimensions_settings.output_scope, "VISIBLE")
        self.assertAlmostEqual(scene.dimensions_settings.output_line_width, 2.0)
        self.assertAlmostEqual(scene.dimensions_settings.output_text_height, 14.0)
        self.assertEqual(len(scene.dimensions_settings.output_source_bindings), 0)

    def test_schema_v2_fixture_receives_guide_point_v8_defaults(self):
        bpy.ops.wm.open_mainfile(filepath=str(self.SCHEMA_V2_FIXTURE), load_ui=False)
        scene = bpy.context.scene
        self.assertEqual(scene.dimensions_settings.schema_version, CURRENT_SCHEMA_VERSION)
        self.assertTrue(scene.dimensions_settings.snap_guide_point)
        self.assertTrue(scene.dimensions_settings.annotation_manager_kind_point)

    def test_schema_v2_fixture_receives_guide_plane_v13_defaults(self):
        bpy.ops.wm.open_mainfile(filepath=str(self.SCHEMA_V2_FIXTURE), load_ui=False)
        scene = bpy.context.scene
        settings = scene.dimensions_settings
        self.assertEqual(settings.schema_version, CURRENT_SCHEMA_VERSION)
        self.assertTrue(settings.snap_guide_plane)
        self.assertTrue(settings.annotation_manager_kind_plane)
        self.assertFalse(migrate_scene(scene))

    def test_released_annotation_appearance_is_preserved_as_explicit_overrides(self):
        bpy.ops.wm.open_mainfile(filepath=str(self.OUTPUT_FIXTURE), load_ui=False)
        scene = bpy.context.scene
        dimensions_in_fixture = [
            obj for obj in scene.objects
            if getattr(getattr(obj, "dimension_props", None), "enabled", False)
        ]
        self.assertTrue(dimensions_in_fixture)
        # These are the presentation values stored in the released 0.3.2
        # fixture, asserted independently rather than derived post-migration.
        expected = {
            "color": (1.0, 1.0, 1.0, 1.0),
            "selected_color": (1.0, 0.72, 0.25, 1.0),
            "line_width": 2.0,
            "text_size": 14,
            "arrow_size": 10.0,
            "arrow_end_style": "ARROW",
            "start_end_style": "OPEN",
            "end_end_style": "OPEN",
            "extension_gap": 0.0,
            "extension_overshoot": 0.0,
            "secondary_unit_style": "NONE",
            "secondary_precision": 2,
            "dual_unit_arrangement": "BRACKETS",
            "label_orientation": "HORIZONTAL",
            "label_line_mode": "BROKEN",
            "value_prefix": "",
            "value_suffix": "",
            "tolerance_mode": "NONE",
            "tolerance_upper": 0.0,
            "tolerance_lower": 0.0,
            "precision": 3,
            "unit_style": "AUTO",
        }
        for obj in dimensions_in_fixture:
            props = obj.dimension_props
            self.assertEqual(props.annotation_kind, "LINEAR")
            resolved = resolve_dimension_style(scene.dimensions_settings, props)
            self.assertEqual(props.style_name, "")
            self.assertTrue(all(
                getattr(props, f"override_{name}") for name in STYLE_PROPERTY_NAMES
            ))
            for actual, expected_channel in zip(resolved.color, expected["color"]):
                self.assertAlmostEqual(actual, expected_channel, places=5)
            for actual, expected_channel in zip(resolved.selected_color, expected["selected_color"]):
                self.assertAlmostEqual(actual, expected_channel, places=5)
            for name in (
                "line_width", "text_size", "arrow_size", "arrow_end_style",
                "start_end_style", "end_end_style", "extension_gap", "extension_overshoot",
                "secondary_unit_style", "secondary_precision", "dual_unit_arrangement",
                "label_orientation", "label_line_mode",
                "value_prefix", "value_suffix", "tolerance_mode",
                "tolerance_upper", "tolerance_lower", "precision",
            ):
                self.assertEqual(getattr(resolved, name), expected[name])
            self.assertEqual(resolved.unit_style, expected["unit_style"])
        self.assertFalse(scene.dimensions_settings.use_snap_target_override)
        for identifier in TARGET_IDS:
            self.assertTrue(getattr(scene.dimensions_settings, f"snap_{identifier}"))

    def test_schema_v2_fixture_preserves_snap_and_style_state(self):
        # Suppress load-time migration for this open so the test can first prove
        # that the fixture really came from the retained schema-v2 release. The
        # migration is then invoked explicitly and inspected on both sides.
        load_handlers = bpy.app.handlers.load_post
        migration_handler = migrations_module._load_post_handler
        handler_was_registered = migration_handler in load_handlers
        if handler_was_registered:
            load_handlers.remove(migration_handler)
        try:
            bpy.ops.wm.open_mainfile(filepath=str(self.SCHEMA_V2_FIXTURE), load_ui=False)
        finally:
            if handler_was_registered and migration_handler not in load_handlers:
                load_handlers.append(migration_handler)

        scene = bpy.context.scene
        settings = scene.dimensions_settings
        self.assertTrue(scene_has_dimensions_data(scene))
        self.assertEqual(settings.schema_version, 2)
        self.assertEqual(settings.output_sizing_mode, "CAMERA")
        self.assertEqual(settings.output_scope, "VISIBLE")
        self.assertEqual(len(settings.annotation_styles), 0)

        dimensions_in_fixture = [
            obj for obj in scene.objects
            if getattr(getattr(obj, "dimension_props", None), "enabled", False)
        ]
        self.assertTrue(dimensions_in_fixture)
        released_style = {
            "color": (1.0, 1.0, 1.0, 1.0),
            "selected_color": (1.0, 0.72, 0.25, 1.0),
            "line_width": 2.0,
            "text_size": 14,
            "arrow_size": 10.0,
            "arrow_end_style": "ARROW",
            "value_prefix": "",
            "value_suffix": "",
            "tolerance_mode": "NONE",
            "tolerance_upper": 0.0,
            "tolerance_lower": 0.0,
        }
        presentation_before = {}
        for obj in dimensions_in_fixture:
            props = obj.dimension_props
            presentation_before[obj.name] = {
                "color": tuple(props.color),
                "selected_color": tuple(props.selected_color),
                "line_width": props.line_width,
                "text_size": props.text_size,
                "arrow_size": props.arrow_size,
                "arrow_end_style": props.arrow_end_style,
                "value_prefix": props.value_prefix,
                "value_suffix": props.value_suffix,
                "tolerance_mode": props.tolerance_mode,
                "tolerance_upper": props.tolerance_upper,
                "tolerance_lower": props.tolerance_lower,
            }
            for name, expected_value in released_style.items():
                actual = presentation_before[obj.name][name]
                if name in {"color", "selected_color"}:
                    for channel, expected_channel in zip(actual, expected_value):
                        self.assertAlmostEqual(channel, expected_channel, places=5)
                else:
                    self.assertEqual(actual, expected_value)

        self.assertTrue(migrate_scene(scene))
        self.assertEqual(settings.schema_version, CURRENT_SCHEMA_VERSION)
        self.assertEqual(len(settings.annotation_styles), 0)
        self.assertFalse(settings.use_snap_target_override)
        self.assertEqual(settings.vector_paper_size, "A4")
        self.assertEqual(settings.vector_orientation, "PORTRAIT")
        self.assertAlmostEqual(settings.vector_scale_denominator, 10.0)
        self.assertAlmostEqual(settings.vector_line_width_mm, 0.25)
        self.assertAlmostEqual(settings.vector_text_height_mm, 3.5)
        self.assertAlmostEqual(settings.vector_arrow_size_mm, 2.5)
        self.assertEqual(settings.dimension_start_end_style, "OPEN")
        self.assertEqual(settings.dimension_end_end_style, "OPEN")
        self.assertEqual(settings.dimension_extension_gap, 0.0)
        self.assertEqual(settings.dimension_extension_overshoot, 0.0)
        self.assertEqual(settings.dimension_secondary_unit_style, "NONE")
        self.assertEqual(settings.dimension_label_orientation, "HORIZONTAL")
        self.assertEqual(settings.dimension_label_line_mode, "BROKEN")
        for identifier in TARGET_IDS:
            self.assertTrue(getattr(settings, f"snap_{identifier}"))

        for obj in dimensions_in_fixture:
            props = obj.dimension_props
            resolved = resolve_dimension_style(settings, props)
            expected = presentation_before[obj.name]
            self.assertEqual(props.style_name, "")
            self.assertTrue(all(
                getattr(props, f"override_{name}") for name in STYLE_PROPERTY_NAMES
            ))
            for name, expected_value in expected.items():
                actual = getattr(resolved, name)
                if name in {"color", "selected_color"}:
                    for channel, expected_channel in zip(actual, expected_value):
                        self.assertAlmostEqual(channel, expected_channel, places=5)
                else:
                    self.assertEqual(actual, expected_value)
            self.assertEqual(resolved.precision, settings.precision)
            self.assertEqual(resolved.unit_style, "AUTO")
            self.assertEqual(resolved.start_end_style, "OPEN")
            self.assertEqual(resolved.end_end_style, "OPEN")
            self.assertEqual(resolved.extension_gap, 0.0)
            self.assertEqual(resolved.extension_overshoot, 0.0)
            self.assertEqual(resolved.secondary_unit_style, "NONE")
            self.assertEqual(resolved.label_orientation, "HORIZONTAL")
            self.assertEqual(resolved.label_line_mode, "BROKEN")
            for _anchor_name, anchor in dimension_source_anchors(props):
                self.assertIn(anchor.resolution_status, {"BY_ID", "BY_FALLBACK", "UNRESOLVABLE"})
                if anchor.target_object is not None:
                    self.assertEqual(anchor.source_object_name, anchor.target_object.name)
        self.assertFalse(migrate_scene(scene))

    def test_persisted_enum_item_numbers_never_move(self):
        from dimensions.properties import classes

        actual = {
            f"{cls.__name__}.{prop.identifier}": {item.identifier: item.value for item in prop.enum_items}
            for cls in classes
            for prop in cls.bl_rna.properties
            if prop.type == "ENUM" and not prop.is_enum_flag
        }
        expected = {
            name: {identifier: number for number, identifier in enumerate(items)}
            for name, items in PERSISTED_ENUM_ITEMS.items()
        }
        self.assertEqual(actual, expected)

        bpy.ops.wm.read_homefile(use_empty=True)
        settings = bpy.context.scene.dimensions_settings
        settings.annotation_manager_bulk_scope = "FILTERED"
        raw = bpy.context.scene.bl_system_properties_get()["dimensions_settings"]
        self.assertEqual(raw["annotation_manager_bulk_scope"], 0)
        raw["annotation_manager_bulk_scope"] = 1  # what 0.6 saved for Selected
        self.assertEqual(settings.annotation_manager_bulk_scope, "SELECTED")

    def _current_construction_and_style(self):
        context = bpy.context
        line = create_guide_object(context, "GUIDE Kept Line")
        set_guide_line_transform(line, Vector((3.0, 4.0, 5.0)), Vector((0.0, 1.0, 0.0)))
        create_guide_point_object(context, "POINT Kept", location=Vector((1.0, 2.0, 3.0)))
        create_guide_plane_object(
            context, plane_frame(Vector((0.0, 0.0, 2.0)), Vector((0.0, 1.0, 0.0))), 1.5, 0.5, "PLANE Kept",
        )
        dimension = create_dimension_object(context, "DIM Kept Style")
        set_world_anchor(dimension.dimension_props.start, Vector((0.0, 0.0, 0.0)))
        set_world_anchor(dimension.dimension_props.end, Vector((2.0, 0.0, 0.0)))
        context.scene.dimensions_settings.annotation_styles.add().name = "House"
        props = dimension.dimension_props
        props.style_name = "House"
        props.start_end_style = "DOT"
        props.override_start_end_style = True
        props.extension_gap = 4.0
        props.override_extension_gap = True
        sync_scene_objects(context.scene)

    def _construction_and_style_snapshot(self):
        objects = bpy.data.objects
        line = guide_line_world(objects["GUIDE Kept Line"])
        plane = objects["PLANE Kept"]
        frame = guide_plane_frame(plane)
        props = objects["DIM Kept Style"].dimension_props
        return (
            tuple(round(value, 5) for value in (*line[0], *line[1])),
            tuple(round(value, 5) for value in guide_point_world(objects["POINT Kept"])),
            tuple(round(value, 5) for value in (*frame[0], *frame[3])),
            (round(plane.guide_props.plane_extent, 5), round(plane.guide_props.plane_spacing, 5)),
            (props.style_name, props.start_end_style, props.override_start_end_style,
             round(props.extension_gap, 5), props.override_extension_gap, props.override_color),
        )

    def test_current_objects_keep_their_shape_in_new_scenes_and_on_append(self):
        bpy.ops.wm.read_homefile(use_empty=True)
        scene = bpy.context.scene
        self._current_construction_and_style()
        expected = self._construction_and_style_snapshot()
        owned = [obj for obj in scene.objects if is_dimension_object(obj) or is_guide_object(obj)]
        self.assertTrue(owned)
        self.assertTrue(all(object_schema_version(obj) == CURRENT_SCHEMA_VERSION for obj in owned))

        # Shift+D carries the stamp to the copy.
        for obj in bpy.context.selected_objects:
            obj.select_set(False)
        line = bpy.data.objects["GUIDE Kept Line"]
        line.select_set(True)
        bpy.context.view_layer.objects.active = line
        self.assertEqual(bpy.ops.object.duplicate(), {"FINISHED"})
        self.assertIsNot(bpy.context.active_object, line)
        self.assertEqual(bpy.context.active_object.guide_props.schema_version, CURRENT_SCHEMA_VERSION)
        bpy.data.objects.remove(bpy.context.active_object, do_unlink=True)

        # A new, never-stamped scene showing the same collections.
        second = bpy.data.scenes.new("Dimensions Unstamped Scene")
        self.assertEqual(second.dimensions_settings.schema_version, 0)
        for role in ("DIMENSIONS", "GUIDES"):
            second.collection.children.link(get_scene_collection(scene, role))
        _run_scheduled_sync()
        self.assertEqual(second.dimensions_settings.schema_version, CURRENT_SCHEMA_VERSION)
        self.assertEqual(self._construction_and_style_snapshot(), expected)
        bpy.data.scenes.remove(second)

        with tempfile.TemporaryDirectory() as directory:
            saved = Path(directory) / "dimensions-current-shape.blend"
            library = Path(directory) / "dimensions-current-library.blend"
            bpy.data.libraries.write(
                str(library),
                {get_scene_collection(scene, "DIMENSIONS"), get_scene_collection(scene, "GUIDES")},
            )
            bpy.ops.wm.save_as_mainfile(filepath=str(saved))
            bpy.ops.wm.open_mainfile(filepath=str(saved), load_ui=False)
            reloaded = [obj for obj in bpy.context.scene.objects if is_dimension_object(obj) or is_guide_object(obj)]
            self.assertTrue(all(object_schema_version(obj) == CURRENT_SCHEMA_VERSION for obj in reloaded))
            self.assertEqual(self._construction_and_style_snapshot(), expected)

            # File > New, then Append the collections into the unstamped startup scene.
            bpy.ops.wm.read_homefile(use_empty=True)
            fresh = bpy.context.scene
            self.assertEqual(fresh.dimensions_settings.schema_version, 0)
            with bpy.data.libraries.load(str(library), link=False) as (data_from, data_to):
                data_to.collections = list(data_from.collections)
            for collection in data_to.collections:
                fresh.collection.children.link(collection)
            _run_scheduled_sync()
            bpy.context.view_layer.update()
            self.assertEqual(fresh.dimensions_settings.schema_version, CURRENT_SCHEMA_VERSION)
            props = bpy.data.objects["DIM Kept Style"].dimension_props
            # The named style itself is scene-owned and stays behind, but the reference is kept.
            self.assertEqual(props.style_name, "House")
            self.assertEqual(self._construction_and_style_snapshot(), expected)

    def test_0_6_objects_appended_into_a_current_scene_are_converted(self):
        bpy.ops.wm.read_homefile(use_empty=True)
        scene = bpy.context.scene
        current = create_dimension_object(bpy.context, "DIM Current")
        set_world_anchor(current.dimension_props.start, Vector((0.0, 0.0, 0.0)))
        set_world_anchor(current.dimension_props.end, Vector((1.0, 0.0, 0.0)))
        self.assertEqual(scene.dimensions_settings.schema_version, CURRENT_SCHEMA_VERSION)
        names = (
            "GUIDE Axis Z", "GUIDE Offset Derived", "DIM Chain Set", "PLANE Point Normal",
            "DIM Circle Removed", "POINT World",
        )
        with bpy.data.libraries.load(str(self.SCHEMA_V15_FIXTURE), link=False) as (_data_from, data_to):
            data_to.objects = list(names)
        for obj in data_to.objects:
            scene.collection.objects.link(obj)
        _run_scheduled_sync()

        objects = scene.objects
        for name, origin, direction in (
            ("GUIDE Axis Z", (3.0, 3.0, 0.0), (0.0, 0.0, 1.0)),
            ("GUIDE Offset Derived", (0.0, 6.0, 0.0), (1.0, 0.0, 0.0)),
        ):
            line = guide_line_world(objects[name])
            self.assertLess((line[0] - Vector(origin)).length, 1e-5, name)
            self.assertLess((line[1] - Vector(direction)).length, 1e-5, name)
        self.assertLess((guide_point_world(objects["POINT World"]) - Vector((2.0, 2.0, 2.0))).length, 1e-5)
        self.assertIsNone(objects.get("DIM Chain Set"))
        self.assertIsNone(objects.get("DIM Circle Removed"))
        for index in (1, 2):
            member = objects[f"DIM Chain Set {index}"]
            self.assertEqual(member.dimension_props.annotation_kind, "LINEAR")
            self.assertEqual(member.dimension_props.measurement_mode, "DELTA_X")
            self.assertTrue(member.dimension_props.override_color)
        plane = objects["PLANE Point Normal"]
        self.assertEqual(plane.type, "MESH")
        self.assertTrue(plane.get(GUIDE_PLANE_FLAG))
        origin, _axis_u, _axis_v, normal = guide_plane_frame(plane)
        self.assertLess((origin - Vector((0.0, 8.0, 0.0))).length, 1e-5)
        self.assertAlmostEqual(abs(normal.y), 1.0, places=5)
        owned = [obj for obj in objects if is_dimension_object(obj) or is_guide_object(obj)]
        self.assertTrue(all(object_schema_version(obj) == CURRENT_SCHEMA_VERSION for obj in owned))
        before = self._scene_state(scene)
        _run_scheduled_sync()
        self.assertEqual(self._scene_state(scene), before)

    def _scene_state(self, scene):
        return sorted((obj.name, tuple(round(value, 5) for value in obj.matrix_world.col[3])) for obj in scene.objects)

    def test_0_6_annotations_appended_into_an_unstamped_scene_keep_their_style(self):
        bpy.ops.wm.read_homefile(use_empty=True)
        scene = bpy.context.scene
        self.assertEqual(scene.dimensions_settings.schema_version, 0)
        with bpy.data.libraries.load(str(self.SCHEMA_V15_FIXTURE), link=False) as (_data_from, data_to):
            data_to.objects = ["DIM Linear Kept", "DIM Chain Set"]
        kept, chain = data_to.objects
        kept.dimension_props.style_name = "House"
        kept.dimension_props.override_line_width = False
        kept.dimension_props.start_end_style = "DOT"
        kept.dimension_props.override_start_end_style = True
        for obj in (kept, chain):
            scene.collection.objects.link(obj)
        _run_scheduled_sync()

        self.assertEqual(scene.dimensions_settings.schema_version, CURRENT_SCHEMA_VERSION)
        props = kept.dimension_props
        self.assertEqual(props.style_name, "House")
        self.assertFalse(props.override_line_width)
        self.assertEqual(props.start_end_style, "DOT")
        self.assertEqual(object_schema_version(kept), CURRENT_SCHEMA_VERSION)
        member = scene.objects["DIM Chain Set 1"].dimension_props
        self.assertTrue(member.override_color)
        self.assertAlmostEqual(member.color[1], 0.2, places=5)

    def test_a_scene_from_a_newer_schema_is_never_written(self):
        bpy.ops.wm.read_homefile(use_empty=True)
        scene = bpy.context.scene
        settings = scene.dimensions_settings
        measurement = create_measurement_object(bpy.context, "MEASURE Future")
        set_world_anchor(measurement.guide_props.start, Vector((0.0, 1.0, 0.0)))
        set_world_anchor(measurement.guide_props.end, Vector((2.0, 1.0, 0.0)))
        measurement.location = (1.0, 1.0, 0.0)
        dimension = create_dimension_object(bpy.context, "DIM Future")
        set_world_anchor(dimension.dimension_props.start, Vector((0.0, 0.0, 0.0)))
        set_world_anchor(dimension.dimension_props.end, Vector((2.0, 0.0, 0.0)))
        sync_scene_objects(scene)

        settings.schema_version = CURRENT_SCHEMA_VERSION + 1
        measurement.location = (9.0, 9.0, 9.0)
        dimension.location = (5.0, 5.0, 5.0)

        def state():
            return (
                tuple(measurement.guide_props.start.world_co),
                tuple(measurement.guide_props.end.world_co),
                tuple(dimension.dimension_props.presentation_offset),
                sorted(obj.name for obj in scene.objects),
            )

        before = state()
        _run_scheduled_sync()
        sync_scene_objects(scene)
        self.assertEqual(state(), before)
        with self.assertRaises(RuntimeError):
            create_dimension_object(bpy.context, "DIM Refused")
        with self.assertRaises(RuntimeError):
            create_guide_object(bpy.context, "GUIDE Refused")
        self.assertIsNone(bpy.data.objects.get("DIM Refused"))
        self.assertIsNone(bpy.data.objects.get("GUIDE Refused"))
        self.assertEqual(settings.schema_version, CURRENT_SCHEMA_VERSION + 1)

    def test_conversion_keeps_visibility_and_parenting(self):
        scene = self._open_without_migration(self.SCHEMA_V15_FIXTURE)
        view_layer = bpy.context.view_layer
        chain = scene.objects["DIM Chain Set"]
        chain.hide_set(True)
        chain.hide_select = True
        plane = scene.objects["PLANE Point Normal"]
        parent = bpy.data.objects.new("Plane Parent", None)
        scene.collection.objects.link(parent)
        parent.location = (0.0, 0.0, 3.0)
        parent.rotation_euler = (0.0, 0.0, 0.5)
        with scene_sync_suspended():
            view_layer.update()
        plane.parent = parent
        plane.matrix_parent_inverse = parent.matrix_world.inverted()
        plane.hide_viewport = True
        plane.hide_set(True)

        self.assertTrue(migrate_scene(scene))
        for index in (1, 2):
            member = scene.objects[f"DIM Chain Set {index}"]
            self.assertTrue(member.hide_get(view_layer=view_layer))
            self.assertTrue(member.hide_select)
        converted = scene.objects["PLANE Point Normal"]
        self.assertEqual(converted.type, "MESH")
        self.assertEqual(converted.parent, parent)
        self.assertTrue(converted.hide_viewport)
        self.assertTrue(converted.hide_get(view_layer=view_layer))
        with scene_sync_suspended():
            view_layer.update()
        origin, _axis_u, _axis_v, normal = guide_plane_frame(converted)
        self.assertLess((origin - Vector((0.0, 8.0, 0.0))).length, 1e-5)
        self.assertAlmostEqual(abs(normal.y), 1.0, places=5)

    def test_conversion_removes_output_left_by_deleted_annotations(self):
        scene = self._open_without_migration(self.SCHEMA_V15_FIXTURE)
        settings = scene.dimensions_settings
        for name, key in (("DIM Circle Removed", "removed-source"), ("DIM Linear Kept", "kept-source")):
            binding = settings.output_source_bindings.add()
            binding.source = scene.objects[name]
            binding.key = key
            generate_grease_pencil_output(
                scene, {"source_key": key, "strokes": [{"points": [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)]}]},
            )
        self.assertEqual(len(generated_output_objects(scene, "removed-source")), 1)

        self.assertTrue(migrate_scene(scene))
        self.assertEqual(generated_output_objects(scene, "removed-source"), ())
        self.assertEqual(len(generated_output_objects(scene, "kept-source")), 1)
        self.assertEqual([binding.key for binding in settings.output_source_bindings], ["kept-source"])

    def test_opening_a_0_6_file_resolves_anchors_on_transformed_meshes(self):
        scene = self._open_without_migration(self.SCHEMA_V15_FIXTURE)
        with tempfile.TemporaryDirectory() as directory:
            moved = Path(directory) / "schema-v15-moved-block.blend"
            with scene_sync_suspended():
                scene.objects["Fixture Block"].location = (10.0, 0.0, 0.0)
                bpy.ops.wm.save_as_mainfile(filepath=str(moved), copy=True)
            # load_post runs before Blender evaluates the file's transforms.
            bpy.ops.wm.open_mainfile(filepath=str(moved), load_ui=False)
        objects = bpy.context.scene.objects
        self.assertEqual(bpy.context.scene.dimensions_settings.schema_version, CURRENT_SCHEMA_VERSION)
        self.assertLess((guide_point_world(objects["POINT Vertex Anchored"]) - Vector((11.0, 1.0, 1.0))).length, 1e-5)
        line = guide_line_world(objects["GUIDE Vertex Anchored"])
        self.assertLess((line[0] - Vector((9.0, -1.0, 1.0))).length, 1e-5)
        self.assertLess((line[1] - Vector((0.0, 1.0, 0.0))).length, 1e-5)


def main():
    loader = unittest.defaultTestLoader
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.TestSuite(
            loader.loadTestsFromTestCase(case)
            for case in (
                DimensionsLifecycleTests,
                DimensionsLifecycleMatrixTests,
                DimensionsReleasedFileTests,
            )
        )
    )
    if not result.wasSuccessful():
        raise SystemExit(1)
    print("Dimensions lifecycle checks passed")


if __name__ == "__main__":
    main()
