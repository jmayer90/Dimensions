"""Focused DIM-01 persistent chain and baseline coverage."""

import inspect
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import bpy
from mathutils import Vector

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

import dimensions
from dimensions.anchors import set_anchor, set_world_anchor
from dimensions.annotation_manager import annotation_display_value, annotation_state, sync_annotation_manager
from dimensions.collections import create_dimension_object
from dimensions.dimension_sets import (
    anchor_snapshot, automatic_baseline_spacing, delete_set_member,
    dimension_set_state, dimension_set_world_geometry, insert_chain_anchor,
    move_set_member, synchronize_set_member_anchor,
)
from dimensions.drawing import _build_dimension_set_geometry, _geometry_hit_distance
from dimensions.operators.dimension_set import DIMENSIONS_OT_CreateDimensionSet
from dimensions.output_geometry import WorldSizingPolicy, dimension_set_output_spec
from dimensions.constants import CURRENT_SCHEMA_VERSION
from dimensions.migrations import migrate_scene


class DimensionsSetTests(unittest.TestCase):
    def setUp(self):
        self.scene = bpy.context.scene
        self.created = []

    def tearDown(self):
        for obj in reversed(self.created):
            if bpy.data.objects.get(obj.name) is not None:
                data = obj.data
                bpy.data.objects.remove(obj, do_unlink=True)
                if data is not None and data.users == 0 and isinstance(data, bpy.types.Mesh):
                    bpy.data.meshes.remove(data)

    def _set(self, kind, points):
        obj = create_dimension_object(bpy.context, f"DIM {kind.title()} Test")
        self.created.append(obj)
        props = obj.dimension_props
        props.annotation_kind = "DIMENSION_SET"
        props.set_kind = kind
        props.offset_distance = 0.25
        props.offset_plane_normal = (0.0, 0.0, 1.0)
        pairs = zip(points, points[1:]) if kind == "CHAIN" else ((points[0], point) for point in points[1:])
        for start, end in pairs:
            member = props.set_members.add()
            set_world_anchor(member.start, Vector(start))
            set_world_anchor(member.end, Vector(end))
        return obj

    def _snapshot(self, props, point):
        temp = props.set_members.add()
        set_world_anchor(temp.end, Vector(point))
        value = anchor_snapshot(temp.end)
        props.set_members.remove(len(props.set_members) - 1)
        return value

    def test_chain_is_one_persistent_object_with_a_shared_dimension_line(self):
        obj = self._set("CHAIN", ((0, 0, 0), (1, 0, 0), (2, 0, 0), (3, 0, 0)))
        geometry = dimension_set_world_geometry(obj.dimension_props)
        self.assertEqual(len(geometry), 3)
        self.assertTrue(all(abs(item["line_start_world"].y - 0.25) < 1e-6 for item in geometry))
        self.assertTrue(all(abs(item["line_end_world"].y - 0.25) < 1e-6 for item in geometry))
        self.assertEqual([item["value"] for item in geometry], [1.0, 1.0, 1.0])

    def test_inserting_and_deleting_chain_points_reflows_continuously(self):
        obj = self._set("CHAIN", ((0, 0, 0), (1, 0, 0), (2, 0, 0)))
        props = obj.dimension_props
        insert_chain_anchor(props, 0, self._snapshot(props, (0.5, 0, 0)))
        self.assertEqual([round(item["value"], 3) for item in dimension_set_world_geometry(props)], [0.5, 0.5, 1.0])
        delete_set_member(props, 1)
        geometry = dimension_set_world_geometry(props)
        self.assertEqual([round(item["value"], 3) for item in geometry], [0.5, 1.5])
        self.assertLess((geometry[0]["end_world"] - geometry[1]["start_world"]).length, 1e-6)

    def test_deleting_chain_member_zero_trims_start(self):
        obj = self._set("CHAIN", ((0, 0, 0), (1, 0, 0), (2, 0, 0), (3, 0, 0)))
        props = obj.dimension_props
        delete_set_member(props, 0)
        geometry = dimension_set_world_geometry(props)
        self.assertEqual(len(geometry), 2)
        self.assertEqual(tuple(geometry[0]["start_world"]), (1.0, 0.0, 0.0))
        self.assertEqual(tuple(geometry[0]["end_world"]), (2.0, 0.0, 0.0))
        self.assertEqual(tuple(geometry[1]["start_world"]), (2.0, 0.0, 0.0))
        self.assertEqual(tuple(geometry[1]["end_world"]), (3.0, 0.0, 0.0))

    def test_reordering_chain_points_preserves_the_original_datum_and_continuity(self):
        obj = self._set("CHAIN", ((0, 0, 0), (1, 0, 0), (2, 0, 0), (3, 0, 0)))
        props = obj.dimension_props
        self.assertTrue(move_set_member(props, 0, 1))
        geometry = dimension_set_world_geometry(props)
        self.assertEqual(tuple(geometry[0]["start_world"]), (0.0, 0.0, 0.0))
        self.assertEqual(tuple(geometry[0]["end_world"]), (2.0, 0.0, 0.0))
        self.assertTrue(all(
            (geometry[index]["end_world"] - geometry[index + 1]["start_world"]).length < 1e-6
            for index in range(len(geometry) - 1)
        ))

    def test_baseline_automatic_spacing_derives_from_text_and_is_adjustable(self):
        obj = self._set("BASELINE", ((0, 0, 0), (1, 0, 0), (2, 0, 0), (3, 0, 0)))
        props = obj.dimension_props
        props.text_size = 20
        automatic = automatic_baseline_spacing(props)
        geometry = dimension_set_world_geometry(props)
        self.assertGreaterEqual(automatic, 0.3)
        self.assertAlmostEqual(geometry[1]["offset_distance"] - geometry[0]["offset_distance"], automatic)
        props.set_spacing = 0.75
        adjusted = dimension_set_world_geometry(props)
        self.assertAlmostEqual(adjusted[2]["offset_distance"] - adjusted[1]["offset_distance"], 0.75)

    def test_source_motion_keeps_alignment_and_one_member_can_need_repair(self):
        mesh = bpy.data.meshes.new("DIM-01 Source Mesh")
        mesh.from_pydata(((0, 0, 0), (1, 0, 0), (2, 0, 0)), (), ())
        source = bpy.data.objects.new("DIM-01 Source", mesh)
        self.scene.collection.objects.link(source)
        self.created.append(source)
        obj = self._set("CHAIN", ((0, 0, 0), (1, 0, 0), (2, 0, 0)))
        props = obj.dimension_props
        set_anchor(props.set_members[0].start, source, 0)
        set_anchor(props.set_members[0].end, source, 1)
        set_anchor(props.set_members[1].start, source, 1)
        set_anchor(props.set_members[1].end, source, 2)
        mesh.vertices[2].co.x = 3.0
        mesh.update()
        self.assertEqual([item["value"] for item in dimension_set_world_geometry(props)], [1.0, 2.0])
        props.set_members[1].end.target_object = None
        props.set_members[1].end.resolution_status = "UNRESOLVABLE"
        self.assertEqual(dimension_set_state(props), "NEEDS_REPAIR")
        remaining = dimension_set_world_geometry(props)
        self.assertEqual(remaining[0]["state"], "LIVE")
        self.assertEqual(remaining[1]["state"], "NEEDS_REPAIR")

    def test_off_axis_or_reverse_chain_members_are_repair_cases(self):
        obj = self._set("CHAIN", ((0, 0, 0), (2, 0, 0), (0, 3, 0)))
        geometry = dimension_set_world_geometry(obj.dimension_props)
        self.assertEqual(len(geometry), 2)
        self.assertEqual([item["index"] for item in geometry], [0, 1])
        self.assertEqual([round(item["value"], 3) for item in geometry], [2.0, 2.0])
        self.assertEqual([item["geometry_valid"] for item in geometry], [True, False])
        self.assertEqual(geometry[1]["geometry_issue"], "OFF_AXIS")
        self.assertEqual(dimension_set_state(obj.dimension_props), "NEEDS_REPAIR")
        self.assertIsNone(
            dimension_set_output_spec(bpy.context, obj, "off-axis-set", WorldSizingPolicy(0.01, 0.1), 0.14)
        )

        reverse = self._set("CHAIN", ((0, 0, 0), (2, 0, 0), (1, 0, 0)))
        reverse_geometry = dimension_set_world_geometry(reverse.dimension_props)
        self.assertEqual(reverse_geometry[1]["geometry_issue"], "NON_FORWARD")
        self.assertEqual(dimension_set_state(reverse.dimension_props), "NEEDS_REPAIR")

    def test_saved_perpendicular_member_is_visible_as_a_repair_case_and_never_outputs(self):
        obj = self._set("CHAIN", ((0, 0, 0), (2, 0, 0), (2, 3, 0)))
        props = obj.dimension_props
        geometry = dimension_set_world_geometry(props)
        self.assertEqual(len(geometry), 2)
        self.assertEqual([item["geometry_valid"] for item in geometry], [True, False])
        self.assertEqual(dimension_set_state(props), "NEEDS_REPAIR")
        self.assertIsNone(
            dimension_set_output_spec(bpy.context, obj, "invalid-set", WorldSizingPolicy(0.01, 0.1), 0.14)
        )

    def test_chain_joint_and_baseline_datum_updates_remain_structural(self):
        chain = self._set("CHAIN", ((0, 0, 0), (1, 0, 0), (2, 0, 0)))
        set_world_anchor(chain.dimension_props.set_members[0].end, Vector((1.5, 0, 0)))
        synchronize_set_member_anchor(chain.dimension_props, 0, "END")
        self.assertEqual(
            tuple(chain.dimension_props.set_members[1].start.world_co),
            (1.5, 0.0, 0.0),
        )

        baseline = self._set("BASELINE", ((0, 0, 0), (1, 0, 0), (2, 0, 0)))
        set_world_anchor(baseline.dimension_props.set_members[1].start, Vector((0.5, 0, 0)))
        synchronize_set_member_anchor(baseline.dimension_props, 1, "START")
        self.assertTrue(all(tuple(member.start.world_co) == (0.5, 0.0, 0.0) for member in baseline.dimension_props.set_members))

    def test_manager_represents_the_set_once_and_output_contains_all_members(self):
        obj = self._set("CHAIN", ((0, 0, 0), (1, 0, 0), (1.05, 0, 0)))
        sync_annotation_manager(self.scene)
        rows = [item for item in self.scene.dimensions_settings.annotation_manager_items if item.annotation == obj]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].kind, "DIMENSION_SET")
        self.assertIn("2 members", annotation_display_value(self.scene, obj))
        self.assertEqual(annotation_state(obj), "LIVE")
        spec = dimension_set_output_spec(bpy.context, obj, "set-output", WorldSizingPolicy(0.01, 0.1), 0.14)
        self.assertIsNotNone(spec)
        self.assertGreater(len(spec.strokes), 12)

    def test_short_chain_output_alternates_label_sides(self):
        obj = self._set("CHAIN", ((0, 0, 0), (0.05, 0, 0), (0.1, 0, 0)))
        positions = []
        with patch("dimensions.output_geometry._text_strokes_at", side_effect=lambda _label, position, *_args, **_kwargs: positions.append(Vector(position)) or ()):
            spec = dimension_set_output_spec(
                bpy.context, obj, "alternating-labels", WorldSizingPolicy(0.01, 0.1), 0.14,
            )
        self.assertIsNotNone(spec)
        self.assertEqual(len(positions), 2)
        self.assertGreater(positions[0].x, 0.05)
        self.assertLess(positions[1].x, 0.05)

    def test_dimension_set_hit_testing_delegates_to_member_geometry(self):
        member = {
            "value": 1.0,
            "line_start_screen": Vector((0.0, 0.0)),
            "line_end_screen": Vector((100.0, 0.0)),
            "line_mid_screen": Vector((50.0, 0.0)),
            "line_direction_screen": Vector((1.0, 0.0)),
            "anchor_start_screen": Vector((0.0, -20.0)),
            "anchor_end_screen": Vector((100.0, -20.0)),
            "measurement_state": "LIVE",
            "text_placement": "INLINE",
            "precision": 3,
            "text_size": 14,
            "arrow_size": 10.0,
        }
        geometry = {"annotation_kind": "DIMENSION_SET", "members": (member,)}
        distance = _geometry_hit_distance(bpy.context, geometry, 3, Vector((50.0, 0.0)))
        self.assertLess(distance, 1e-6)
        self.assertIsNone(_geometry_hit_distance(
            bpy.context, {"annotation_kind": "DIMENSION_SET", "members": ()}, 3, Vector(),
        ))

    def test_baseline_viewport_spacing_is_a_minimum_not_a_replacement(self):
        obj = self._set("BASELINE", ((0, 0, 0), (1, 0, 0), (2, 0, 0)))
        props = obj.dimension_props

        def project(_context, start, end, geometry):
            line_start = Vector((geometry["line_start_world"].x, geometry["line_start_world"].y * 100.0))
            line_end = Vector((geometry["line_end_world"].x, geometry["line_end_world"].y * 100.0))
            return {
                "anchor_start_screen": Vector((start.x, start.y * 100.0)),
                "anchor_end_screen": Vector((end.x, end.y * 100.0)),
                "line_start_screen": line_start,
                "line_end_screen": line_end,
                "line_mid_screen": (line_start + line_end) * 0.5,
                "line_direction_screen": Vector((1.0, 0.0)),
            }

        def style(_context, _props, geometry):
            geometry.update({
                "precision": 3, "text_size": 14, "arrow_size": 10.0,
                "color": (1.0, 1.0, 1.0, 1.0),
                "selected_color": (1.0, 0.7, 0.2, 1.0),
            })
            return geometry

        with (
            patch("dimensions.drawing._project_dimension_geometry", side_effect=project),
            patch("dimensions.drawing._annotation_style", side_effect=style),
        ):
            props.set_spacing = 1.0
            expanded = _build_dimension_set_geometry(bpy.context, props)
            self.assertAlmostEqual(
                expanded["members"][1]["line_mid_screen"].y - expanded["members"][0]["line_mid_screen"].y,
                100.0,
            )
            props.set_spacing = 0.01
            clamped = _build_dimension_set_geometry(bpy.context, props)
            self.assertAlmostEqual(
                clamped["members"][1]["line_mid_screen"].y - clamped["members"][0]["line_mid_screen"].y,
                21.0,
            )

    def test_set_generates_through_the_out01_operator(self):
        obj = self._set("BASELINE", ((0, 0, 0), (1, 0, 0), (2, 0, 0)))
        for selected in bpy.context.selected_objects:
            selected.select_set(False)
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        settings = self.scene.dimensions_settings
        settings.output_scope = "SELECTED"
        settings.output_sizing_mode = "WORLD"
        self.assertEqual(bpy.ops.dimensions.generate_output(), {"FINISHED"})
        generated = [item for item in self.scene.objects if item.get("dimensions_generated_output", False)]
        self.assertEqual(len(generated), 1)
        self.assertGreater(len(generated[0].data.layers), 0)
        for item in generated:
            bpy.data.objects.remove(item, do_unlink=True)

    def test_creation_commits_each_member_as_an_explicit_undo_step(self):
        source = inspect.getsource(DIMENSIONS_OT_CreateDimensionSet.modal)
        self.assertIn('push_undo_step("Create Dimension Set Member")', source)

    def test_schema_v6_migrates_additively_and_idempotently(self):
        obj = self._set("CHAIN", ((0, 0, 0), (1, 0, 0)))
        settings = self.scene.dimensions_settings
        settings.schema_version = 6
        self.assertTrue(migrate_scene(self.scene))
        self.assertEqual(settings.schema_version, CURRENT_SCHEMA_VERSION)
        self.assertEqual(obj.dimension_props.set_kind, "CHAIN")
        self.assertEqual(len(obj.dimension_props.set_members), 1)
        self.assertFalse(migrate_scene(self.scene))


def main():
    dimensions.register()
    try:
        result = unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(DimensionsSetTests)
        )
        return 0 if result.wasSuccessful() else 1
    finally:
        dimensions.unregister()


if __name__ == "__main__":
    sys.exit(main())
